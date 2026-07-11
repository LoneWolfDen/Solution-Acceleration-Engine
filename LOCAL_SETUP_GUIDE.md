# LOCAL SETUP GUIDE
## Solution Acceleration Engine — Mac (Intel + Apple Silicon)

> **Purpose of this guide:**
> Get the full stack running on your local Mac in two different ways, with all LLM traffic
> routed through the Headroom AI proxy on port `8787` to maximise cache hits and reduce token spend.
>
> **Audience:** Beginner-friendly. Every command is complete and copy-pasteable.
> No prior knowledge of Reflex, FastAPI, or Docker is assumed.

---

## Table of Contents

1. [What is running and why](#1-what-is-running-and-why)
2. [Prerequisites — install once, keep forever](#2-prerequisites--install-once-keep-forever)
3. [Section A — Shared workspace setup](#section-a--shared-workspace-setup)
   - [A1 · File-descriptor limit](#a1--file-descriptor-limit)
   - [A2 · Install Headroom proxy](#a2--install-headroom-proxy)
   - [A3 · Build the `.env` file](#a3--build-the-env-file)
4. [Method A — Docker (containerised)](#method-a--docker-containerised)
5. [Method B — Native VS Code terminals](#method-b--native-vs-code-terminals)
6. [Health check and validation](#health-check-and-validation)
7. [Troubleshooting quick-reference](#troubleshooting-quick-reference)

---

## 1. What is running and why

```
┌─────────────────────────────────────────────────────┐
│  Your Mac                                           │
│                                                     │
│  ┌─────────────────┐      ┌────────────────────┐   │
│  │  Headroom Proxy │      │  SAE Application   │   │
│  │  port 8787      │      │  port 8000         │   │
│  │                 │      │                    │   │
│  │  Intercepts ALL │      │  Reflex UI  +       │   │
│  │  LLM API calls  │      │  FastAPI backend    │   │
│  │  ↓ caches them  │      │  + SQLite DB        │   │
│  └────────┬────────┘      └────────────────────┘   │
│           │                                         │
│           ▼                                         │
│     Groq / OpenRouter / Gemini (cloud LLMs)         │
└─────────────────────────────────────────────────────┘
```

| Component | Port | What it does |
|---|---|---|
| **Headroom proxy** | `8787` | Sits in front of every LLM API call; de-duplicates identical prompts via semantic caching, saving 50–90% of tokens |
| **SAE backend** | `8000` | Runs FastAPI (REST API + WebSocket) and serves the Reflex-compiled frontend from the same port |
| **SQLite database** | *(file)* | `contexta.db` stores projects, artifacts, reviews, and proposals — persisted to disk |

---

## 2. Prerequisites — install once, keep forever

Work through this checklist **once** before using either run method.

### 2.1 — Xcode Command Line Tools

```bash
xcode-select --install
```

If already installed, this command prints `error: command line tools are already installed` — that is fine, continue.

### 2.2 — Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After install, follow any instructions in the terminal about adding Homebrew to your PATH (particularly on Apple Silicon Macs where the path is `/opt/homebrew`).

Verify:

```bash
brew --version
# expected: Homebrew 4.x.x
```

### 2.3 — Python 3.11

```bash
brew install python@3.11
```

Verify:

```bash
python3.11 --version
# expected: Python 3.11.x
```

> **Note on PEP 668 (`externally-managed-environment` errors)**
> Homebrew Python 3.11+ is "externally managed," which means `pip install` into
> the system Python is blocked by default.
> **This project uses a virtual environment (`.venv`) which bypasses this restriction entirely.**
> You never need to pip-install into the system Python; all commands in this guide
> target the `.venv` environment. If you see a PEP 668 error, you have accidentally
> used the system `pip` rather than `.venv/bin/pip`.

### 2.4 — Git

```bash
brew install git
git --version
# expected: git version 2.x.x
```

### 2.5 — Docker Desktop (Method A only)

Skip this step if you plan to use Method B (native).

Download and install from [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/). After installation, open Docker Desktop and wait for the whale icon in your menu bar to become steady (not animated) — this means the Docker Engine is running.

Verify:

```bash
docker --version
# expected: Docker version 24.x.x or higher

docker compose version
# expected: Docker Compose version v2.x.x
```

### 2.6 — Clone the repository

```bash
git clone https://github.com/LoneWolfDen/Solution-Acceleration-Engine.git
cd Solution-Acceleration-Engine
```

> All commands in this guide assume your terminal is inside the
> `Solution-Acceleration-Engine` directory unless stated otherwise.

---

## Section A — Shared workspace setup

Complete **all three steps** in Section A before choosing Method A or Method B.
These steps are identical for both run methods.

---

### A1 · File-descriptor limit

macOS defaults to 256 open file handles per process. Reflex compiles a
Next.js frontend, which reads thousands of node_modules files simultaneously.
Without raising this limit, the build can crash with `EMFILE: too many open files`.

Run this command **in every new terminal session** before starting the app,
or add it to your shell profile to make it permanent:

```bash
ulimit -n 65536
```

**Verify it was applied:**

```bash
ulimit -n
# expected: 65536
```

**Make it permanent (optional but recommended):**

```bash
# For zsh (default on macOS Catalina and later):
echo 'ulimit -n 65536' >> ~/.zshrc
source ~/.zshrc

# For bash:
echo 'ulimit -n 65536' >> ~/.bash_profile
source ~/.bash_profile
```

---

### A2 · Install the Headroom AI proxy

Headroom is a global macOS CLI tool installed via Homebrew. It acts as a
transparent proxy for all LLM API traffic, providing semantic caching.

#### A2.1 — Install

```bash
brew install headroom-ai/tap/headroom
```

> **If `brew tap` fails:** Headroom may be available as a pip install instead.
> Check [https://headroom-docs.vercel.app](https://headroom-docs.vercel.app) for
> the latest installation method.

**Verify the install:**

```bash
headroom --version
# expected: headroom, version 0.31.0 or higher
```

#### A2.2 — First-time initialisation

```bash
headroom init
```

This sets up the local memory store and proxy certificate. Follow any on-screen prompts.

#### A2.3 — Verify the proxy command is available

```bash
headroom proxy --help
```

You should see output listing `--port`, `--host`, and `--workers` options.

---

### A3 · Build the `.env` file

The application reads LLM API keys and configuration from a `.env` file in
the project root. This file is **never committed to git** — you create it locally.

#### A3.1 — Copy the example file

```bash
cp .env.example .env
```

#### A3.2 — Edit `.env` with your keys

Open `.env` in any text editor and fill in your values:

```bash
# .env — your local configuration
# ────────────────────────────────────────────────────────────────────────────
# LLM PROVIDER KEYS
# At least one provider is required to run reviews and proposals.
# Leave the others blank if you do not have keys for them.
# ────────────────────────────────────────────────────────────────────────────

GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── Headroom proxy routing ───────────────────────────────────────────────────
# Point all LLM traffic through the local Headroom proxy.
# "localhost" is correct for both native (Method B) and Docker (Method A)
# because the proxy runs on the HOST machine, not inside a container.

OPENAI_BASE_URL=http://localhost:8787/v1
ANTHROPIC_BASE_URL=http://localhost:8787

# ── Ollama (optional — only if you run a local Ollama instance) ──────────────
# Native:
OLLAMA_BASE_URL=http://localhost:11434
# Docker — uncomment this line and comment out the line above:
# OLLAMA_BASE_URL=http://host.docker.internal:11434

# ── Application settings (sensible defaults, rarely need changing) ───────────
# CONTEXTA_DB_PATH=/app/data/contexta.db
# CONTEXTA_LOG_LEVEL=WARNING
```

> **Key points:**
> - You need at least **one** of `GROQ_API_KEY`, `OPENROUTER_API_KEY`, or `GEMINI_API_KEY`.
> - The `OPENAI_BASE_URL` and `ANTHROPIC_BASE_URL` lines redirect all LiteLLM HTTP
>   calls through the Headroom proxy at `localhost:8787`. **Do not skip these.**
> - For Docker, change `OLLAMA_BASE_URL` to use `host.docker.internal` so the
>   container can reach the Ollama process running on the host machine.

---

## Method A — Docker (containerised)

Use this method when you want a clean, isolated environment that mirrors production.
Docker handles all dependencies inside the container.

**Before starting:** Complete all steps in Section A above.

---

### Step A-1 · Raise file-descriptor limit

```bash
ulimit -n 65536
```

### Step A-2 · Start the Headroom proxy on the host

The Headroom proxy **must run on your Mac** (not inside Docker). The container
will reach it via the special Docker hostname `host.docker.internal`.

Open a dedicated terminal tab and run:

```bash
headroom proxy --port 8787
```

You will see output similar to:

```
╔══════════════════════════════════════════╗
║  Headroom Proxy  v0.31.0                 ║
║  Listening on http://127.0.0.1:8787      ║
║  Semantic cache: ENABLED                 ║
╚══════════════════════════════════════════╝
```

> **Keep this terminal open.** The proxy must stay running for the duration of
> your session. LLM calls will fail if this process is stopped.

### Step A-3 · Verify Docker network routing

Make sure your `.env` file has the Docker-specific Ollama URL if you use Ollama:

```
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

The `OPENAI_BASE_URL` and `ANTHROPIC_BASE_URL` should point to `localhost:8787` —
Docker's `host.docker.internal` resolver maps `localhost` on the container to
the Mac's loopback interface, so this configuration works correctly.

> **If LLM calls fail inside Docker:** Change `localhost` to `host.docker.internal`
> in those two variables inside `.env` and rebuild.

### Step A-4 · Build the Docker image

This step downloads all Python packages and compiles the Reflex frontend into
the image. **It takes 3–10 minutes on the first run** and is fully cached afterwards.

```bash
docker compose build
```

Watch for the following success messages near the end of the build log:

```
=> [build] Running reflex init ...        ✓
=> [build] Running reflex export ...      ✓
=> exporting to image                     ✓
```

### Step A-5 · Start the application

```bash
docker compose up
```

Or, to run in the background (detached mode):

```bash
docker compose up -d
```

### Step A-6 · Watch the startup logs

```bash
docker compose logs -f sae
```

Wait for this sequence in the logs (takes ~30 seconds on first start):

```
[entrypoint] Data directory: /app/data
[entrypoint] Running database migrations...
[entrypoint] Database ready at: /app/data/contexta.db
[entrypoint] Starting Reflex backend on port 8000...
─────────────────────────────────────── App Running ───────────────────────────────────────
 URL: http://localhost:8000
```

Once you see `App Running`, the application is ready.

### Step A-7 · Verify the health endpoint

In a new terminal tab:

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

Expected response:

```json
{
    "status": "ok",
    "error": null
}
```

### Stopping the application

```bash
docker compose down
```

Your database is persisted in `./data/contexta.db` on the Mac and survives restarts.

---

## Method B — Native VS Code terminals

Use this method during active development. Changes to Python files are picked
up immediately without a rebuild. You will use **three separate terminal tabs**.

**Before starting:** Complete all steps in Section A above.

---

### Terminal Tab 1 — Headroom Proxy (ALWAYS FIRST)

> This tab runs the proxy in the foreground. **Do not close it.**

```bash
# Step B1-1: Raise file-descriptor limit
ulimit -n 65536

# Step B1-2: Start the proxy
headroom proxy --port 8787
```

Expected output:

```
╔══════════════════════════════════════════╗
║  Headroom Proxy  v0.31.0                 ║
║  Listening on http://127.0.0.1:8787      ║
║  Semantic cache: ENABLED                 ║
╚══════════════════════════════════════════╝
INFO:     Started server process [XXXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Leave this tab alone.** Every incoming LLM call will log a line here.
Cache hits appear as `[CACHE HIT]`; uncached calls appear as `[PROXY]`.

---

### Terminal Tab 2 — Environment setup and database init

> This tab sets up the Python environment and initialises the database.
> Run these steps once (or whenever dependencies change).

```bash
# Step B2-1: Navigate to the project root
cd /path/to/Solution-Acceleration-Engine
# Replace the above with your actual path, e.g.:
# cd ~/Developer/Solution-Acceleration-Engine

# Step B2-2: Raise file-descriptor limit
ulimit -n 65536

# Step B2-3: Create the virtual environment (first time only)
python3.11 -m venv .venv
```

> **If you already have a `.venv` directory:** Skip Step B2-3 and go straight to B2-4.

```bash
# Step B2-4: Activate the virtual environment
source .venv/bin/activate
```

Your terminal prompt will change to show `(.venv)` at the start, like:

```
(.venv) wolf@mac Solution-Acceleration-Engine %
```

> **Every command from this point onwards uses the activated `.venv`.
> If you open a new terminal tab, re-run `source .venv/bin/activate` inside it.**

```bash
# Step B2-5: Install all Python dependencies (first time or after pyproject.toml changes)
pip install --upgrade pip
pip install -e ".[dev]"
```

This installs: `reflex`, `fastapi`, `uvicorn`, `aiosqlite`, `litellm`, `httpx`,
`pydantic`, and all dev tools including `pytest`. It takes 1–3 minutes on
the first run.

```bash
# Step B2-6: Verify the critical packages are installed
pip show reflex litellm headroom-ai
```

You should see version info printed for all three packages.

```bash
# Step B2-7: Initialise the database
mkdir -p data
python3 -c "
import asyncio
from contexta.db.schema import init_database

async def setup():
    conn = await init_database('data/contexta.db')
    await conn.close()
    print('Database ready at: data/contexta.db')

asyncio.run(setup())
"
```

Expected output:

```
Database ready at: data/contexta.db
```

> **Subsequent starts:** You do not need to repeat B2-7 unless you delete the
> database file. The migration runner is idempotent — running it again does nothing.

```bash
# Step B2-8: Verify the database schema was applied
python3 -c "
import sqlite3
conn = sqlite3.connect('data/contexta.db')
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print('Tables:', [t[0] for t in tables])
conn.close()
"
```

Expected output (order may differ):

```
Tables: ['schema_version', 'projects', 'versions', 'artifacts',
         'artifact_version_links', 'review_jobs', 'proposal_jobs',
         'app_config', 'intelligence_layer', 'nodes', 'reviews',
         'knowledge_observations']
```

---

### Terminal Tab 3 — Reflex application server

> This tab runs the live application. Keep Tab 1 (proxy) running.

```bash
# Step B3-1: Navigate to the project root
cd /path/to/Solution-Acceleration-Engine

# Step B3-2: Raise file-descriptor limit
ulimit -n 65536

# Step B3-3: Activate the virtual environment
source .venv/bin/activate
# Prompt should show (.venv)

# Step B3-4: Load your environment variables from .env
export $(grep -v '^#' .env | grep -v '^$' | xargs)
```

Verify the proxy routing variables were loaded:

```bash
echo $OPENAI_BASE_URL
# expected: http://localhost:8787/v1
```

```bash
# Step B3-5: Start the Reflex application (development mode with hot reload)
python -m reflex run --env dev --backend-port 8000
```

The first time you run this, Reflex downloads `bun` (the JavaScript bundler)
and installs node_modules for the frontend. **This takes 2–5 minutes.** Subsequent
starts are faster (under 30 seconds).

Watch for this output sequence:

```
─── Installing bun ... ✓
─── Building frontend ...
─── Frontend ready on http://localhost:3000
─── Backend running on http://localhost:8000
─────────────────────────────────────── App Running ───────────────────────────────────────
 URL: http://localhost:3000
```

> **Dev mode uses two ports:**
> - `:3000` — Next.js frontend with hot-reload
> - `:8000` — FastAPI backend and Reflex WebSocket state-sync
>
> **Always open the app at `http://localhost:3000` in dev mode.**

---

## Health check and validation

### Step 1 — Open the application in a browser

- **Docker (Method A):** [http://localhost:8000](http://localhost:8000)
- **Native dev (Method B):** [http://localhost:3000](http://localhost:3000)

You should see the Solution Acceleration Engine dashboard:
- Left sidebar with the heading **"Contexta"**
- An empty project list with the message *"No projects found."*
- A **"New Project"** button in the sidebar

### Step 2 — Create your first project

1. Click **"New Project"** in the sidebar.
2. A dialog appears. Type any name, for example: `Test Project`
3. Click **"Create"**.
4. The project appears in the sidebar tree within 1–2 seconds.

**Expected:** The project name appears as a collapsible row in the sidebar.
No error toast appears at the bottom right of the screen.

### Step 3 — Verify the API health endpoint

```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

```json
{
    "status": "ok",
    "error": null
}
```

### Step 4 — Verify admin panel connectivity

Open [http://localhost:8000/admin](http://localhost:8000/admin) (Method A)
or [http://localhost:3000/admin](http://localhost:3000/admin) (Method B).

You should see the Admin Dashboard page with:
- A **Provider Health** section showing each provider's status
- A **Thresholds** section with sliders for Risk / Constraint / Dependency

Enter your API key for one provider in the appropriate field and click **Save Key**.
The status indicator next to that provider changes from **not_set** to **set**.

### Step 5 — Verify Headroom proxy cache hits

Look at **Terminal Tab 1** (the Headroom proxy window).

When the application makes LLM API calls, you will see log lines like:

```
# First call — cache miss, routed to provider:
[PROXY]  POST /v1/chat/completions  →  groq  (tokens_in=842, tokens_out=312)

# Identical follow-up call — served from cache:
[CACHE HIT]  POST /v1/chat/completions  (saved 842 tokens)
```

To force a cache hit immediately after creating a project:
1. Run a review on any artifact (requires a configured LLM provider key).
2. Click **"Run Review"** a second time with the **exact same settings**.
3. Check the Headroom terminal — the second call should show `[CACHE HIT]`.

You can also check savings statistics at any time:

```bash
headroom savings
```

---

## Troubleshooting quick-reference

| Symptom | Cause | Fix |
|---|---|---|
| `EMFILE: too many open files` | macOS file limit too low | Run `ulimit -n 65536` in every terminal tab |
| `error: externally-managed-environment` | Using system pip instead of venv pip | Run `source .venv/bin/activate` first |
| `ModuleNotFoundError: No module named 'reflex'` | Virtual environment not activated | Run `source .venv/bin/activate` |
| `Connection refused` on port 8000 | App not started yet | Wait for `App Running` in the Reflex terminal |
| `Connection refused` on port 8787 | Headroom proxy not running | Start it: `headroom proxy --port 8787` |
| LLM calls return `502 Bad Gateway` | Proxy up but provider key missing | Add key to `.env` and re-export |
| Docker `EADDRINUSE` on port 8000 | Port in use by another process | `docker compose down` then `docker compose up` |
| Docker LLM calls fail with `Connection refused` | Container can't reach host proxy | Change `localhost` → `host.docker.internal` in `OPENAI_BASE_URL` inside `.env` |
| Reflex WebSocket stuck as "Pending" | `api_url` mismatch | Set `REFLEX_API_URL=http://localhost:8000` before running `reflex run` |
| `PEP 668` error on pip install | Running pip outside venv | Always activate `.venv` before pip commands |
| Database tables missing | `init_database` not run | Re-run Step B2-7 |
| Blank white screen in browser | Frontend build failed | Check Tab 3 logs for JS build errors; re-run `python -m reflex run` |

### Reset everything and start clean

If your environment becomes corrupted or you want a fresh start:

```bash
# Stop all running processes first (Ctrl+C in each terminal tab)

# Remove the virtual environment and database
rm -rf .venv data/contexta.db

# Recreate (follow Section A3 and Method B steps from the beginning)
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
mkdir -p data
python3 -c "
import asyncio
from contexta.db.schema import init_database
asyncio.run(init_database('data/contexta.db'))
"
python -m reflex run --env dev --backend-port 8000
```

---

## Quick-start cheat sheet

```
┌─────────────────────────────────────────────────────────────────────────┐
│  EVERY SESSION — run in every new terminal tab, before anything else    │
│                                                                         │
│  ulimit -n 65536                                                        │
│  source .venv/bin/activate                                              │
├─────────────────────────────────────────────────────────────────────────┤
│  Tab 1  (proxy — leave running)                                         │
│  headroom proxy --port 8787                                             │
├─────────────────────────────────────────────────────────────────────────┤
│  Tab 2  (one-time setup, skip after first run)                          │
│  pip install -e ".[dev]"                                                │
│  python3 -c "import asyncio; from contexta.db.schema import            │
│    init_database; asyncio.run(init_database('data/contexta.db'))"      │
├─────────────────────────────────────────────────────────────────────────┤
│  Tab 3  (app server)                                                    │
│  export $(grep -v '^#' .env | grep -v '^$' | xargs)                    │
│  python -m reflex run --env dev --backend-port 8000                    │
├─────────────────────────────────────────────────────────────────────────┤
│  Open browser → http://localhost:3000                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

*This guide was written for the Solution Acceleration Engine v0.1.0 running
Reflex 0.9.6, Python 3.11–3.14, and Headroom AI 0.31.0.*
