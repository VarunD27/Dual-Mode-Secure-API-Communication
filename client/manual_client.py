#!/usr/bin/env python3
"""
Manual API Client - Interactive Request Testing
Allows manual sending of requests to demonstrate API communication
"""

import os
import sys
import time
import json
import uuid
import logging
from typing import Dict, Any, Optional

# Ensure imports work when run from project root or client directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.session_manager import SessionManager
from client.decision_engine import DecisionEngine
from client.hysteresis_controller import HysteresisController
from client.network_prober import NetworkProber

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)

class ManualClient:
    """
    Interactive client for manual API request testing with adaptive protocol selection.
    """
    
    def __init__(self):
        self.session = SessionManager(enable_fallback=True)
        self.engine = DecisionEngine()
        self.hysteresis = HysteresisController()
        self.prober = NetworkProber()
        self.request_count = 0
        self.log_file = os.path.join(PROJECT_ROOT, "logs", "manual_session_log.json")
        self._last_evaluation = None
        
        # Initialize log file
        self._init_log()
    
    def _init_log(self):
        """Initialize the log file."""
        try:
            with open(self.log_file, 'w') as f:
                json.dump([], f)
        except Exception as e:
            logging.error(f"Failed to initialize log file: {e}")
    
    def _log_request(self, protocol: str, action: str, response: Dict[str, Any]):
        """Log request details to file."""
        # Track if this is the first request after protocol switch
        is_first_request = False
        if not hasattr(self, '_last_logged_protocol'):
            self._last_logged_protocol = None
            
        if self._last_logged_protocol != protocol:
            self._last_logged_protocol = protocol
            is_first_request = True
        
        # Get handshake time only on first request after protocol switch
        handshake_time = 0
        if is_first_request and hasattr(self.session, '_last_handshake_time'):
            handshake_time = self.session._last_handshake_time.get(protocol, 0)
        
        # Use evaluated scores if available
        tls_score = 0
        tcp_score = 0
        tls_components = {}
        tcp_components = {}
        if self._last_evaluation:
            tls_score = self._last_evaluation.get("tls_score", 0)
            tcp_score = self._last_evaluation.get("tcp_score", 0)
            tls_components = self._last_evaluation.get("tls_components", {})
            tcp_components = self._last_evaluation.get("tcp_components", {})
        
        log_entry = {
            "request_id": self.request_count,
            "timestamp": time.time(),
            "protocol": protocol,
            "action": action,
            "rtt_ms": response.get("_rtt_ms", 0),
            "handshake_time_ms": handshake_time,
            "payload_size": response.get("_payload_size", 0),
            "status": response.get("status", "unknown"),
            "tls_score": tls_score,
            "tcp_score": tcp_score,
            "request_type": "MANUAL",
            "tls_components": tls_components,
            "tcp_components": tcp_components,
        }
        
        try:
            logs = []
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            logs.append(log_entry)
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to log request: {e}")
    
    def probe_and_evaluate(self):
        """Probe both protocols and evaluate the best choice."""
        print("\n🔍 Probing both protocols...")
        
        tls_metrics = self.prober.probe_tls()
        tcp_metrics = self.prober.probe_tcp()
        
        print(f"   TLS → RTT: {tls_metrics.get('rtt', 0):.1f}ms, Handshake: {tls_metrics.get('handshake_time', 0):.1f}ms")
        print(f"   TCP → RTT: {tcp_metrics.get('rtt', 0):.1f}ms, Handshake: {tcp_metrics.get('handshake_time', 0):.1f}ms")
        
        # Evaluate with decision engine
        evaluation = self.engine.evaluate(tls_metrics, tcp_metrics)
        self._last_evaluation = evaluation
        print(f"   Scores: TLS={evaluation['tls_score']:.1f}, TCP={evaluation['tcp_score']:.1f}")
        print(f"   Advantage: {evaluation['score_advantage']:.1f}%")
        
        # Apply hysteresis
        hysteresis_result = self.hysteresis.should_switch(evaluation)
        
        print(f"   Decision: {hysteresis_result['protocol']} ({hysteresis_result['reason']})")
        
        return hysteresis_result
    
    def connect_initial(self):
        """Initial connection setup."""
        print("🚀 Setting up initial connection...")
        
        # Probe and evaluate
        result = self.probe_and_evaluate()
        protocol = result['protocol']
        
        # Connect to chosen protocol
        try:
            self.session.connect(protocol)
            print(f"✅ Connected to {protocol} server")
            return True
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            return False
    
    def send_request(self, action: str, payload: Optional[Dict] = None):
        """Send a manual request."""
        self.request_count += 1
        
        print(f"\n📤 [Request #{self.request_count}] Sending {action} request...")
        
        try:
            # Check if we should re-evaluate (every 3 requests)
            if self.request_count % 3 == 1:  # Every 3 requests
                print("🔄 Re-evaluating protocol choice...")
                result = self.probe_and_evaluate()
                if result['switch']:
                    self.session.switch_to(result['protocol'])
                    print(f"🔄 Switched to {result['protocol']}")
            
            # Send the request
            start_time = time.time()
            response = self.session.send_request(action, payload)
            elapsed = (time.time() - start_time) * 1000
            
            # Display results
            print(f"✅ Response received in {elapsed:.1f}ms")
            print(f"   Protocol: {self.session.active_protocol}")
            print(f"   Status: {response.get('status', 'unknown')}")
            print(f"   Payload Size: {response.get('_payload_size', 0)} bytes")
            
            if response.get('status') == 'ok':
                data = response.get('data', {})
                if isinstance(data, dict):
                    print(f"   Data: {json.dumps(data, indent=6)[:100]}...")
                else:
                    print(f"   Data: {str(data)[:100]}...")
            else:
                print(f"   Error: {response.get('message', 'Unknown error')}")
            
            # Log the request
            self._log_request(self.session.active_protocol, action, response)
            
        except Exception as e:
            print(f"❌ Request failed: {e}")
    
    def show_menu(self):
        """Display the interactive menu."""
        print("\n" + "="*60)
        print("🎮 MANUAL API CLIENT - Interactive Menu")
        print("="*60)
        print("Available Actions:")
        print("  1. health   - Check server health")
        print("  2. data     - Get sample data")
        print("  3. echo     - Echo test message")
        print("  4. compute  - Perform calculation")
        print("  5. probe    - Probe both protocols")
        print("  6. switch   - Manual protocol switch")
        print("  7. status   - Show current status")
        print("  8. help     - Show this menu")
        print("  9. quit     - Exit client")
        print("-"*60)
    
    def manual_switch(self):
        """Manual protocol switching."""
        current = self.session.active_protocol
        new_protocol = "TCP" if current == "TLS" else "TLS"
        
        print(f"🔄 Manually switching from {current} to {new_protocol}...")
        try:
            self.session.switch_to(new_protocol)
            print(f"✅ Switched to {new_protocol}")
        except Exception as e:
            print(f"❌ Switch failed: {e}")
    
    def show_status(self):
        """Show current client status."""
        print("\n📊 Current Status:")
        print(f"   Active Protocol: {self.session.active_protocol}")
        print(f"   Requests Sent: {self.request_count}")
        print(f"   TLS URL: {self.session.tls_url}")
        print(f"   TCP Endpoint: {self.session.tcp_host}:{self.session.tcp_port}")
        print(f"   Log File: {self.log_file}")
        
        # Show recent hysteresis state
        print(f"   Hysteresis State:")
        print(f"     Current: {self.hysteresis.current_protocol}")
        print(f"     Candidate: {self.hysteresis.candidate_protocol}")
        print(f"     Consecutive Count: {self.hysteresis.consecutive_count}")
        print(f"     Switch History: {len(self.hysteresis.switch_history)} switches")
    
    def run(self):
        """Run the interactive client."""
        print("🎯 Starting Manual API Client...")
        
        # Initial connection
        if not self.connect_initial():
            print("❌ Failed to establish initial connection")
            return
        
        # Show menu and start interactive loop
        self.show_menu()
        
        while True:
            try:
                choice = input("\nEnter choice (1-9): ").strip().lower()
                
                if choice in ['1', 'health']:
                    self.send_request('health')
                
                elif choice in ['2', 'data']:
                    self.send_request('data')
                
                elif choice in ['3', 'echo']:
                    message = input("Enter message to echo (default: 'Hello World'): ").strip()
                    payload = {"message": message} if message else {"message": "Hello World"}
                    self.send_request('echo', payload)
                
                elif choice in ['4', 'compute']:
                    numbers = input("Enter numbers (comma-separated, default: '1,2,3'): ").strip()
                    try:
                        nums = [int(x.strip()) for x in numbers.split(',') if x.strip()]
                        if not nums:
                            nums = [1, 2, 3]
                        payload = {"numbers": nums}
                        self.send_request('compute', payload)
                    except ValueError:
                        print("❌ Invalid numbers format")
                
                elif choice in ['5', 'probe']:
                    self.probe_and_evaluate()
                
                elif choice in ['6', 'switch']:
                    self.manual_switch()
                
                elif choice in ['7', 'status']:
                    self.show_status()
                
                elif choice in ['8', 'help', 'menu']:
                    self.show_menu()
                
                elif choice in ['9', 'quit', 'exit', 'q']:
                    print("\n👋 Goodbye!")
                    break
                
                else:
                    print("❌ Invalid choice. Please enter 1-9.")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


def main():
    """Main entry point."""
    print("🎮 Manual API Client for Adaptive Protocol Testing")
    print("="*60)
    print("This client allows you to manually send API requests")
    print("and observe the adaptive protocol selection in action.")
    print("="*60)
    
    client = ManualClient()
    client.run()


if __name__ == "__main__":
    main()
