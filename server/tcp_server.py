"""
Custom TCP Server — Raw socket (port 6000) with AES-GCM encryption.
Uses a custom HELLO→ACK handshake and length-prefixed JSON framing.

Protocol:
  1. Client sends HELLO (authenticated)
  2. ECDH key exchange
  3. Shared AES key derived securely
  4. All messages AES-GCM encrypted
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
import hmac

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from server.shared_api import handle_request, inject_delay
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

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
    aad = b"session-bound-data"
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce + ciphertext


def decrypt_message(key: bytes, data: bytes) -> bytes:
    """
    Decrypt AES-256-GCM encrypted data.
    Expects: nonce (12 bytes) + ciphertext (includes tag)
    """
    aesgcm = AESGCM(key)
    nonce = data[:12]
    ciphertext = data[12:]
    aad = b"session-bound-data"
    return aesgcm.decrypt(nonce, ciphertext, aad)


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
    client_id = f"{addr[0]}:{addr[1]}"
    try:
        # ── Step 1: Custom Handshake ──
        # Wait for HELLO from client
        hello_raw = recv_framed(client_sock)
        if not hello_raw:
            print("[TCP Server] Empty HELLO received")
            client_sock.close()
            return
        try:
            hello = json.loads(hello_raw.decode())
        except Exception as e:
            print("[TCP Server] Invalid HELLO format:", hello_raw)
            client_sock.close()
            return
        timestamp = float(hello.get("timestamp"))
        signature = hello.get("signature")

        # Timestamp validation
        if abs(time.time() - timestamp) > 30:
            print("[TCP Server] Stale HELLO timestamp")
            client_sock.close()
            return

        client_secret = b"my_shared_secret"
        expected_sig = hmac.new(
            client_secret,
            str(timestamp).encode(),
            hashlib.sha256
        ).hexdigest()

        if signature != expected_sig:
            print("[TCP Server] Invalid client authentication")
            client_sock.close()
            return

        # Step 1: Server generates ECDH key pair
        server_private_key = ec.generate_private_key(ec.SECP256R1())
        server_public_key = server_private_key.public_key()

        # Receive client public key
        client_pub_bytes = client_sock.recv(1024)
        client_public_key = serialization.load_pem_public_key(client_pub_bytes)

        # Send server public key
        server_pub_bytes = server_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        client_sock.sendall(server_pub_bytes)

        # Derive shared key
        shared_secret = server_private_key.exchange(ec.ECDH(), client_public_key)

        aes_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'handshake data',
        ).derive(shared_secret)

        print(f"[TCP Server] Secure ECDH handshake complete with {addr}")

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
                plaintext = decrypt_message(aes_key, encrypted_data)
                request_data = json.loads(plaintext.decode("utf-8"))

                # NOW validate hash
                recv_hash = request_data.get("hash")

                data_copy = dict(request_data)
                data_copy.pop("hash", None)

                calc_hash = hashlib.sha256(
                    json.dumps(data_copy, sort_keys=True).encode()
                ).hexdigest()

                if recv_hash != calc_hash:
                    error_response = json.dumps({
                    "status": "error",
                    "message": "Tampered request detected"
                }).encode("utf-8")
                    encrypted_error = encrypt_message(aes_key, error_response)
                    send_framed(client_sock, encrypted_error)
                    continue
                
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
