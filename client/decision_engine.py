"""
Decision Engine — NORMALIZED multi-metric scoring model.

All metrics are normalized to 0–1 range.
Lower score = better protocol.
"""

import math
from typing import Dict


class DecisionEngine:
    def __init__(self):
        # ✅ Balanced weights (sum = 1)
        self.w_latency = 0.30
        self.w_handshake = 0.20
        self.w_payload = 0.10
        self.w_security = 0.25
        self.w_reliability = 0.15

        # For reliability tracking
        self.performance_history = {"TLS": [], "TCP": []}
        self.max_history = 20

        # ✅ Normalization bounds (VERY IMPORTANT)
        self.MAX_RTT = 3000.0
        self.MAX_HANDSHAKE = 3000.0
        self.MAX_PAYLOAD = 2000.0

    # -------------------------------
    # NORMALIZATION FUNCTION
    # -------------------------------
    def _normalize(self, value, max_value):
        return min(value / max_value, 1.0)

    # -------------------------------
    # SECURITY (normalized cost)
    # -------------------------------
    def compute_security_cost(self, protocol):
        if protocol == "TLS":
            return 0.2   # better
        elif protocol == "TCP":
            return 0.6   # worse
        return 1.0

    # -------------------------------
    # RELIABILITY (normalized)
    # -------------------------------
    def compute_reliability_cost(self, protocol, error_rate=0.0):
        # error_rate already 0–1 → perfect normalization
        return error_rate

    # -------------------------------
    # PERFORMANCE HISTORY
    # -------------------------------
    def update_performance_history(self, protocol, metrics):
        history = self.performance_history[protocol]
        history.append({
            "rtt": metrics.get("rtt", 0),
            "success": metrics.get("success", True)
        })

        if len(history) > self.max_history:
            self.performance_history[protocol] = history[-self.max_history:]

    # -------------------------------
    # MAIN SCORING FUNCTION
    # -------------------------------
    def compute_score(self, metrics, protocol):
        rtt = metrics.get("rtt", 9999.0)
        handshake = metrics.get("handshake_time", 9999.0)
        payload = metrics.get("payload_size", 0)
        success = metrics.get("success", True)

        error_rate = metrics.get("error_rate", 0.0)

        if not success:
            error_rate = 1.0

        # ✅ NORMALIZED VALUES
        latency_norm = self._normalize(rtt, self.MAX_RTT)
        handshake_norm = self._normalize(handshake, self.MAX_HANDSHAKE)
        payload_norm = self._normalize(payload, self.MAX_PAYLOAD)
        # Treat reliability as a cost: higher error_rate -> worse (higher) score
        reliability_norm = error_rate
        security_norm = self.compute_security_cost(protocol)

        # ✅ FINAL SCORE (0–1 range)
        score = (
            self.w_latency * latency_norm +
            self.w_handshake * handshake_norm +
            self.w_payload * payload_norm +
            self.w_security * security_norm +
            self.w_reliability * reliability_norm
        )

        return round(score, 4)

    # -------------------------------
    # EVALUATION
    # -------------------------------
    def evaluate(self, tls_metrics, tcp_metrics):
        self.update_performance_history("TLS", tls_metrics)
        self.update_performance_history("TCP", tcp_metrics)

        tls_score = self.compute_score(tls_metrics, "TLS")
        tcp_score = self.compute_score(tcp_metrics, "TCP")

        if tls_score <= tcp_score:
            recommended = "TLS"
        else:
            recommended = "TCP"

        # ✅ FIXED advantage (no weird % explosion)
        advantage = abs(tls_score - tcp_score) * 100

        return {
            "tls_score": tls_score,
            "tcp_score": tcp_score,
            "recommended": recommended,
            "score_advantage": round(advantage, 2),
            "tls_components": self._get_components(tls_metrics, "TLS"),
            "tcp_components": self._get_components(tcp_metrics, "TCP"),
        }

    # -------------------------------
    # DEBUG COMPONENTS
    # -------------------------------
    def _get_components(self, metrics, protocol):
        rtt = metrics.get("rtt", 0)
        handshake = metrics.get("handshake_time", 0)
        payload = metrics.get("payload_size", 0)
        error_rate = metrics.get("error_rate", 0.0)

        latency_norm = self._normalize(rtt, self.MAX_RTT)
        handshake_norm = self._normalize(handshake, self.MAX_HANDSHAKE)
        payload_norm = self._normalize(payload, self.MAX_PAYLOAD)
        # Reliability is a cost contribution (error_rate 0..1)
        reliability_norm = error_rate
        security_norm = self.compute_security_cost(protocol)

        # ✅ Return WEIGHTED contributions that sum to the total score
        return {
            "normalized": {
                "latency": round(self.w_latency * latency_norm, 4),
                "handshake": round(self.w_handshake * handshake_norm, 4),
                "payload": round(self.w_payload * payload_norm, 4),
                "security": round(self.w_security * security_norm, 4),
                "reliability": round(self.w_reliability * reliability_norm, 4)
            }
        }