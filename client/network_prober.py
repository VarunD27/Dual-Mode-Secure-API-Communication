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
                "error_rate": error_rate,
                "error": None
            }

        except Exception as e:
            return {
                "protocol": "TLS",
                "handshake_time": 9999.0,
                "rtt": 9999.0,
                "payload_size": 0,
                "success": False,
                "error_rate": error_rate,
                "error": str(e)
            }

    def probe_tcp(self) -> dict:
        """
        Probe the TCP server.
        Returns dict with: handshake_time, rtt, payload_size, success
        """
        import hmac
        import hashlib
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

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

            # ── Step 1: Send authenticated HELLO (framed JSON) ──
            client_secret = b"my_shared_secret"
            timestamp = str(time.time())
            signature = hmac.new(
                client_secret,
                timestamp.encode(),
                hashlib.sha256
            ).hexdigest()

            hello_msg = json.dumps({
                "type": "HELLO",
                "timestamp": timestamp,
                "signature": signature
            }).encode("utf-8")
            
            # Frame the HELLO message (4-byte length prefix)
            hello_framed = struct.pack("!I", len(hello_msg)) + hello_msg
            sock.sendall(hello_framed)

            # ── Step 2: ECDH key exchange ──
            # Generate client ECDH key pair
            client_private_key = ec.generate_private_key(ec.SECP256R1())
            client_public_key = client_private_key.public_key()

            client_pub_bytes = client_public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            sock.sendall(client_pub_bytes)

            # Receive server public key (raw recv, not framed)
            server_pub_bytes = sock.recv(1024)
            server_public_key = serialization.load_pem_public_key(server_pub_bytes)

            # Derive shared AES key
            shared_secret = client_private_key.exchange(ec.ECDH(), server_public_key)
            aes_key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=b'handshake data',
            ).derive(shared_secret)

            end_handshake = time.perf_counter()
            handshake_time = (end_handshake - start_handshake) * 1000 + delay_ms  # ms

            # ── Measure RTT with encrypted health request ──
            start_rtt = time.perf_counter()

            request_data = {
                "action": "health",
                "nonce": str(uuid.uuid4()),
                "timestamp": time.time(),
                "hash": ""  # Will be filled below
            }
            
            # Calculate hash
            data_copy = dict(request_data)
            data_copy.pop("hash", None)
            request_data["hash"] = hashlib.sha256(
                json.dumps(data_copy, sort_keys=True).encode()
            ).hexdigest()
            
            request_bytes = json.dumps(request_data).encode("utf-8")
            aesgcm = AESGCM(aes_key)
            nonce = os.urandom(12)
            aad = b"session-bound-data"
            ciphertext = aesgcm.encrypt(nonce, request_bytes, aad)
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
            plaintext = aesgcm.decrypt(resp_nonce, resp_ciphertext, aad)

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
