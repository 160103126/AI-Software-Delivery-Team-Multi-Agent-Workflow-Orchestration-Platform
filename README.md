# AI Software Delivery Team

A multi-agent platform that automates the entire software delivery lifecycle using AI. 

One natural-language prompt → 8 specialized AI agents take over:
1. 🧠 **Product Owner** → analyzes requirements
2. 🏗️ **Architect** → designs the system
3. 📋 **Scrum Master** → plans sprint tasks
4. 👨‍💻 **Developer** → writes real, executable code
5. 🧪 **QA Engineer** → writes & runs pytest tests
6. 🔒 **Security Agent** → runs bandit SAST + pip-audit SCA
7. 📝 **Code Reviewer** → reviews for maintainability
8. ☁️ **DevOps** → generates deployment plan

*(Plus an automated Auto-Rework loop and a Human Approval gate!)*

The execution agents (Developer, QA, Security) use the **ReAct (Reasoning and Acting)** loop. They don't just generate text—they are equipped with a sandbox and tools to read/write files and execute terminal commands. If tests fail or vulnerabilities are found, an Aggregator node intercepts the terminal traces and feeds them back to the Developer agent to automatically fix the code.

## Tech Stack
* **Orchestration**: LangGraph (state machine with parallel fan-out)
* **LLM**: LangChain + Gemini 2.5 Pro (via Google Vertex AI)
* **Backend**: FastAPI + Python 3.10
* **Frontend**: Vanilla JS + HTML/CSS (Server-Sent Events for real-time terminal streaming)
* **State & Caching**: Redis (LLM caching & checkpointing) + Firestore (persistent storage)
* **Deployment**: GCP Cloud Run
* **Observability & Evaluation**: LangSmith

## Run Locally

You must have Google Cloud SDK installed and authenticated to use Vertex AI.

```powershell
# 1. Authenticate with GCP
gcloud auth application-default login
gcloud config set project your-gcp-project-id

# 2. Install dependencies
venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 3. Start the server (serves both API and Frontend)
venv\Scripts\python.exe -m uvicorn ai_sdlc.api:app --app-dir backend\src --reload
```

Open your browser to: **http://127.0.0.1:8000**

## Cloud Run Deployment

The project includes a fully automated PowerShell script to deploy the backend and frontend to Google Cloud Run, backed by a managed Redis instance and Firestore.

```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId your-gcp-project-id -Region us-central1
```

## Offline Evaluation (LangSmith)

We use a deterministic, zero-LLM-judge evaluation pipeline to measure agent reliability against a "Golden Dataset" of 8 rigorous software engineering prompts (e.g., JWT Auth, Sliding Window Rate Limiter, Async Job Queue). 

To run the offline evaluation and push scores to your LangSmith dashboard:

```powershell
venv\Scripts\python.exe backend\scripts\run_evaluation.py --experiment "v2.0-latest"
```

## Project Layout

```text
frontend/           # Deprecated Streamlit UI (kept for reference)
docs/               # Architecture diagrams, issue logs, and project breakdowns
scripts/            # GCP Deployment scripts
backend/
  Dockerfile
  pyproject.toml
  requirements.txt
  pytest.ini
  frontend/         # Active HTML/JS/CSS UI served by FastAPI
  scripts/          # Evaluation and demo scripts
  src/ai_sdlc/      # Main LangGraph and Agent implementation
  tests/            # Platform unit tests
```
