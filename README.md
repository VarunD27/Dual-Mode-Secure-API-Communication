# Dual-Mode Secure API Communication with Multi-Metric Driven Protocol Selection

**NPS Lab 6th Sem — RV College of Engineering, Bengaluru**
**Team:** Varun Dhandharia (1RV23CS279) & Sridula O S (1RV23CS303)

---

## Overview

This project implements an **Adaptive Session-Based Protocol Selection System** that dynamically chooses between:

- **Secure Mode (TLS)** — Flask HTTPS server with TLS 1.3 on port 5000
- **Fast Mode (TCP)** — Custom raw TCP server with AES-256-GCM encryption, nonce/timestamp replay protection, and simplified HELLO-ACK handshake on port 6000

A **5-factor decision engine** scores both protocols using latency, handshake time, payload size, security cost, and reliability cost. A **hysteresis controller** prevents rapid oscillation by requiring a candidate protocol to maintain a >15% score advantage for 3 consecutive checks before switching.

---

## Prerequisites

- **Python 3.10+** (tested with Python 3.12)
- **pip** (comes with Python)
- **A web browser** (Chrome / Edge / Firefox)

---

## Quick Start (Step by Step)

### 1. Install Python Dependencies

Open **PowerShell** or **Command Prompt** and navigate to the project folder:

```powershell
cd "c:\Users\varun\Desktop\NPS Lab el"
pip install -r requirements.txt
```

### 2. Generate TLS Certificates

```powershell
python generate_certs.py
```

This creates `certs/server.crt` and `certs/server.key` (self-signed, valid for 365 days).

### 3. Start the TLS Server (Terminal 1)

Open a **new terminal window**:

```powershell
cd "c:\Users\varun\Desktop\NPS Lab el"
python server/tls_server.py
```

You should see: `[TLS Server] Starting on https://localhost:5000`

### 4. Start the TCP Server (Terminal 2)

Open a **second terminal window**:

```powershell
cd "c:\Users\varun\Desktop\NPS Lab el"
python server/tcp_server.py
```

You should see: `[TCP Server] Starting on tcp://localhost:6000`

### 5. Start the Dashboard (Terminal 3)

Open a **third terminal window**:

```powershell
cd "c:\Users\varun\Desktop\NPS Lab el"
python dashboard/dashboard_server.py
```

You should see: `[Dashboard] Serving at http://localhost:8080`

### 6. Open the Dashboard in Browser

Open your browser and go to: **http://localhost:8080**

The dashboard will show "Waiting for data..." until you start a client.

### 7. Run Auto-Requests from Dashboard (Recommended)

Click the **Run 30 Auto** button on the dashboard. This starts 30 automated requests with adaptive protocol selection. Watch the real-time charts update!

You can also click **Stop** anytime to terminate the run cleanly.

### 8. Run the Adaptive Client from Terminal (Alternative)

If you prefer running from terminal, open a **fourth terminal window**:

```powershell
cd "c:\Users\varun\Desktop\NPS Lab el"
python client/adaptive_client.py --count 30
```

The client will send 30 requests, switching protocols adaptively.

---

## Dashboard Controls

The dashboard provides a **Network Simulation** control panel:

| Control | Function |
|---------|----------|
| **Run 30 Auto** | Starts 30 automated requests with adaptive protocol selection |
| **Stop** | Terminates an ongoing auto-run cleanly (sets stop flag + kills process) |
| **TLS Delay** | Set artificial delay for TLS in ms (0-500) |
| **TCP Delay** | Set artificial delay for TCP in ms (0-500) |
| **Error Rate** | Set packet loss / error rate as % (0-100). Affects reliability score and RTT. |
| **Probe Network** | Live-probes both protocols and displays RTT, handshake, scores in a panel (auto-hides after 10s) |
| **Reset** | Resets all delays and error rate to 0 (updates config + TLS server API) |
| **Clear** | Clears all logs from backend and frontend, resets charts and stats |

> **Tip:** Set TLS delay to 200ms and click Apply. Then start an auto-run. You will see the system detect TLS degradation and switch to TCP after 3 consecutive evaluations.

---

## Configuration Options

### Adaptive Client Flags

```powershell
python client/adaptive_client.py --help
```

| Flag | Default | Description |
|------|---------|-------------|
| `--requests` | 50 | Number of requests to send |
| `--count` | 50 | Alias for --requests |
| `--switch-at` | 25 | Request # where latency changes |
| `--low-delay` | 20.0 | Initial delay (ms) |
| `--high-delay` | 180.0 | High delay after switch (ms) |

### Manual Client (Interactive CLI)

```powershell
python client/manual_client.py
```

An interactive CLI for sending manual requests. Supports actions: health, data, echo, compute, probe, switch, status. Logs are written to `logs/manual_session_log.json` and appear in the dashboard.

### Server Flags

```powershell
python server/tls_server.py --delay 50 --packet-loss 0.1
python server/tcp_server.py --delay 10 --packet-loss 0.05
```

---

## Architecture

```
Client                          Servers
┌──────────────────┐     ┌─────────────────────┐
│  Network Prober  │────▶│  TLS Server (:5000) │
│  Decision Engine │     │  Flask + HTTPS       │
│  Hysteresis Ctrl │     └─────────────────────┘
│  Session Manager │     ┌─────────────────────┐
│  Logger          │────▶│  TCP Server (:6000) │
└──────────────────┘     │  Socket + AES-GCM   │
          │               └─────────────────────┘
          ▼
┌──────────────────┐
│  Dashboard (:8080)│
│  Chart.js + HTML  │
└──────────────────┘
```

---

## Project Structure

```
NPS Lab el/
├── certs/                  # Auto-generated TLS certificates
├── server/
│   ├── __init__.py
│   ├── shared_api.py       # Common API logic (health, data, echo, compute)
│   ├── tls_server.py       # Flask HTTPS server with TLS 1.3
│   └── tcp_server.py       # Custom TCP server with AES-GCM + replay protection
├── client/
│   ├── __init__.py
│   ├── adaptive_client.py  # Main orchestrator (auto-run)
│   ├── manual_client.py    # Interactive CLI for manual requests
│   ├── decision_engine.py  # 5-metric scoring model
│   ├── hysteresis_controller.py  # Stability control
│   ├── network_prober.py   # Protocol probing (reads simulation_config.json)
│   └── session_manager.py  # Connection manager with session-wise handshake
├── dashboard/
│   ├── dashboard_server.py # HTTP server + API endpoints
│   ├── index.html          # Dashboard UI
│   ├── style.css           # Glassmorphism styling
│   └── script.js           # Chart.js visualizations
├── logs/
│   ├── session_log.json          # Auto-generated auto-run logs
│   ├── manual_session_log.json   # Manual client logs
│   └── simulation_config.json    # Network simulation parameters
├── generate_certs.py       # Certificate generator
├── requirements.txt        # Python dependencies
├── PROJECT_REPORT.md       # Detailed implementation report
├── PROJECT_EXPLANATION.txt # File-by-file deep explanation
└── README.md               # This file
```

---

## Dashboard Charts

1. **Protocol Timeline** — Which protocol was used for each request (TLS = blue, TCP = cyan)
2. **RTT Comparison** — Latency trends split by protocol
3. **Request Outcome** — Success/failure per request (shows impact of error rate)
4. **Score Divergence** — TLS vs TCP total scores over time
5. **Decision Component Breakdown** — Stacked bar chart showing 5 score components (latency, handshake, payload, security, reliability)

---

## Key Features Implemented

- **Session-wise handshake optimization** — Handshake time is recorded only once per session (after connect/switch), not per request
- **Network simulation via dashboard** — Real-time delay and error rate injection; reflected in probe RTT, reliability score, and request outcomes
- **Emergency protocol switch** — After 3 consecutive request failures, the client automatically switches to the other protocol
- **Clean stop mechanism** — Stop button writes a stop flag that the client checks every iteration, terminating gracefully
- **Real-time probe panel** — Probe button performs live network assessment and shows results in an auto-hiding panel
- **Manual client integration** — Manual requests are logged separately and displayed in the dashboard alongside auto-run logs

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'client'` | Make sure you run scripts from the project root (`NPS Lab el`) |
| TLS certificates not found | Run `python generate_certs.py` first |
| Dashboard shows "Waiting for data" | Start the auto-run from the dashboard or run `python client/adaptive_client.py` |
| Manual logs not appearing in dashboard | Run `python client/manual_client.py` from the project root, not from inside the `client/` folder |
| Stop button doesn't stop immediately | It sets a stop flag checked at the next request. The process is also killed as fallback within ~1 second. |
| Changes to delay/error not reflecting | Make sure you click **Apply** after changing the value. The prober reads `logs/simulation_config.json`. |

---

*Prepared by: Varun Dhandharia & Sridula O S | RV College of Engineering, Bengaluru*
