"""
Custom TCP Server — Raw socket (port 6000) with AES-GCM encryption.
Uses a custom HELLO→ACK handshake and length-prefixed JSON framing.

Protocol:
  1. Client connects via TCP
  2. Client sends: HELLO
  3. Server responds: ACK:<base64-encoded-aes-key>
  4. All subsequent messages are AES-256-GCM encrypted
  5. Message format: [4-byte length][nonce (12 bytes)][tag (16 bytes)][ciphertext]
"""

import os
import sys
import json
import socket
import struct
import base64
import argparse
import threading
import time
import hashlib
import random
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from server.shared_api import handle_request, inject_delay

# Default settings
ARTIFICIAL_DELAY_MS = 20.0
HOST = "0.0.0.0"
PORT = 6000
# Packet loss simulation (0.0 = 0%, 1.0 = 100%)
PACKET_LOSS_RATE = 0.0

# Replay attack prevention
NONCE_CACHE_SIZE = 1000
TIMESTAMP_TOLERANCE_SECONDS = 300  # 5 minutes


class ReplayProtection:
    """Manages nonce and timestamp-based replay attack protection."""
    
    def __init__(self, max_size=1000, timestamp_tolerance=300):
        self.max_size = max_size
        self.timestamp_tolerance = timestamp_tolerance
        self.seen_nonces = set()
        self.client_timestamps = defaultdict(list)  # client_id -> list of timestamps
        
    def is_valid_request(self, nonce: str, timestamp: float, client_id: str = None) -> bool:
        """Check if request is valid (not a replay)."""
        current_time = time.time()
        
        # Check timestamp freshness
        if abs(current_time - timestamp) > self.timestamp_tolerance:
            print(f"[TCP Server] Rejected stale timestamp: {timestamp} (current: {current_time})")
            return False
            
        # Check nonce uniqueness
        if nonce in self.seen_nonces:
            print(f"[TCP Server] Rejected replay nonce: {nonce}")
            return False
            
        # Check client-specific timestamp tracking
        if client_id:
            client_ts_list = self.client_timestamps[client_id]
            # Remove old timestamps outside tolerance window
            cutoff_time = current_time - self.timestamp_tolerance
            self.client_timestamps[client_id] = [ts for ts in client_ts_list if ts > cutoff_time]
            
            # Check if this timestamp was already used by this client
            if timestamp in self.client_timestamps[client_id]:
                print(f"[TCP Server] Rejected replay timestamp for client {client_id}: {timestamp}")
                return False
                
            # Add new timestamp
            self.client_timestamps[client_id].append(timestamp)
            
            # Limit list size
            if len(self.client_timestamps[client_id]) > 100:
                self.client_timestamps[client_id] = self.client_timestamps[client_id][-50:]
        
        # Add nonce to cache
        self.seen_nonces.add(nonce)
        
        # Limit cache size
        if len(self.seen_nonces) > self.max_size:
            # Remove oldest entries (simple approach: clear half the cache)
            nonces_list = list(self.seen_nonces)
            self.seen_nonces = set(nonces_list[self.max_size//2:])
        
        return True

# Global replay protection instance
replay_protection = ReplayProtection(NONCE_CACHE_SIZE, TIMESTAMP_TOLERANCE_SECONDS)


def generate_aes_key() -> bytes:
    """Generate a random 256-bit AES key."""
    return AESGCM.generate_key(bit_length=256)


def encrypt_message(key: bytes, plaintext: bytes) -> bytes:
    """
    Encrypt plaintext using AES-256-GCM.
    Returns: nonce (12 bytes) + tag (included in ciphertext by AESGCM) + ciphertext
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)  # ciphertext includes 16-byte tag
    return nonce + ciphertext


def decrypt_message(key: bytes, data: bytes) -> bytes:
    """
    Decrypt AES-256-GCM encrypted data.
    Expects: nonce (12 bytes) + ciphertext (includes tag)
    """
    aesgcm = AESGCM(key)
    nonce = data[:12]
    ciphertext = data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)


def send_framed(sock: socket.socket, data: bytes):
    """Send a length-prefixed message."""
    length = struct.pack("!I", len(data))
    sock.sendall(length + data)


def recv_framed(sock: socket.socket) -> bytes:
    """Receive a length-prefixed message."""
    # Read 4-byte length header
    raw_len = recv_exact(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack("!I", raw_len)[0]
    # Read the full message
    return recv_exact(sock, msg_len)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes from a socket."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def handle_client(client_sock: socket.socket, addr: tuple):
    """Handle a single client connection."""
    print(f"[TCP Server] New connection from {addr}")
    client_id = f"{addr[0]}:{addr[1]}"

    try:
        # ── Step 1: Custom Handshake ──
        # Wait for HELLO from client
        hello = client_sock.recv(1024).decode("utf-8").strip()
        if hello != "HELLO":
            print(f"[TCP Server] Invalid handshake from {addr}: {hello}")
            client_sock.close()
            return

        # Generate AES key and send ACK with key
        aes_key = generate_aes_key()
        key_b64 = base64.b64encode(aes_key).decode("utf-8")
        ack_msg = f"ACK:{key_b64}"
        client_sock.sendall(ack_msg.encode("utf-8"))
        print(f"[TCP Server] Handshake complete with {addr}")

        # ── Step 2: Handle encrypted requests ──
        while True:
            encrypted_data = recv_framed(client_sock)
            if encrypted_data is None:
                print(f"[TCP Server] Client {addr} disconnected")
                break

            # Inject artificial delay
            inject_delay(ARTIFICIAL_DELAY_MS)
            
            # Simulate packet loss
            if PACKET_LOSS_RATE > 0 and random.random() < PACKET_LOSS_RATE:
                print(f"[TCP Server] Simulating packet loss for {addr}")
                # Close connection to simulate packet loss
                client_sock.close()
                return

            try:
                # Decrypt the request
                plaintext = decrypt_message(aes_key, encrypted_data)
                request_data = json.loads(plaintext.decode("utf-8"))
                
                # Extract nonce and timestamp for replay protection
                nonce = request_data.get("nonce")
                timestamp = request_data.get("timestamp")
                
                if nonce is None or timestamp is None:
                    print(f"[TCP Server] Missing nonce/timestamp from {addr}")
                    error_response = json.dumps({
                        "status": "error",
                        "message": "Missing nonce or timestamp"
                    }).encode("utf-8")
                    encrypted_error = encrypt_message(aes_key, error_response)
                    send_framed(client_sock, encrypted_error)
                    continue
                
                # Validate request (replay protection)
                if not replay_protection.is_valid_request(nonce, timestamp, client_id):
                    error_response = json.dumps({
                        "status": "error",
                        "message": "Request rejected (potential replay attack)"
                    }).encode("utf-8")
                    encrypted_error = encrypt_message(aes_key, error_response)
                    send_framed(client_sock, encrypted_error)
                    continue

                # Process the request
                action = request_data.get("action", "health")
                payload = request_data.get("payload", {})
                response = handle_request(action, payload)
                response["protocol"] = "TCP"
                response["server_timestamp"] = time.time()

                # Encrypt and send the response
                response_bytes = json.dumps(response).encode("utf-8")
                encrypted_response = encrypt_message(aes_key, response_bytes)
                send_framed(client_sock, encrypted_response)

            except Exception as e:
                print(f"[TCP Server] Error processing request from {addr}: {e}")
                error_response = json.dumps({
                    "status": "error",
                    "message": str(e)
                }).encode("utf-8")
                encrypted_error = encrypt_message(aes_key, error_response)
                send_framed(client_sock, encrypted_error)

    except (ConnectionResetError, BrokenPipeError, OSError) as e:
        print(f"[TCP Server] Connection lost with {addr}: {e}")
    finally:
        client_sock.close()
        print(f"[TCP Server] Connection closed: {addr}")


def main():
    global ARTIFICIAL_DELAY_MS, PORT, PACKET_LOSS_RATE

    parser = argparse.ArgumentParser(description="Custom TCP Server with AES-GCM")
    parser.add_argument("--port", type=int, default=6000, help="Port to listen on (default: 6000)")
    parser.add_argument("--delay", type=float, default=20.0, help="Artificial delay in ms (default: 20)")
    parser.add_argument("--packet-loss", type=float, default=0.0, help="Packet loss rate 0.0-1.0 (default: 0.0)")
    args = parser.parse_args()

    ARTIFICIAL_DELAY_MS = args.delay
    PORT = args.port
    PACKET_LOSS_RATE = args.packet_loss

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(5)

    print(f"[TCP Server] Starting on tcp://localhost:{PORT}")
    print(f"[TCP Server] Artificial delay: {ARTIFICIAL_DELAY_MS}ms")
    print(f"[TCP Server] Packet loss simulation: {PACKET_LOSS_RATE*100:.1f}%")
    print(f"[TCP Server] AES-256-GCM encryption enabled")
    print(f"[TCP Server] Custom HELLO->ACK handshake")
    print(f"[TCP Server] Replay attack protection enabled (nonce + timestamp)")
    print(f"[TCP Server] Press Ctrl+C to stop\n")

    try:
        while True:
            client_sock, addr = server_sock.accept()
            thread = threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\n[TCP Server] Shutting down...")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
