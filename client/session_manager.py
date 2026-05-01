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
import uuid
import random

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
                 tcp_host="localhost", tcp_port=6000, enable_fallback=False):
        self.tls_url = f"https://{tls_host}:{tls_port}"
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self._fallback_enabled = enable_fallback

        # Active connections
        self._http_session = None
        self._tcp_socket = None
        self._aes_key = None

        # State tracking
        self.active_protocol = None
        self.request_count = 0
        self.last_eval_time = time.time()
        self.error_counts = {"TLS": 0, "TCP": 0}
        self.last_errors = {"TLS": None, "TCP": None}
        self._last_handshake_time = {"TLS": 0.0, "TCP": 0.0}
        self._success_counts = {"TLS": 0, "TCP": 0}
        self._failure_counts = {"TLS": 0, "TCP": 0}
        
        # Simulation settings
        self.simulation_config = self._load_simulation_config()
        self._last_config_check = 0
    
    def _load_simulation_config(self):
        """Load simulation configuration from file."""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_file = os.path.join(project_root, "logs", "simulation_config.json")
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[SessionManager] Failed to load simulation config: {e}")
        
        # Default configuration
        return {
            "tls_delay_ms": 0,
            "tcp_delay_ms": 0,
            "error_rate": 0.0
        }
    
    def _reload_config_if_needed(self):
        """Reload simulation config if enough time has passed."""
        current_time = time.time()
        if current_time - self._last_config_check > 2.0:  # Check every 2 seconds
            self.simulation_config = self._load_simulation_config()
            self._last_config_check = current_time

    def connect_tls(self):
        """Establish an HTTP keep-alive session to the TLS server."""
        self.close_all()
        start_handshake = time.perf_counter()
        self._http_session = requests.Session()
        # Verify the connection works
        self._http_session.get(f"{self.tls_url}/api/health", verify=False, timeout=10)
        end_handshake = time.perf_counter()
        self._last_handshake_time["TLS"] = (end_handshake - start_handshake) * 1000
        self.active_protocol = "TLS"
        self.request_count = 0
        print(f"[Session] Connected to TLS server at {self.tls_url}")

    def connect_tcp(self):
        """Establish a persistent TCP connection with HELLO→ACK handshake."""
        self.close_all()
        start_handshake = time.perf_counter()
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
        end_handshake = time.perf_counter()
        self._last_handshake_time["TCP"] = (end_handshake - start_handshake) * 1000
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
        Send a request using the currently active protocol with enhanced error handling.
        
        Args:
            action: API action ("health", "data", "echo", "compute")
            payload: Optional payload for echo action
            
        Returns:
            dict with response data and timing metrics
        """
        self.request_count += 1
        
        # Reload config periodically to pick up changes
        self._reload_config_if_needed()

        if self.active_protocol == "TLS":
            try:
                return self._send_tls_request(action, payload)
            except Exception as e:
                print(f"[Session] TLS request failed: {e}")
                # Try to fallback to TCP if available
                if hasattr(self, '_fallback_enabled') and self._fallback_enabled:
                    print(f"[Session] Attempting fallback to TCP...")
                    try:
                        self.connect_tcp()
                        return self._send_tcp_request(action, payload)
                    except Exception as fallback_error:
                        print(f"[Session] Fallback failed: {fallback_error}")
                raise e
        elif self.active_protocol == "TCP":
            try:
                return self._send_tcp_request(action, payload)
            except Exception as e:
                print(f"[Session] TCP request failed: {e}")
                # Try to reconnect
                try:
                    print(f"[Session] Attempting TCP reconnection...")
                    self.connect_tcp()
                    return self._send_tcp_request(action, payload)
                except Exception as reconnect_error:
                    print(f"[Session] Reconnection failed: {reconnect_error}")
                raise e
        else:
            raise Exception("No active protocol. Call connect() first.")

    def _send_tls_request(self, action: str, payload: dict = None) -> dict:
        """Send request via TLS/HTTPS with enhanced error handling."""
        start = time.perf_counter()
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
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
                
                # Apply artificial delay if configured
                delay_ms = self.simulation_config.get("tls_delay_ms", 0)
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                    elapsed += delay_ms
                
                # Simulate errors if configured
                error_rate = self.simulation_config.get("error_rate", 0.0)
                if error_rate > 0 and random.random() < error_rate:
                    raise Exception(f"Simulated error (TLS) - {error_rate * 100:.1f}% error rate")
                
                # Check for HTTP errors
                if response.status_code >= 400:
                    if response.status_code == 500 and "packet loss" in response.text:
                        # Simulated packet loss, retry
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (2 ** attempt))
                            continue
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
                
                data = response.json()
                data["_rtt_ms"] = round(elapsed, 3)
                data["_payload_size"] = len(response.content)
                return data
                
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                raise Exception("TLS request timeout")
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                raise Exception(f"TLS connection error: {e}")
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                raise Exception(f"TLS request failed: {e}")
        
        raise Exception(f"TLS request failed after {max_retries} attempts")

    def _send_tcp_request(self, action: str, payload: dict = None) -> dict:
        """Send request via custom TCP + AES-GCM with enhanced error handling."""
        start = time.perf_counter()
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                # Build request with nonce and timestamp for replay protection
                request_data = {
                    "action": action,
                    "nonce": str(uuid.uuid4()),  # Unique nonce for each request
                    "timestamp": time.time()     # Current timestamp
                }
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
                if not raw_len:
                    raise Exception("Connection closed by server")
                msg_len = struct.unpack("!I", raw_len)[0]
                encrypted_response = self._recv_exact(self._tcp_socket, msg_len)
                
                if not encrypted_response:
                    raise Exception("No response received")

                # Decrypt
                aesgcm = AESGCM(self._aes_key)
                nonce = encrypted_response[:12]
                ciphertext = encrypted_response[12:]
                response_plaintext = aesgcm.decrypt(nonce, ciphertext, None)
                data = json.loads(response_plaintext.decode("utf-8"))
                
                elapsed = (time.perf_counter() - start) * 1000  # ms
                
                # Apply artificial delay if configured
                delay_ms = self.simulation_config.get("tcp_delay_ms", 0)
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                    elapsed += delay_ms
                
                # Simulate errors if configured
                error_rate = self.simulation_config.get("error_rate", 0.0)
                if error_rate > 0 and random.random() < error_rate:
                    raise Exception(f"Simulated error (TCP) - {error_rate * 100:.1f}% error rate")
                
                # Check for server errors
                if data.get("status") == "error":
                    if "packet loss" in data.get("message", ""):
                        # Simulated packet loss, retry
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (2 ** attempt))
                            continue
                    raise Exception(f"Server error: {data.get('message', 'Unknown error')}")
                
                data["_rtt_ms"] = round(elapsed, 3)
                data["_payload_size"] = len(response_plaintext)
                return data
                
            except (ConnectionResetError, BrokenPipeError) as e:
                if attempt < max_retries - 1:
                    # Try to reconnect
                    try:
                        self.connect_tcp()
                        time.sleep(retry_delay * (2 ** attempt))
                        continue
                    except Exception:
                        pass
                raise Exception(f"TCP connection lost: {e}")
            except socket.timeout:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                raise Exception("TCP request timeout")
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                raise Exception(f"TCP request failed: {e}")
        
        raise Exception(f"TCP request failed after {max_retries} attempts")

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
