# Dual-Mode Secure API Communication with Multi-Metric Driven Protocol Selection

**NPS Lab 6th Sem — RV College of Engineering, Bengaluru**
**Team:** Varun Dhandharia (1RV23CS279) & Sridula O S (1RV23CS303)

---

## Overview

This project implements an **Adaptive Session-Based Protocol Selection System** that dynamically chooses between:

- **Secure Mode (TLS)** — Flask HTTPS server with TLS 1.3 on port 5000
- **Fast Mode (TCP)** — Custom raw TCP server with AES-256-GCM encryption on port 6000

A **decision engine** scores both protocols based on latency, handshake time, and payload size. A **hysteresis controller** prevents rapid oscillation by requiring a candidate protocol to maintain a >15% score advantage for 3 consecutive checks before switching.

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

### 6. Run the Adaptive Client (Terminal 4)

Open a **fourth terminal window**:

```powershell
cd "c:\Users\varun\Desktop\NPS Lab el"
python client/adaptive_client.py
```

The client will send 50 requests, switching protocols adaptively.

### 7. Open the Dashboard

Open your browser and go to: **http://localhost:8080**

Watch the real-time charts update as the client runs!

---

## Configuration Options

### Adaptive Client Flags

```powershell
python client/adaptive_client.py --help
```

| Flag | Default | Description |
|------|---------|-------------|
| `--requests` | 50 | Number of requests to send |
| `--switch-at` | 25 | Request # where latency changes |
| `--low-delay` | 20 | Initial delay (ms) |
| `--high-delay` | 180 | High delay after switch (ms) |

### Server Flags

```powershell
python server/tls_server.py --delay 50    # Set TLS delay to 50ms
python server/tcp_server.py --delay 10    # Set TCP delay to 10ms
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
│   ├── shared_api.py       # Common API logic
│   ├── tls_server.py       # Flask HTTPS server
│   └── tcp_server.py       # Custom TCP server
├── client/
│   ├── adaptive_client.py  # Main orchestrator
│   ├── decision_engine.py  # Scoring model
│   ├── hysteresis_controller.py
│   ├── network_prober.py   # Protocol probing
│   └── session_manager.py  # Connection manager
├── dashboard/
│   ├── dashboard_server.py # HTTP server for dashboard
│   ├── index.html          # Dashboard UI
│   ├── style.css           # Styling
│   └── script.js           # Chart.js visualizations
├── logs/
│   └── session_log.json    # Auto-generated logs
├── generate_certs.py       # Certificate generator
├── requirements.txt        # Python dependencies
└── README.md               # This file
```
