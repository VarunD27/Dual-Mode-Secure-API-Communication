"""
Session Manager — Manages active connections to TLS and TCP servers.
Handles connection lifecycle, protocol switching, and request execution.
"""

import json
import os
import socket
import struct
import time
import base64

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Suppress insecure request warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SessionManager:
    """
    Maintains one active connection (HTTP keep-alive or persistent TCP socket).
    Handles switching between protocols cleanly.
    """

    def __init__(self, tls_host="localhost", tls_port=5000,
                 tcp_host="localhost", tcp_port=6000):
        self.tls_url = f"https://{tls_host}:{tls_port}"
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port

        # Active connections
        self._http_session = None
        self._tcp_socket = None
        self._aes_key = None

        # State tracking
        self.active_protocol = None
        self.request_count = 0
        self.last_eval_time = time.time()

    def connect_tls(self):
        """Establish an HTTP keep-alive session to the TLS server."""
        self.close_all()
        self._http_session = requests.Session()
        # Verify the connection works
        self._http_session.get(f"{self.tls_url}/api/health", verify=False, timeout=10)
        self.active_protocol = "TLS"
        self.request_count = 0
        print(f"[Session] Connected to TLS server at {self.tls_url}")

    def connect_tcp(self):
        """Establish a persistent TCP connection with HELLO→ACK handshake."""
        self.close_all()
        self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_socket.settimeout(10)
        self._tcp_socket.connect((self.tcp_host, self.tcp_port))

        # Custom handshake
        self._tcp_socket.sendall(b"HELLO")
        ack_data = self._tcp_socket.recv(1024).decode("utf-8")
        if not ack_data.startswith("ACK:"):
            raise Exception(f"TCP handshake failed: {ack_data}")

        key_b64 = ack_data[4:]
        self._aes_key = base64.b64decode(key_b64)
        self.active_protocol = "TCP"
        self.request_count = 0
        print(f"[Session] Connected to TCP server at {self.tcp_host}:{self.tcp_port}")

    def connect(self, protocol: str):
        """Connect to the specified protocol."""
        if protocol == "TLS":
            self.connect_tls()
        elif protocol == "TCP":
            self.connect_tcp()
        else:
            raise ValueError(f"Unknown protocol: {protocol}")

    def switch_to(self, new_protocol: str):
        """Switch to a different protocol."""
        if new_protocol == self.active_protocol:
            return
        print(f"[Session] Switching from {self.active_protocol} to {new_protocol}")
        self.connect(new_protocol)

    def send_request(self, action: str, payload: dict = None) -> dict:
        """
        Send a request using the currently active protocol.
        
        Args:
            action: API action ("health", "data", "echo", "compute")
            payload: Optional payload for echo action
            
        Returns:
            dict with response data and timing metrics
        """
        self.request_count += 1

        if self.active_protocol == "TLS":
            return self._send_tls_request(action, payload)
        elif self.active_protocol == "TCP":
            return self._send_tcp_request(action, payload)
        else:
            raise Exception("No active protocol. Call connect() first.")

    def _send_tls_request(self, action: str, payload: dict = None) -> dict:
        """Send request via TLS/HTTPS."""
        start = time.perf_counter()

        if action == "echo":
            response = self._http_session.post(
                f"{self.tls_url}/api/{action}",
                json=payload or {"message": "test"},
                verify=False,
                timeout=10,
            )
        else:
            response = self._http_session.get(
                f"{self.tls_url}/api/{action}",
                verify=False,
                timeout=10,
            )

        elapsed = (time.perf_counter() - start) * 1000  # ms
        data = response.json()
        data["_rtt_ms"] = round(elapsed, 3)
        data["_payload_size"] = len(response.content)
        return data

    def _send_tcp_request(self, action: str, payload: dict = None) -> dict:
        """Send request via custom TCP + AES-GCM."""
        start = time.perf_counter()

        # Build request
        request_data = {"action": action}
        if payload:
            request_data["payload"] = payload
        plaintext = json.dumps(request_data).encode("utf-8")

        # Encrypt
        aesgcm = AESGCM(self._aes_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        encrypted = nonce + ciphertext

        # Send length-prefixed
        length = struct.pack("!I", len(encrypted))
        self._tcp_socket.sendall(length + encrypted)

        # Receive response
        raw_len = self._recv_exact(self._tcp_socket, 4)
        msg_len = struct.unpack("!I", raw_len)[0]
        encrypted_response = self._recv_exact(self._tcp_socket, msg_len)

        # Decrypt
        resp_nonce = encrypted_response[:12]
        resp_ciphertext = encrypted_response[12:]
        response_plaintext = aesgcm.decrypt(resp_nonce, resp_ciphertext, None)

        elapsed = (time.perf_counter() - start) * 1000  # ms
        data = json.loads(response_plaintext.decode("utf-8"))
        data["_rtt_ms"] = round(elapsed, 3)
        data["_payload_size"] = len(response_plaintext)
        return data

    def should_reevaluate(self, interval_requests=5, interval_seconds=10) -> bool:
        """Check if it's time to re-evaluate the protocol choice."""
        time_elapsed = time.time() - self.last_eval_time
        if self.request_count >= interval_requests or time_elapsed >= interval_seconds:
            self.last_eval_time = time.time()
            self.request_count = 0
            return True
        return False

    def close_all(self):
        """Close all active connections cleanly."""
        if self._http_session:
            try:
                self._http_session.close()
            except Exception:
                pass
            self._http_session = None

        if self._tcp_socket:
            try:
                self._tcp_socket.close()
            except Exception:
                pass
            self._tcp_socket = None
            self._aes_key = None

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        """Receive exactly n bytes."""
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        return data
