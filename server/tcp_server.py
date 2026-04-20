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

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from server.shared_api import handle_request, inject_delay

# Default settings
ARTIFICIAL_DELAY_MS = 20.0
HOST = "0.0.0.0"
PORT = 6000


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

            try:
                # Decrypt the request
                plaintext = decrypt_message(aes_key, encrypted_data)
                request_data = json.loads(plaintext.decode("utf-8"))

                # Process the request
                action = request_data.get("action", "health")
                payload = request_data.get("payload", {})
                response = handle_request(action, payload)
                response["protocol"] = "TCP"

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
    global ARTIFICIAL_DELAY_MS, PORT

    parser = argparse.ArgumentParser(description="Custom TCP Server with AES-GCM")
    parser.add_argument("--port", type=int, default=6000, help="Port to listen on (default: 6000)")
    parser.add_argument("--delay", type=float, default=20.0, help="Artificial delay in ms (default: 20)")
    args = parser.parse_args()

    ARTIFICIAL_DELAY_MS = args.delay
    PORT = args.port

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(5)

    print(f"[TCP Server] Starting on tcp://localhost:{PORT}")
    print(f"[TCP Server] Artificial delay: {ARTIFICIAL_DELAY_MS}ms")
    print(f"[TCP Server] AES-256-GCM encryption enabled")
    print(f"[TCP Server] Custom HELLO->ACK handshake")
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
