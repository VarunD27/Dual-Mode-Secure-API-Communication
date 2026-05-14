"""
Dashboard Server — Serves the real-time visualization dashboard.
Runs on port 8080, serves static files and provides a /api/logs endpoint.
"""

import os
import sys
import json
import time
import random
import argparse
import signal
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler


# Project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
SESSION_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "session_log.json")
MANUAL_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "manual_session_log.json")


# Global variable to track the auto client process
auto_client_process = None

# Global variables to store auto-run state
auto_run_state = "stopped"  # "stopped", "running", "completed"
expected_request_count = 30

# Global variables to store delays for simulation
tls_delay_ms = 0
tcp_delay_ms = 0
error_rate_simulation = 0.0  # 0% error rate by default

# Stop flag file
STOP_FLAG_FILE = os.path.join(PROJECT_ROOT, "logs", "stop_flag.json")

class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler that serves dashboard files and the logs API."""

    def __init__(self, *args, **kwargs):
        # Serve files from the dashboard directory
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/api/logs":
            self._serve_logs()
        elif self.path == "/api/get-settings":
            self._get_settings()
        elif self.path == "/logs/simulation_config.json":
            self._serve_simulation_config()
        else:
            super().do_GET()
    
    def do_POST(self):
        """Handle POST requests for control endpoints."""
        if self.path == "/api/set-delay":
            self._set_delay()
        elif self.path == "/api/probe-network":
            self._probe_network()
        elif self.path == "/api/reset-delays":
            self._reset_delays()
        elif self.path == "/api/run-auto":
            self._run_auto()
        elif self.path == "/api/clear-logs":
            self._clear_logs()
        elif self.path == "/api/set-error-rate":
            self._set_error_rate()
        elif self.path == "/api/get-settings":
            self._get_settings()
        elif self.path == "/api/stop-auto":
            self._stop_auto()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_logs(self):
        """Serve combined logs from both session and manual clients."""
        try:
            all_logs = []
            
            # Load session logs
            if os.path.exists(SESSION_LOG_FILE):
                try:
                    with open(SESSION_LOG_FILE, "r") as f:
                        session_logs = json.load(f)
                        all_logs.extend(session_logs)
                except (json.JSONDecodeError, IOError):
                    pass
            
            # Load manual logs
            if os.path.exists(MANUAL_LOG_FILE):
                try:
                    with open(MANUAL_LOG_FILE, "r") as f:
                        manual_logs = json.load(f)
                        # Add a prefix to distinguish manual logs
                        for log in manual_logs:
                            log['source'] = 'manual'
                        all_logs.extend(manual_logs)
                except (json.JSONDecodeError, IOError):
                    pass
            
            # Sort by timestamp if available
            if all_logs:
                all_logs.sort(key=lambda x: x.get('timestamp', 0))
            
        except Exception:
            all_logs = []

        response = json.dumps(all_logs).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(response))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response)

    def _set_delay(self):
        """Set delay for TLS or TCP server."""
        try:
            global tls_delay_ms, tcp_delay_ms
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            protocol = data.get('protocol')
            delay = data.get('delay')
            
            # Store the delay for simulation
            if protocol.lower() == 'tls':
                tls_delay_ms = delay
            elif protocol.lower() == 'tcp':
                tcp_delay_ms = delay
            
            # Write to config file for clients to read
            self._write_simulation_config()
            
            print(f"[Dashboard] Setting {protocol.upper()} delay to {delay}ms")
            
            response = json.dumps({"success": True, "message": f"{protocol.upper()} delay set to {delay}ms"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())
            
        except Exception as e:
            error_response = json.dumps({"success": False, "error": str(e)})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(error_response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def _probe_network(self):
        """Probe network and return configuration data."""
        print("[Dashboard] Probe network called")

        try:
            # Read request body (ignore content)
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                self.rfile.read(content_length)

            # FIX 1: Ensure correct import path
            if PROJECT_ROOT not in sys.path:
                sys.path.insert(0, PROJECT_ROOT)

            try:
                from client.network_prober import NetworkProber
                from client.decision_engine import DecisionEngine
            except Exception as import_error:
                print("[Dashboard ERROR] Import failed:", import_error)
                raise import_error

            # FIX 2: Run prober
            prober = NetworkProber()
            results = prober.probe_both()

            print("[Dashboard] Probe Results:", results)

            # FIX 3: Validate probe results
            if not results or "TLS" not in results or "TCP" not in results:
                raise Exception("Invalid probe results")

            # FIX 4: Run decision engine
            engine = DecisionEngine()
            evaluation = engine.evaluate(results["TLS"], results["TCP"])

            print("[Dashboard] Evaluation:", evaluation)

            # Extract error rates safely
            tls_reliability = evaluation["tls_components"]["normalized"].get("reliability", 1.0)
            tcp_reliability = evaluation["tcp_components"]["normalized"].get("reliability", 1.0)
            # ✅ FINAL DATA (REAL VALUES)
            data = {
                "tls_rtt": results["TLS"]["rtt"],
                "tcp_rtt": results["TCP"]["rtt"],
                "tls_handshake": results["TLS"]["handshake_time"],
                "tcp_handshake": results["TCP"]["handshake_time"],
                "tls_score": evaluation["tls_score"],
                "tcp_score": evaluation["tcp_score"],
                "tls_payload": results["TLS"]["payload_size"],
                "tcp_payload": results["TCP"]["payload_size"],
                "tls_security": 1.0,
                "tcp_security": 5.0,
                "tls_reliability": 1.0 - tls_reliability,
                "tcp_reliability": 1.0 - tcp_reliability,
                "has_logs": 0
            }

            print("[Dashboard] Sending Data:", data)

            response = json.dumps({"success": True, "data": data})

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())

        except Exception as e:
            print("[Dashboard ERROR] Probe failed:", str(e))

            # ❌ REMOVE SILENT ZERO FALLBACK → instead send error
            response = json.dumps({
                "success": False,
                "error": str(e)
            })

            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())

    def _reset_delays(self):
        """Reset all delays to default."""
        try:
            global tls_delay_ms, tcp_delay_ms, error_rate_simulation
            tls_delay_ms = 0
            tcp_delay_ms = 0
            error_rate_simulation = 0.0
            
            # Write to config file for clients to read
            self._write_simulation_config()
            
            # Also reset TLS server internal delay and packet loss via its API
            try:
                import requests as req_lib
                req_lib.post(
                    "https://localhost:5000/api/set_delay",
                    json={"delay_ms": 0},
                    verify=False,
                    timeout=3,
                )
                req_lib.post(
                    "https://localhost:5000/api/set_packet_loss",
                    json={"loss_rate": 0.0},
                    verify=False,
                    timeout=3,
                )
                print("[Dashboard] Reset TLS server delay and packet loss to 0")
            except Exception as api_err:
                print(f"[Dashboard] Could not reset TLS server via API: {api_err}")
            
            print(f"[Dashboard] Resetting delays to 0ms and error rate to 0%")
            
            response = json.dumps({"success": True, "message": "Delays and error rate reset to 0"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())
            
        except Exception as e:
            error_response = json.dumps({"success": False, "error": str(e)})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(error_response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def _run_auto(self):
        """Start automatic client for 30 requests."""
        try:
            import threading
            global auto_client_process, auto_run_state
            
            # Clear stop flag
            try:
                with open(STOP_FLAG_FILE, 'w') as f:
                    json.dump({"stop": False}, f)
            except Exception:
                pass
            
            # Kill any existing auto client process
            if auto_client_process and auto_client_process.poll() is None:
                self._kill_process_tree(auto_client_process.pid)
                auto_client_process = None
            
            # Set state to running
            auto_run_state = "running"
            
            # Start the adaptive client in a separate thread
            def run_client():
                try:
                    global auto_client_process, auto_run_state
                    client_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "client")
                    
                    # Create process with process group for proper termination
                    import signal
                    auto_client_process = subprocess.Popen(
                        ["python", "adaptive_client.py", "--count", "30"], 
                        cwd=client_path, 
                        stdout=None, 
                        stderr=None,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                    )
                    auto_client_process.wait()
                    
                    # Check if completed successfully (did not get killed)
                    if auto_client_process and auto_client_process.returncode == 0:
                        auto_run_state = "completed"
                    else:
                        # Was killed or crashed
                        auto_run_state = "stopped"
                except Exception as e:
                    print(f"Error running auto client: {e}")
                    auto_run_state = "stopped"
                finally:                    
                    auto_client_process = None
            
            # Start the client thread
            thread = threading.Thread(target=run_client, daemon=True)
            thread.start()
            
            response = json.dumps({"success": True, "message": "Auto client started for 30 requests"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())
            
        except Exception as e:
            error_response = json.dumps({"success": False, "error": str(e)})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(error_response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def _set_error_rate(self, error_rate=None):
        """Set error rate for simulation."""
        try:
            global error_rate_simulation
            
            # If error_rate is provided as parameter, use it
            if error_rate is not None:
                # Clamp between 0 and 1
                error_rate = max(0.0, min(1.0, error_rate))
                error_rate_simulation = error_rate
            else:
                # Read from request body
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                error_rate = data.get('error_rate', 0.0)
                # Clamp between 0 and 1
                error_rate = max(0.0, min(1.0, error_rate))
                error_rate_simulation = error_rate
            
            # Write to config file for clients to read
            self._write_simulation_config()
            
            print(f"[Dashboard] Setting error rate to {error_rate * 100:.1f}%")
            
            response = json.dumps({"success": True, "message": f"Error rate set to {error_rate * 100:.1f}%"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())
            
        except Exception as e:
            error_response = json.dumps({"success": False, "error": str(e)})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(error_response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def _serve_simulation_config(self):
        """Serve the simulation config file."""
        try:
            config_file = os.path.join(LOG_DIR, "simulation_config.json")
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(content))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content.encode())
            else:
                # Return default config if file doesn't exist
                default_config = {"tls_delay_ms": 0, "tcp_delay_ms": 0, "error_rate": 0.0}
                content = json.dumps(default_config)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(content))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content.encode())
        except Exception as e:
            error_response = json.dumps({"error": str(e)})
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(error_response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def _get_settings(self):
        """Get current delay and error rate settings."""
        try:
            # Read directly from simulation config file
            config_file = os.path.join(LOG_DIR, "simulation_config.json")
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    settings = {
                        "tls_delay_ms": config.get("tls_delay_ms", 0),
                        "tcp_delay_ms": config.get("tcp_delay_ms", 0),
                        "error_rate": config.get("error_rate", 0.0)
                    }
            else:
                # Fallback to defaults
                settings = {
                    "tls_delay_ms": 0,
                    "tcp_delay_ms": 0,
                    "error_rate": 0.0
                }
            
            response = json.dumps({"success": True, "settings": settings})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())
            
        except Exception as e:
            error_response = json.dumps({"success": False, "error": str(e)})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(error_response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def _clear_logs(self):
        """Clear all logs and reset network conditions from backend files."""
        try:
            # Clear session log
            if os.path.exists(SESSION_LOG_FILE):
                with open(SESSION_LOG_FILE, 'w') as f:
                    f.write('[]')
            
            # Clear manual log
            if os.path.exists(MANUAL_LOG_FILE):
                with open(MANUAL_LOG_FILE, 'w') as f:
                    f.write('[]')
            
            # Reset error rate to 0
            self._set_error_rate(error_rate=0.0)
            
            # Reset delays to 0
            self._reset_delays()
            
            response = json.dumps({"success": True, "message": "All logs and network conditions reset successfully"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())
            
        except Exception as e:
            error_response = json.dumps({"success": False, "error": str(e)})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(error_response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def _stop_auto(self):
        """Stop automatic client."""
        try:
            global auto_client_process
            
            # Write stop flag first (clean signal)
            try:
                with open(STOP_FLAG_FILE, 'w') as f:
                    json.dump({"stop": True}, f)
            except Exception:
                pass
            
            if auto_client_process and auto_client_process.poll() is None:
                # Try to terminate the process and all its children
                try:
                    if os.name == 'nt':
                        # On Windows, use taskkill to kill the process tree
                        subprocess.call(['taskkill', '/F', '/T', '/PID', str(auto_client_process.pid)])
                    else:
                        # On Unix-like systems, kill the process group
                        os.killpg(os.getpgid(auto_client_process.pid), signal.SIGTERM)
                    auto_client_process.wait(timeout=2)
                except:
                    # Force kill if graceful termination fails
                    try:
                        if os.name == 'nt':
                            subprocess.call(['taskkill', '/F', '/T', '/PID', str(auto_client_process.pid)])
                        else:
                            os.killpg(os.getpgid(auto_client_process.pid), signal.SIGKILL)
                    except:
                        pass
                auto_client_process = None
                message = "Auto client stopped successfully"
            else:
                message = "No auto client running"
            
            response = json.dumps({"success": True, "message": message})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())
            
        except Exception as e:
            error_response = json.dumps({"success": False, "error": str(e)})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(error_response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def _write_simulation_config(self):
        """Write simulation configuration to a file for clients to read."""
        try:
            config = {
                "tls_delay_ms": tls_delay_ms,
                "tcp_delay_ms": tcp_delay_ms,
                "error_rate": error_rate_simulation
            }
            
            config_file = os.path.join(PROJECT_ROOT, "logs", "simulation_config.json")
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
                
        except Exception as e:
            print(f"[Dashboard] Failed to write simulation config: {e}")
    
    def _kill_process_tree(self, pid):
        """Kill a process and all its children."""
        try:
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(pid)])
            else:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            pass

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
    print(f"[Dashboard] Reading session logs from: {SESSION_LOG_FILE}")
    print(f"[Dashboard] Reading manual logs from: {MANUAL_LOG_FILE}")
    print(f"[Dashboard] Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Dashboard] Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()
