"""
Shared API logic used by both TLS and TCP servers.
Provides identical business logic regardless of transport protocol.
"""

import json
import time
import random


# Simulated data store
SAMPLE_DATA = {
    "users": [
        {"id": 1, "name": "Alice", "role": "admin", "status": "active"},
        {"id": 2, "name": "Bob", "role": "user", "status": "active"},
        {"id": 3, "name": "Charlie", "role": "user", "status": "inactive"},
        {"id": 4, "name": "Diana", "role": "moderator", "status": "active"},
        {"id": 5, "name": "Eve", "role": "user", "status": "active"},
    ],
    "metadata": {
        "version": "1.0",
        "server": "Dual-Mode Adaptive API",
        "timestamp": None,  # Filled at runtime
    },
}


def handle_request(action: str, payload: dict = None) -> dict:
    """
    Process an API request and return a response dict.
    
    Supported actions:
      - "health"  → health check
      - "data"    → return sample data
      - "echo"    → echo back the payload
      - "compute" → simulate a small computation
    """
    timestamp = time.time()

    if action == "health":
        return {
            "status": "ok",
            "timestamp": timestamp,
            "uptime": time.monotonic(),
        }

    elif action == "data":
        data = SAMPLE_DATA.copy()
        data["metadata"] = {**data["metadata"], "timestamp": timestamp}
        return {
            "status": "ok",
            "data": data,
            "timestamp": timestamp,
        }

    elif action == "echo":
        return {
            "status": "ok",
            "echo": payload or {},
            "timestamp": timestamp,
        }

    elif action == "compute":
        # Simulate some CPU work
        result = sum(random.randint(1, 100) for _ in range(100))
        return {
            "status": "ok",
            "result": result,
            "timestamp": timestamp,
        }

    else:
        return {
            "status": "error",
            "message": f"Unknown action: {action}",
            "timestamp": timestamp,
        }


def inject_delay(delay_ms: float):
    """Inject artificial network delay in milliseconds."""
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
