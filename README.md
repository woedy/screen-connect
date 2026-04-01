# ScreenConnect

A high-performance, self-hosted remote management and support platform. Designed for IT professionals to provide instant remote assistance via a standalone agent.

```
┌─────────────┐    Binary WS    ┌──────────────┐    React UI    ┌──────────────┐
│ Desktop     │ ─────────────▶  │   Django +   │ ◀──────────── │   Browser    │
│ Agent (py)  │                 │   Channels   │                │  Dashboard   │
└─────────────┘                 └──────────────┘                └──────────────┘
                                       │
                               Postgres + Redis
```

---

## 🚀 Key Features

*   **Real-time Screen Streaming**: High-speed binary WebSocket relay with adaptive JPEG quality.
*   **Spatial Tiling Delta Compression**: Optimized bandwidth usage by only transmitting changed 128x128px screen tiles.
*   **Stealth Mode (Privacy Screen)**: Remote-only visible desktop behind a fake "Windows Update" overlay on the client machine.
*   **Remote Terminal**: Full-featured command execution with streaming output and support for long-running processes.
*   **File Manager**: High-speed directory traversal, recursive file listing, and chunked upload/download support.
*   **System Tools**: Real-time process management (kill/list), detailed system telemetry, and bidirectional clipboard sync.
*   **Native Control**: Low-latency mouse and keyboard injection with modifier key support.

---

## 🛠️ Stack

| Component | Technology |
|-----------|-----------------------------------|
| **Backend** | Django 5, DRF, Channels (ASGI), Daphne |
| **Real-time** | Django Channels + Redis (Binary Relay) |
| **Tasks** | Celery + Celery Beat (Redis Broker) |
| **Database** | PostgreSQL 16 |
| **Frontend** | React 19, Tailwind CSS v4, Vite |
| **Agent** | Python (mss, OpenCV, PyAutoGUI, WebSockets) |

---

## 📦 Quick Start (Docker)

**1. Clone and configure**

```bash
cp .env.example .env
# Edit .env — set DJANGO_SECRET_KEY, POSTGRES_PASSWORD, etc.
```

**2. Start everything**

```bash
docker compose up --build
```

**3. Create an admin user**

```bash
docker compose exec backend python manage.py createsuperuser
```

**4. Access the dashboard**

Navigate to `http://localhost:3000` and log in.

---

## 🖥️ Running the Agent

The agent is a standalone Python script designed to be run on the machine being managed.

### Dev Mode
```bash
cd agent
pip install -r requirements.txt
python agent.py --server ws://localhost:8000 --session <id> --token <token>
```

### Standalone Build (Windows)
```bash
cd agent
build.bat
# Output in agent/dist/ScreenConnect-Agent.exe
```

---

## ⚙️ Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | *(default)* | Production security key |
| `DEBUG` | `True` | Set to `False` for production |
| `POSTGRES_PASSWORD` | `screenconnect` | Database password |
| `REDIS_URL` | `redis://redis:6379/0` | Channels/Celery broker |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Allowed frontend origins |
| `SESSION_EXPIRY_HOURS` | `2` | Auto-cleanup time for sessions |

---

## 📄 License
This project is for educational and authorized IT support use only.
