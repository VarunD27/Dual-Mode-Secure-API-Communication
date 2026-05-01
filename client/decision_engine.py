"""
Decision Engine — Enhanced multi-metric scoring model for protocol selection.
Computes a cost score for each protocol:
  Score = w1 × latency + w2 × handshake_time + w3 × payload_cost + w4 × security_score + w5 × reliability_score
Lower score = preferred protocol.

Enhanced features:
- Security scoring (TLS gets higher security score)
- Reliability scoring (based on error rates and packet loss)
- Adaptive weighting based on network conditions
- Protocol-specific optimizations
"""

import math
from typing import Dict, List, Tuple


class DecisionEngine:
    """
    Enhanced scoring model that evaluates both protocols and recommends
    the one with the lowest cost score using multiple metrics.
    """

    def __init__(self, w_latency=0.4, w_handshake=0.3, w_payload=0.1, w_security=0.1, w_reliability=0.1):
        """
        Initialize weights for the enhanced scoring formula.
        
        Args:
            w_latency:    Weight for RTT latency (default 0.4)
            w_handshake:   Weight for handshake time (default 0.2)
            w_payload:     Weight for payload cost (default 0.1)
            w_security:    Weight for security score (default 0.2)
            w_reliability: Weight for reliability score (default 0.1)
        """
        self.w_latency = w_latency
        self.w_handshake = w_handshake
        self.w_payload = w_payload
        self.w_security = w_security
        self.w_reliability = w_reliability
        
        # Protocol-specific security scores (lower is better for cost, but we'll invert)
        self.security_scores = {
            "TLS": 0.1,   # Very secure (low cost)
            "TCP": 0.3    # Less secure (higher cost)
        }
        
        # Track historical performance for reliability scoring
        self.performance_history = {"TLS": [], "TCP": []}
        self.max_history = 20  # Keep last 20 measurements

    def compute_security_cost(self, protocol: str) -> float:
        """
        Compute security cost (lower is more secure).
        """
        if protocol == "TLS":
            return 1.0  # Low cost (high security)
        elif protocol == "TCP":
            return 5.0  # Higher cost (less secure than TLS)
        else:
            return 10.0  # High cost (unknown protocol)
    
    def compute_reliability_cost(self, protocol: str, error_rate: float = 0.0) -> float:
        """
        Compute reliability cost based on error rates and historical performance.
        
        Args:
            protocol: "TLS" or "TCP"
            error_rate: Current error rate (0.0 to 1.0)
        """
        # Base cost from error rate
        error_cost = error_rate * 1000  # Scale up error impact
        
        # Historical volatility (if available)
        history = self.performance_history.get(protocol, [])
        if len(history) >= 3:
            # Calculate coefficient of variation (std/mean)
            recent_times = [h["rtt"] for h in history[-10:]]
            if recent_times:
                mean_time = sum(recent_times) / len(recent_times)
                if mean_time > 0:
                    variance = sum((t - mean_time) ** 2 for t in recent_times) / len(recent_times)
                    std_dev = math.sqrt(variance)
                    cv = std_dev / mean_time
                    volatility_cost = cv * 50  # Scale volatility impact
                else:
                    volatility_cost = 0
            else:
                volatility_cost = 0
        else:
            volatility_cost = 0
        
        return error_cost + volatility_cost
    
    def update_performance_history(self, protocol: str, metrics: dict):
        """
        Update performance history for reliability calculations.
        """
        history = self.performance_history[protocol]
        history.append({
            "timestamp": metrics.get("timestamp", 0),
            "rtt": metrics.get("rtt", 0),
            "success": metrics.get("success", True)
        })
        
        # Keep only recent history
        if len(history) > self.max_history:
            self.performance_history[protocol] = history[-self.max_history:]

    def compute_score(self, metrics: dict, protocol: str) -> float:
        """
        Compute the enhanced cost score for a protocol's metrics.
        
        Args:
            metrics: dict with keys:
              - rtt: round-trip time in ms
              - handshake_time: handshake duration in ms
              - payload_size: response payload size in bytes
              - success: whether the request succeeded
              - error_rate: current error rate (optional)
            protocol: "TLS" or "TCP"
        
        Returns:
            Cost score (lower is better)
        """
        rtt = metrics.get("rtt", 9999.0)
        handshake = metrics.get("handshake_time", 9999.0)
        # Normalize payload size (divide by 1000 to bring into similar scale as ms)
        payload_cost = metrics.get("payload_size", 0) / 1000.0
        success = metrics.get("success", True)
        
        # Load current simulation error rate if not provided in metrics
        error_rate = metrics.get("error_rate")
        if error_rate is None:
            try:
                import json
                import os
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                config_file = os.path.join(project_root, "logs", "simulation_config.json")
                if os.path.exists(config_file):
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                        error_rate = config.get("error_rate", 0.0)
                else:
                    error_rate = 0.0
            except Exception:
                error_rate = 0.0
        
        # If request failed, apply heavy penalty
        if not success:
            rtt = 9999.0
            error_rate = 1.0
        
        # Calculate individual components
        latency_cost = self.w_latency * rtt
        handshake_cost = self.w_handshake * handshake
        payload_cost_weighted = self.w_payload * payload_cost
        security_cost = self.w_security * self.compute_security_cost(protocol)
        reliability_cost = self.w_reliability * self.compute_reliability_cost(protocol, error_rate)
        
        # Total score
        score = (
            latency_cost +
            handshake_cost +
            payload_cost_weighted +
            security_cost +
            reliability_cost
        )
        
        return round(score, 3)

    def evaluate(self, tls_metrics: dict, tcp_metrics: dict) -> dict:
        """
        Evaluate both protocols and return enhanced scores + recommendation.
        
        Args:
            tls_metrics: Probe results for TLS
            tcp_metrics: Probe results for TCP
            
        Returns:
            dict with tls_score, tcp_score, recommended protocol,
            score_advantage percentage, and detailed breakdown.
        """
        # Update performance history
        self.update_performance_history("TLS", tls_metrics)
        self.update_performance_history("TCP", tcp_metrics)
        
        # Compute enhanced scores
        tls_score = self.compute_score(tls_metrics, "TLS")
        tcp_score = self.compute_score(tcp_metrics, "TCP")

        # Determine recommendation
        if tls_score <= tcp_score:
            recommended = "TLS"
            advantage = ((tcp_score - tls_score) / tcp_score * 100) if tcp_score > 0 else 0
        else:
            recommended = "TCP"
            advantage = ((tls_score - tcp_score) / tls_score * 100) if tls_score > 0 else 0

        # Calculate score components for debugging
        tls_components = self._get_score_components(tls_metrics, "TLS")
        tcp_components = self._get_score_components(tcp_metrics, "TCP")

        return {
            "tls_score": tls_score,
            "tcp_score": tcp_score,
            "recommended": recommended,
            "score_advantage": round(advantage, 2),
            "tls_components": tls_components,
            "tcp_components": tcp_components,
        }
    
    def _get_score_components(self, metrics: dict, protocol: str) -> dict:
        """Get detailed score breakdown for analysis."""
        rtt = metrics.get("rtt", 0)
        handshake = metrics.get("handshake_time", 0)
        payload_cost = metrics.get("payload_size", 0) / 1000.0
        error_rate = 1.0 - (metrics.get("success_rate", 1.0) if metrics.get("success", True) else 0.0)
        
        return {
            "latency_cost": round(self.w_latency * rtt, 2),
            "handshake_cost": round(self.w_handshake * handshake, 2),
            "payload_cost": round(self.w_payload * payload_cost, 2),
            "security_cost": round(self.w_security * self.compute_security_cost(protocol), 2),
            "reliability_cost": round(self.w_reliability * self.compute_reliability_cost(protocol, error_rate), 2),
            "raw_metrics": {
                "rtt": rtt,
                "handshake": handshake,
                "payload_size": metrics.get("payload_size", 0),
                "error_rate": error_rate
            }
        }


# Quick standalone test
if __name__ == "__main__":
    engine = DecisionEngine()

    # Simulate: TLS has higher latency, TCP is faster
    tls = {"rtt": 85.0, "handshake_time": 120.0, "payload_size": 512, "success": True}
    tcp = {"rtt": 30.0, "handshake_time": 15.0, "payload_size": 480, "success": True}

    result = engine.evaluate(tls, tcp)
    print(f"TLS Score: {result['tls_score']}")
    print(f"TCP Score: {result['tcp_score']}")
    print(f"Recommended: {result['recommended']}")
    print(f"Score Advantage: {result['score_advantage']}%")
    print("\nTLS Components:")
    for comp, value in result['tls_components'].items():
        print(f"  {comp}: {value}")
    print("\nTCP Components:")
    for comp, value in result['tcp_components'].items():
        print(f"  {comp}: {value}")
