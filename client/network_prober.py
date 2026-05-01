"""
Network Prober — Probes both TLS and TCP servers to measure
RTT (round-trip time) and handshake duration.
"""

import time
import socket
import base64
import struct
import json
import os
import uuid
import random

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Suppress insecure request warnings for self-signed certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class NetworkProber:
    """Probes both protocols and returns performance metrics."""

    def __init__(self, tls_host="localhost", tls_port=5000,
                 tcp_host="localhost", tcp_port=6000):
        self.tls_url = f"https://{tls_host}:{tls_port}"
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port

    def _load_simulation_config(self):
        """Load simulation configuration from file."""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_file = os.path.join(project_root, "logs", "simulation_config.json")
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {"tls_delay_ms": 0, "tcp_delay_ms": 0, "error_rate": 0.0}

    def probe_tls(self) -> dict:
        """
        Probe the TLS server.
        Returns dict with: handshake_time, rtt, payload_size, success
        """
        config = self._load_simulation_config()
        delay_ms = config.get("tls_delay_ms", 0)
        error_rate = config.get("error_rate", 0.0)

        if error_rate > 0 and random.random() < error_rate:
            return {
                "protocol": "TLS",
                "handshake_time": 9999.0,
                "rtt": 9999.0,
                "payload_size": 0,
                "success": False,
                "error": "Simulated error"
            }

        try:
            # Measure full request (includes TLS handshake on new connection)
            session = requests.Session()

            # Measure handshake + first request
            start_handshake = time.perf_counter()
            response = session.get(
                f"{self.tls_url}/api/health",
                verify=False,
                timeout=10
            )
            end_handshake = time.perf_counter()
            handshake_time = (end_handshake - start_handshake) * 1000 + delay_ms  # ms

            # Measure RTT with a second request (connection already established)
            start_rtt = time.perf_counter()
            response = session.get(
                f"{self.tls_url}/api/data",
                verify=False,
                timeout=10
            )
            end_rtt = time.perf_counter()
            rtt = (end_rtt - start_rtt) * 1000 + delay_ms  # ms

            payload_size = len(response.content)

            return {
                "protocol": "TLS",
                "handshake_time": round(handshake_time, 3),
                "rtt": round(rtt, 3),
                "payload_size": payload_size,
                "success": True,
                "error": None
            }

        except Exception as e:
            return {
                "protocol": "TLS",
                "handshake_time": 9999.0,
                "rtt": 9999.0,
                "payload_size": 0,
                "success": False,
                "error": str(e)
            }

    def probe_tcp(self) -> dict:
        """
        Probe the TCP server.
        Returns dict with: handshake_time, rtt, payload_size, success
        """
        config = self._load_simulation_config()
        delay_ms = config.get("tcp_delay_ms", 0)
        error_rate = config.get("error_rate", 0.0)

        # Simulate error
        if error_rate > 0 and random.random() < error_rate:
            return {
                "protocol": "TCP",
                "handshake_time": 9999.0,
                "rtt": 9999.0,
                "payload_size": 0,
                "success": False,
                "error": f"Simulated error (TCP) - {error_rate * 100:.1f}% error rate",
                "error_rate": error_rate,
            }

        sock = None
        try:
            # Measure TCP connection + custom handshake
            start_handshake = time.perf_counter()

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.tcp_host, self.tcp_port))

            # Send HELLO
            sock.sendall(b"HELLO")

            # Receive ACK with AES key
            ack_data = sock.recv(1024).decode("utf-8")
            if not ack_data.startswith("ACK:"):
                raise Exception(f"Invalid handshake response: {ack_data}")

            end_handshake = time.perf_counter()
            handshake_time = (end_handshake - start_handshake) * 1000 + delay_ms  # ms

            # Extract AES key
            key_b64 = ack_data[4:]
            aes_key = base64.b64decode(key_b64)

            # Measure RTT with an encrypted health request
            start_rtt = time.perf_counter()

            request_data = {
                "action": "health",
                "nonce": str(uuid.uuid4()),  # Unique nonce for probing
                "timestamp": time.time()     # Current timestamp
            }
            request_bytes = json.dumps(request_data).encode("utf-8")
            aesgcm = AESGCM(aes_key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, request_bytes, None)
            encrypted = nonce + ciphertext

            # Send length-prefixed encrypted message
            length = struct.pack("!I", len(encrypted))
            sock.sendall(length + encrypted)

            # Receive length-prefixed response
            raw_len = self._recv_exact(sock, 4)
            msg_len = struct.unpack("!I", raw_len)[0]
            encrypted_response = self._recv_exact(sock, msg_len)

            # Decrypt response
            resp_nonce = encrypted_response[:12]
            resp_ciphertext = encrypted_response[12:]
            plaintext = aesgcm.decrypt(resp_nonce, resp_ciphertext, None)

            end_rtt = time.perf_counter()
            rtt = (end_rtt - start_rtt) * 1000 + delay_ms  # ms

            payload_size = len(plaintext)
            sock.close()

            return {
                "protocol": "TCP",
                "handshake_time": round(handshake_time, 3),
                "rtt": round(rtt, 3),
                "payload_size": payload_size,
                "success": True,
                "error_rate": error_rate,
            }
        except Exception as e:
            if sock:
                sock.close()
            return {
                "protocol": "TCP",
                "handshake_time": 9999.0,
                "rtt": 9999.0,
                "payload_size": 0,
                "success": False,
                "error": str(e),
                "error_rate": error_rate,
            }

    def probe_both(self) -> dict:
        """Probe both protocols and return combined results."""
        tls_result = self.probe_tls()
        tcp_result = self.probe_tcp()
        return {
            "TLS": tls_result,
            "TCP": tcp_result,
            "timestamp": time.time(),
        }

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        """Receive exactly n bytes from a socket."""
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed while receiving data")
            data += chunk
        return data


# Quick standalone test
if __name__ == "__main__":
    prober = NetworkProber()
    print("Probing both servers...")
    results = prober.probe_both()
    print(json.dumps(results, indent=2))
