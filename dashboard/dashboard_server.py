"""
Dashboard Server — Serves the real-time visualization dashboard.
Runs on port 8080, serves static files and provides a /api/logs endpoint.
"""

import os
import sys
import json
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler


# Project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "session_log.json")


class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler that serves dashboard files and the logs API."""

    def __init__(self, *args, **kwargs):
        # Serve files from the dashboard directory
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/api/logs":
            self._serve_logs()
        else:
            super().do_GET()

    def _serve_logs(self):
        """Serve the session log as JSON."""
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r") as f:
                    data = json.load(f)
            else:
                data = []
        except (json.JSONDecodeError, IOError):
            data = []

        response = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(response))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        """Suppress default access logs for cleaner output."""
        pass


def main():
    parser = argparse.ArgumentParser(description="Dashboard Server")
    parser.add_argument("--port", type=int, default=8080,
                        help="Port to serve dashboard on (default: 8080)")
    args = parser.parse_args()

    server = HTTPServer(("0.0.0.0", args.port), DashboardHandler)
    print(f"[Dashboard] Serving at http://localhost:{args.port}")
    print(f"[Dashboard] Reading logs from: {LOG_FILE}")
    print(f"[Dashboard] Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Dashboard] Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
