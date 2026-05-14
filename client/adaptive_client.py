"""
Adaptive Client — Main orchestrator that ties all client components together.

Runs a loop of API requests, periodically re-probing network conditions,
using the decision engine + hysteresis controller to adaptively switch
between TLS and TCP protocols.

All request metrics are logged to logs/session_log.json for the dashboard.
"""

import os
import sys
import json
import time
import argparse
import random
import hashlib

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.network_prober import NetworkProber
from client.decision_engine import DecisionEngine
from client.hysteresis_controller import HysteresisController
from client.session_manager import SessionManager

API_KEY = "super_secret_key"

# ── Logging ────────────────────────────────────────────────────────

def get_log_path():
    """Get the path to the session log file."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(project_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return os.path.join(logs_dir, "session_log.json")


def load_logs(log_path):
    """Load existing logs or return empty list."""
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_log_entry(log_path, entry):
    """Append a log entry to the session log file."""
    logs = load_logs(log_path)
    logs.append(entry)
    with open(log_path, "w") as f:
        json.dump(logs, f, indent=2)


def clear_logs(log_path):
    """Clear the log file for a fresh session."""
    with open(log_path, "w") as f:
        json.dump([], f)


def get_stop_flag_path():
    """Get path to the stop flag file."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(project_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return os.path.join(logs_dir, "stop_flag.json")


def check_stop_flag():
    """Check if stop flag is set."""
    try:
        stop_file = get_stop_flag_path()
        if os.path.exists(stop_file):
            with open(stop_file, "r") as f:
                data = json.load(f)
                return data.get("stop", False)
    except Exception:
        pass
    return False


def clear_stop_flag():
    """Clear the stop flag."""
    try:
        stop_file = get_stop_flag_path()
        with open(stop_file, "w") as f:
            json.dump({"stop": False}, f)
    except Exception:
        pass


def set_stop_flag():
    """Set the stop flag."""
    try:
        stop_file = get_stop_flag_path()
        with open(stop_file, "w") as f:
            json.dump({"stop": True}, f)
    except Exception:
        pass

# ── ADD AUTHENTICATION ─────────────────────────────────────────────
def sign_request(payload: dict):
    payload_str = json.dumps(payload, sort_keys=True)
    signature = hashlib.sha256((payload_str + API_KEY).encode()).hexdigest()
    return signature

# ── Main Client Logic ─────────────────────────────────────────────

def run_adaptive_client(
    num_requests=50,
    tls_host="localhost",
    tls_port=5000,
    tcp_host="localhost",
    tcp_port=6000,
    switch_delay_at=25,
    low_delay=20.0,
    high_delay=180.0,
):
    """
    Run the adaptive client.
    
    The client will:
    1. Start with TLS (secure by default)
    2. Send API requests in a loop
    3. Every 5 requests, re-probe and evaluate protocol scores
    4. Use hysteresis to decide if switching is warranted
    5. At request #switch_delay_at, change server delays to simulate network change
    6. Log everything for the dashboard
    
    Args:
        num_requests:    Total number of requests to send
        tls_host/port:   TLS server address
        tcp_host/port:   TCP server address
        switch_delay_at: Request number at which to change network conditions
        low_delay:       Initial low delay in ms
        high_delay:      High delay applied after switch_delay_at
    """
    # Initialize components
    prober = NetworkProber(tls_host, tls_port, tcp_host, tcp_port)
    engine = DecisionEngine()
    hysteresis = HysteresisController(threshold_pct=15.0, required_consecutive=3)
    session = SessionManager(tls_host, tls_port, tcp_host, tcp_port)

    log_path = get_log_path()
    clear_logs(log_path)
    clear_stop_flag()

    # Cycle through different API actions
    actions = ["health", "data", "compute", "echo"]
    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 3
    last_connected_protocol = None

    print("=" * 70)
    print("  ADAPTIVE CLIENT -- Dual-Mode Protocol Selection System")
    print("=" * 70)
    print(f"  Requests to send : {num_requests}")
    print(f"  TLS Server       : https://{tls_host}:{tls_port}")
    print(f"  TCP Server       : tcp://{tcp_host}:{tcp_port}")
    print(f"  Delay switch at  : Request #{switch_delay_at}")
    print(f"  Low delay        : {low_delay}ms -> High delay: {high_delay}ms")
    print("=" * 70)

    # ── Initial Probe ──
    print("\n[1/3] Probing both servers...")
    probe_results = prober.probe_both()

    if not probe_results["TLS"]["success"]:
        print("[!] TLS server is not reachable. Make sure it's running.")
        print(f"    Error: {probe_results['TLS'].get('error', 'Unknown')}")
        return
    if not probe_results["TCP"]["success"]:
        print("[!] TCP server is not reachable. Make sure it's running.")
        print(f"    Error: {probe_results['TCP'].get('error', 'Unknown')}")
        return

    print(f"    TLS -> RTT: {probe_results['TLS']['rtt']:.1f}ms, "
          f"Handshake: {probe_results['TLS']['handshake_time']:.1f}ms")
    print(f"    TCP -> RTT: {probe_results['TCP']['rtt']:.1f}ms, "
          f"Handshake: {probe_results['TCP']['handshake_time']:.1f}ms")

    # ── Initial Evaluation ──
    print("\n[2/3] Evaluating initial protocol...")
    evaluation = engine.evaluate(probe_results["TLS"], probe_results["TCP"])
    decision = hysteresis.should_switch(evaluation)
    initial_protocol = hysteresis.get_current_protocol()
    print(f"    TLS Score: {evaluation['tls_score']:.2f}")
    print(f"    TCP Score: {evaluation['tcp_score']:.2f}")
    print(f"    Starting with: {initial_protocol}")

    # ── Connect ──
    print(f"\n[3/3] Connecting via {initial_protocol}...")
    try:
        session.connect(initial_protocol)
    except Exception as e:
        print(f"[!] Failed to connect: {e}")
        return

    print(f"\n{'-' * 70}")
    print(f"  Starting request loop... ({num_requests} requests)")
    print(f"{'-' * 70}\n")

    # ── Request Loop ──
    delay_switched = False

    for i in range(1, num_requests + 1):
        # Check stop flag
        if check_stop_flag():
            print(f"\n  [!] Stop requested at request #{i}. Terminating auto-run.")
            break

        # ── Simulate network change midway ──
        if i == switch_delay_at and not delay_switched:
            delay_switched = True
            print(f"\n  >> REQUEST #{i}: Simulating network degradation!")
            print(f"     TLS delay: {low_delay}ms -> {high_delay}ms")
            print(f"     TCP delay stays at: {low_delay}ms\n")

            # Change TLS server delay via its API
            try:
                import requests as req_lib
                req_lib.post(
                    f"https://{tls_host}:{tls_port}/api/set_delay",
                    json={"delay_ms": high_delay},
                    verify=False,
                    timeout=5,
                )
            except Exception:
                print("     [!] Could not set TLS delay dynamically")

        # Pick a random API action
        action = actions[i % len(actions)]
        payload = {"request_id": i,"message": f"Request #{i}","timestamp": time.time()}
        payload["signature"] = sign_request(payload) if action == "echo" else None

        # ── Send request ──
        current_protocol = hysteresis.get_current_protocol()
        try:
            start = time.perf_counter()
            response = session.send_request(action, payload)
            rtt = response.get("_rtt_ms", 0)
            payload_size = response.get("_payload_size", 0)
            status = response.get("status", "unknown")
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            print(f"  [{i:3d}] ERROR: {e} (consecutive: {consecutive_errors})")
            
            # Switch protocol after max consecutive errors
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                other_protocol = "TCP" if current_protocol == "TLS" else "TLS"
                print(f"  [!] Max consecutive errors reached. Emergency switch to {other_protocol}")
                try:
                    hysteresis.force_protocol(other_protocol)
                    session.switch_to(other_protocol)
                    consecutive_errors = 0
                except Exception as switch_err:
                    print(f"  [!] Emergency switch failed: {switch_err}")
            
            # Log the error with error status
            log_entry = {
                "request_id": i,
                "timestamp": time.time(),
                "protocol": current_protocol,
                "action": action,
                "rtt_ms": 0,
                "handshake_time_ms": 0,
                "payload_size": 0,
                "tls_score": evaluation["tls_score"],
                "tcp_score": evaluation["tcp_score"],
                "status": "error",
                "request_type": "AUTO",
                "tls_components": evaluation.get("tls_components", {}),
                "tcp_components": evaluation.get("tcp_components", {}),
            }
            save_log_entry(log_path, log_entry)
            
            # Try to reconnect
            try:
                session.connect(hysteresis.get_current_protocol())
                last_connected_protocol = None  # reset so handshake is logged after reconnect
            except Exception:
                pass
            continue

        # Determine if this is the first request after a switch
        is_new_connection = (current_protocol != last_connected_protocol)
        last_connected_protocol = current_protocol
        handshake_time = session._last_handshake_time.get(current_protocol, 0) if is_new_connection else 0

        # ── Log the request ──
        log_entry = {
            "request_id": i,
            "timestamp": time.time(),
            "protocol": current_protocol,
            "action": action,
            "rtt_ms": rtt,
            "handshake_time_ms": handshake_time,
            "payload_size": payload_size,
            "tls_score": evaluation["tls_score"],
            "tcp_score": evaluation["tcp_score"],
            "status": status,
            "request_type": "AUTO",
            "tls_components": evaluation.get("tls_components", {}),
            "tcp_components": evaluation.get("tcp_components", {}),
        }
        save_log_entry(log_path, log_entry)

        # Compact status line
        proto_icon = "[SECURE]" if current_protocol == "TLS" else "[FAST]"
        print(f"  [{i:3d}] {proto_icon} {current_protocol} | {action:8s} | "
              f"RTT: {rtt:7.1f}ms | Size: {payload_size:5d}B | "
              f"Scores: TLS={evaluation['tls_score']:.1f} TCP={evaluation['tcp_score']:.1f}")

        # ── Re-evaluate every 5 requests ──
        if i % 5 == 0:
            print(f"\n  {'.' * 50}")
            print(f"  Re-evaluating at request #{i}...")

            probe_results = prober.probe_both()

            if probe_results["TLS"]["success"] and probe_results["TCP"]["success"]:
                evaluation = engine.evaluate(probe_results["TLS"], probe_results["TCP"])
                decision = hysteresis.should_switch(evaluation)

                print(f"    TLS -> RTT: {probe_results['TLS']['rtt']:.1f}ms  |  "
                      f"TCP -> RTT: {probe_results['TCP']['rtt']:.1f}ms")
                print(f"    Scores: TLS={evaluation['tls_score']:.1f}  "
                      f"TCP={evaluation['tcp_score']:.1f}  |  "
                      f"Advantage: {evaluation['score_advantage']:.1f}%")
                print(f"    Hysteresis: {decision['reason']}")

                if decision["switch"]:
                    print(f"\n  >>> SWITCHING PROTOCOL: {decision['protocol']}")
                    try:
                        session.switch_to(decision["protocol"])
                        last_connected_protocol = None  # reset so handshake is logged
                    except Exception as e:
                        print(f"  [!] Switch failed: {e}")

            print(f"  {'.' * 50}\n")

        # Small pause between requests
        time.sleep(0.3)

    # ── Cleanup ──
    clear_stop_flag()
    session.close_all()

    print(f"\n{'=' * 70}")
    print(f"  SESSION COMPLETE -- {num_requests} requests sent")
    print(f"  Protocol switches: {len(hysteresis.get_switch_history())}")
    for sw in hysteresis.get_switch_history():
        print(f"    * {sw['from']} -> {sw['to']} (advantage: {sw['advantage']:.1f}%)")
    print(f"  Log file: {log_path}")
    print(f"  Dashboard: http://localhost:8080")
    print(f"{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(
        description="Adaptive Client -- Dual-Mode Protocol Selection"
    )
    parser.add_argument("--requests", type=int, default=50,
                        help="Number of requests to send (default: 50)")
    parser.add_argument("--count", type=int, default=50,
                        help="Alias for --requests (default: 50)")
    parser.add_argument("--tls-host", default="localhost",
                        help="TLS server host (default: localhost)")
    parser.add_argument("--tls-port", type=int, default=5000,
                        help="TLS server port (default: 5000)")
    parser.add_argument("--tcp-host", default="localhost",
                        help="TCP server host (default: localhost)")
    parser.add_argument("--tcp-port", type=int, default=6000,
                        help="TCP server port (default: 6000)")
    parser.add_argument("--switch-at", type=int, default=25,
                        help="Request # at which to simulate network change (default: 25)")
    parser.add_argument("--low-delay", type=float, default=20.0,
                        help="Initial low delay in ms (default: 20)")
    parser.add_argument("--high-delay", type=float, default=180.0,
                        help="High delay after switch (default: 180)")
    args = parser.parse_args()

    # Use --count if provided, otherwise use --requests
    num_requests = args.count if args.count != 50 else args.requests
    
    run_adaptive_client(
        num_requests=num_requests,
        tls_host=args.tls_host,
        tls_port=args.tls_port,
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        switch_delay_at=args.switch_at,
        low_delay=args.low_delay,
        high_delay=args.high_delay,
    )


if __name__ == "__main__":
    main()
