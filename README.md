# ScreenConnect

Self-hosted remote desktop and support tool. A support agent opens a session from the dashboard, shares the link/token with the end user, and the user runs the desktop agent to start the session.

```
┌─────────────┐    WebSocket    ┌──────────────┐    React UI    ┌──────────────┐
│ Desktop     │ ─────────────▶  │   Django +   │ ◀──────────── │   Browser    │
│ Agent (py)  │                 │   Channels   │                │  Dashboard   │
└─────────────┘                 └──────────────┘                └──────────────┘
                                      │
                              Postgres + Redis
```

---

## Stack

| Layer     | Tech                              |
|-----------|-----------------------------------|
| Backend   | Django 5, DRF, Channels, Daphne   |
| Realtime  | Django Channels + Redis           |
| Tasks     | Celery + Celery Beat              |
| Database  | PostgreSQL 16                     |
| Frontend  | React 19, Tailwind v4, Vite       |
| Agent     | Python (mss, opencv, pyautogui)   |

---

## Quick Start (Docker)

**1. Clone and configure**

```bash
cp .env.example .env
# Edit .env — at minimum set DJANGO_SECRET_KEY and POSTGRES_PASSWORD
```

**2. Start everything**

```bash
docker compose up --build
```

**3. Create an admin user**

```bash
docker compose exec web python manage.py createsuperuser
```

**4. Open the dashboard**

```
http://localhost:3000
```

Log in with the superuser credentials you just created.

---

## Running Without Docker (Dev)

### Backend

Requirements: Python 3.11+, PostgreSQL, Redis running locally.

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt

# Set env vars or create a .env in backend/
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

In separate terminals:

```bash
# Celery worker
celery -A core worker -l info

# Celery beat (optional, for session cleanup)
celery -A core beat -l info
```

### Frontend

Requirements: Node 22+

```bash
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:5173`.

---

## Setting Up the Desktop Agent

The agent runs on the **end user's machine** — the one being controlled.

### Install dependencies

```bash
cd agent
pip install -r requirements.txt
```

### Run the agent

The agent needs a `session_id` and `token` — both come from the dashboard after creating a session.

```bash
python agent.py --server ws://localhost:8000 --session <session_id> --token <token>
```

Or build a standalone exe:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name ScreenConnect-Agent agent.py
```

---

## Testing a Full Session

1. Log into the dashboard at `http://localhost:3000`
2. Create a new session — you'll get a `session_id` and `token`
3. On the same machine (or another), run the agent:
   ```bash
   python agent.py --server ws://localhost:8000 --session <session_id> --token <token>
   ```
4. Back in the dashboard, open the session — you should see the live screen

From the session view you can:
- View and control the remote screen
- Browse, upload, and download files
- Run commands in the remote terminal
- View system info and running processes
- Sync clipboard

---

## Environment Variables

| Variable               | Default                  | Notes                          |
|------------------------|--------------------------|--------------------------------|
| `DJANGO_SECRET_KEY`    | *(insecure default)*     | **Change in production**       |
| `DEBUG`                | `True`                   | Set `False` in production      |
| `POSTGRES_PASSWORD`    | `screenconnect`          | **Change in production**       |
| `REDIS_URL`            | `redis://redis:6379/0`   |                                |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000`  | Add your frontend origin       |
| `SESSION_EXPIRY_HOURS` | `2`                      | How long sessions stay active  |

---

## API (brief)

| Method | Endpoint                        | Description              |
|--------|---------------------------------|--------------------------|
| POST   | `/api/auth/token/`              | Get JWT token            |
| POST   | `/api/auth/token/refresh/`      | Refresh JWT              |
| POST   | `/api/sessions/`                | Create session           |
| GET    | `/api/sessions/`                | List sessions            |
| GET    | `/api/sessions/{id}/`           | Session detail           |
| GET    | `/api/sessions/{id}/join/?token=` | Agent join endpoint    |
| POST   | `/api/sessions/{id}/end/`       | End session              |
| GET    | `/health/`                      | Health check             |

WebSocket: `ws://host/ws/session/{id}/?token=xxx&role=client|agent`
