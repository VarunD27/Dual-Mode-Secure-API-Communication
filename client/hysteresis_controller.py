"""
Hysteresis Controller — Prevents rapid oscillation between protocols.

Rules:
  1. Candidate protocol must show >15% score advantage
  2. Must hold that advantage for 3 consecutive checks
  3. Switching only at safe points (after request completion)
"""


class HysteresisController:
    """
    Controls protocol switching with hysteresis to ensure stability.
    Prevents rapid oscillation under unstable network conditions.
    """

    def __init__(self, threshold_pct=15.0, required_consecutive=3):
        """
        Args:
            threshold_pct:        Minimum score advantage (%) to consider switching (default 15%)
            required_consecutive: Number of consecutive checks the candidate must win (default 3)
        """
        self.threshold_pct = threshold_pct
        self.required_consecutive = required_consecutive

        # Internal state
        self.current_protocol = "TLS"  # Start with TLS (secure by default)
        self.candidate_protocol = None
        self.consecutive_count = 0
        self.switch_history = []

    def should_switch(self, evaluation: dict) -> dict:
        """
        Given the decision engine's evaluation, determine if we should switch.
        
        Args:
            evaluation: dict from DecisionEngine.evaluate() with keys:
              - recommended: "TLS" or "TCP"
              - score_advantage: percentage advantage
              - tls_score, tcp_score
              
        Returns:
            dict with:
              - switch: bool (True if protocol should change)
              - protocol: current/new protocol after decision
              - reason: explanation string
        """
        recommended = evaluation["recommended"]
        advantage = evaluation["score_advantage"]

        # Case 1: Recommended protocol is the same as current → reset candidate
        if recommended == self.current_protocol:
            self.candidate_protocol = None
            self.consecutive_count = 0
            return {
                "switch": False,
                "protocol": self.current_protocol,
                "reason": f"Current protocol ({self.current_protocol}) is still optimal",
                "consecutive_count": 0,
            }

        # Case 2: Different protocol recommended but advantage below threshold
        if advantage < self.threshold_pct:
            self.candidate_protocol = None
            self.consecutive_count = 0
            return {
                "switch": False,
                "protocol": self.current_protocol,
                "reason": (
                    f"{recommended} is better by only {advantage:.1f}% "
                    f"(need >{self.threshold_pct}%)"
                ),
                "consecutive_count": 0,
            }

        # Case 3: Different protocol with sufficient advantage
        if self.candidate_protocol == recommended:
            self.consecutive_count += 1
        else:
            # New candidate
            self.candidate_protocol = recommended
            self.consecutive_count = 1

        # Check if we've reached the required consecutive count
        if self.consecutive_count >= self.required_consecutive:
            old_protocol = self.current_protocol
            self.current_protocol = recommended
            self.candidate_protocol = None
            self.consecutive_count = 0
            self.switch_history.append({
                "from": old_protocol,
                "to": recommended,
                "advantage": advantage,
            })
            return {
                "switch": True,
                "protocol": self.current_protocol,
                "reason": (
                    f"Switched {old_protocol} -> {recommended} "
                    f"(advantage: {advantage:.1f}%, held for "
                    f"{self.required_consecutive} consecutive checks)"
                ),
                "consecutive_count": self.required_consecutive,
            }

        # Still accumulating consecutive checks
        return {
            "switch": False,
            "protocol": self.current_protocol,
            "reason": (
                f"{recommended} leads by {advantage:.1f}% "
                f"({self.consecutive_count}/{self.required_consecutive} checks)"
            ),
            "consecutive_count": self.consecutive_count,
        }

    def get_current_protocol(self) -> str:
        """Return the current active protocol."""
        return self.current_protocol

    def get_switch_history(self) -> list:
        """Return the full switch history."""
        return self.switch_history

    def force_protocol(self, protocol: str):
        """Force a specific protocol (for testing)."""
        self.current_protocol = protocol
        self.candidate_protocol = None
        self.consecutive_count = 0


# Quick standalone test
if __name__ == "__main__":
    controller = HysteresisController()
    print(f"Starting protocol: {controller.get_current_protocol()}")

    # Simulate 5 evaluations where TCP is better by 25%
    for i in range(5):
        eval_result = {
            "recommended": "TCP",
            "score_advantage": 25.0,
            "tls_score": 100.0,
            "tcp_score": 75.0,
        }
        decision = controller.should_switch(eval_result)
        print(f"Check {i+1}: switch={decision['switch']}, "
              f"protocol={decision['protocol']}, reason={decision['reason']}")
