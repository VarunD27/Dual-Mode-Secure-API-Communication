"""
TLS Server — Flask over HTTPS (port 5000) with TLS 1.3.
Provides JSON API endpoints with configurable artificial delay.
"""

import os
import sys
import ssl
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from server.shared_api import handle_request, inject_delay

app = Flask(__name__)

# Default delay in milliseconds (configurable via CLI)
ARTIFICIAL_DELAY_MS = 20.0


@app.before_request
def apply_delay():
    """Inject artificial delay before processing each request."""
    inject_delay(ARTIFICIAL_DELAY_MS)


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    result = handle_request("health")
    result["protocol"] = "TLS"
    result["delay_ms"] = ARTIFICIAL_DELAY_MS
    return jsonify(result)


@app.route("/api/data", methods=["GET"])
def get_data():
    """Return sample data."""
    result = handle_request("data")
    result["protocol"] = "TLS"
    return jsonify(result)


@app.route("/api/echo", methods=["POST"])
def echo():
    """Echo back the received payload."""
    payload = request.get_json(silent=True) or {}
    result = handle_request("echo", payload)
    result["protocol"] = "TLS"
    return jsonify(result)


@app.route("/api/compute", methods=["GET"])
def compute():
    """Run a simulated computation."""
    result = handle_request("compute")
    result["protocol"] = "TLS"
    return jsonify(result)


@app.route("/api/set_delay", methods=["POST"])
def set_delay():
    """Dynamically change the artificial delay. Expects JSON: {"delay_ms": <number>}"""
    global ARTIFICIAL_DELAY_MS
    data = request.get_json(silent=True) or {}
    new_delay = data.get("delay_ms", ARTIFICIAL_DELAY_MS)
    ARTIFICIAL_DELAY_MS = float(new_delay)
    return jsonify({"status": "ok", "delay_ms": ARTIFICIAL_DELAY_MS})


def main():
    global ARTIFICIAL_DELAY_MS

    parser = argparse.ArgumentParser(description="TLS Server (Flask HTTPS)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--delay", type=float, default=20.0, help="Artificial delay in ms (default: 20)")
    args = parser.parse_args()

    ARTIFICIAL_DELAY_MS = args.delay

    # Paths to TLS certificates
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cert_path = os.path.join(project_root, "certs", "server.crt")
    key_path = os.path.join(project_root, "certs", "server.key")

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        print("[!] TLS certificates not found. Run 'python generate_certs.py' first.")
        sys.exit(1)

    # Configure TLS context for TLS 1.3
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    print(f"[TLS Server] Starting on https://localhost:{args.port}")
    print(f"[TLS Server] Artificial delay: {ARTIFICIAL_DELAY_MS}ms")
    print(f"[TLS Server] TLS 1.3 enabled")
    print(f"[TLS Server] Press Ctrl+C to stop\n")

    app.run(
        host="0.0.0.0",
        port=args.port,
        ssl_context=context,
        debug=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
