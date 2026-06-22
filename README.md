# Adda247 Operations Copilot — POC

Multi-agent system that automates course launch coordination.

## Quick Start

### 1. (Already done) Create uv venv + install deps
```bash
# From project root — venv is at .venv/
uv venv .venv
uv pip install -r requirements.txt
```

### 2. Set up Gemini API key (optional — works without it too)
```bash
cp .env.example .env
# Edit .env and paste your GOOGLE_API_KEY
# Get a free key at: https://aistudio.google.com/app/apikey
```

### 3. Run the backend (two ways — pick one)

**Option A — uv run (recommended, no manual activation needed)**
```bash
cd backend
uv run python main.py
```

**Option B — activate venv then run**
```bash
source .venv/bin/activate
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Open the frontend
Open `frontend/index.html` in your browser (double-click or use VS Code Live Server).

---

## Demo Flow

1. Type a goal: **"Launch SSC Foundation Batch next month"**
2. Watch agents execute live on screen
3. Review the generated execution plan
4. Click **Approve & Execute**

## Try These Goals
- `Launch SSC Foundation Batch next month`
- `Launch Banking Foundation Batch in 2 weeks`
- `Launch UPSC Prelims Batch next quarter`
- `Launch Railway Foundation Batch`

## Architecture

```
Frontend (HTML/JS)
      │  SSE stream
      ▼
FastAPI (main.py)
      │
LangGraph workflow (graph.py)
      │
  ┌───┴──────────────┐
Manager  Faculty  Ops  Marketing
Agent    Agent    Agent  Agent
  │        │       │       │
  └────────┴───────┴───────┘
              │
         Mock Tools
    (faculty_tool, lms_tool, crm_tool)
```

## Notes
- All data is mock/simulated — no real LMS or CRM calls
- Works without a Gemini API key (uses keyword-based fallback parser)
- State is in-memory — restart server to reset sessions
