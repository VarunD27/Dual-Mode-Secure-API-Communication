"""
Decision Engine — Multi-metric scoring model for protocol selection.
Computes a cost score for each protocol:
  Score = w1 × latency + w2 × handshake_time + w3 × payload_cost
Lower score = preferred protocol.
"""


class DecisionEngine:
    """
    Scoring model that evaluates both protocols and recommends
    the one with the lowest cost score.
    """

    def __init__(self, w_latency=0.5, w_handshake=0.3, w_payload=0.2):
        """
        Initialize weights for the scoring formula.
        
        Args:
            w_latency:   Weight for RTT latency (default 0.5)
            w_handshake: Weight for handshake time (default 0.3)
            w_payload:   Weight for payload cost (default 0.2)
        """
        self.w_latency = w_latency
        self.w_handshake = w_handshake
        self.w_payload = w_payload

    def compute_score(self, metrics: dict) -> float:
        """
        Compute the cost score for a single protocol's metrics.
        
        Args:
            metrics: dict with keys:
              - rtt: round-trip time in ms
              - handshake_time: handshake duration in ms
              - payload_size: response payload size in bytes
        
        Returns:
            Cost score (lower is better)
        """
        rtt = metrics.get("rtt", 9999.0)
        handshake = metrics.get("handshake_time", 9999.0)
        # Normalize payload size (divide by 1000 to bring into similar scale as ms)
        payload_cost = metrics.get("payload_size", 0) / 1000.0

        score = (
            self.w_latency * rtt
            + self.w_handshake * handshake
            + self.w_payload * payload_cost
        )
        return round(score, 3)

    def evaluate(self, tls_metrics: dict, tcp_metrics: dict) -> dict:
        """
        Evaluate both protocols and return scores + recommendation.
        
        Args:
            tls_metrics: Probe results for TLS
            tcp_metrics: Probe results for TCP
            
        Returns:
            dict with tls_score, tcp_score, recommended protocol,
            and score_advantage percentage.
        """
        tls_score = self.compute_score(tls_metrics)
        tcp_score = self.compute_score(tcp_metrics)

        # Determine recommendation
        if tls_score <= tcp_score:
            recommended = "TLS"
            advantage = ((tcp_score - tls_score) / tcp_score * 100) if tcp_score > 0 else 0
        else:
            recommended = "TCP"
            advantage = ((tls_score - tcp_score) / tls_score * 100) if tls_score > 0 else 0

        return {
            "tls_score": tls_score,
            "tcp_score": tcp_score,
            "recommended": recommended,
            "score_advantage": round(advantage, 2),
        }


# Quick standalone test
if __name__ == "__main__":
    engine = DecisionEngine()

    # Simulate: TLS has higher latency, TCP is faster
    tls = {"rtt": 85.0, "handshake_time": 120.0, "payload_size": 512}
    tcp = {"rtt": 30.0, "handshake_time": 15.0, "payload_size": 480}

    result = engine.evaluate(tls, tcp)
    print(f"TLS Score: {result['tls_score']}")
    print(f"TCP Score: {result['tcp_score']}")
    print(f"Recommended: {result['recommended']}")
    print(f"Score Advantage: {result['score_advantage']}%")
