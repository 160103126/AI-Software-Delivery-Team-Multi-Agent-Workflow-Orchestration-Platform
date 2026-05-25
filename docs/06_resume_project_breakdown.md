# AI Software Delivery Team — Resume Project Breakdown

---

## 🎯 One-Liner (Resume Title)

**AI Software Delivery Team — Multi-Agent Workflow Orchestration Platform**

> Built an autonomous multi-agent platform that replaces 8 human SDLC roles (Product Owner, Architect, Scrum Master, Developer, QA, Security, Code Reviewer, DevOps) with LLM-powered AI agents orchestrated via a LangGraph state machine, featuring a human-in-the-loop approval gate, real-time SSE streaming, and production deployment on GCP Cloud Run.

---

## 📋 What the Project Is

A **fully autonomous software delivery pipeline** where a single natural-language prompt (e.g. *"Build a palindrome checker in Python"*) triggers an end-to-end workflow that:

1. **Analyzes requirements** (Product Owner agent)
2. **Designs architecture** (Architect agent)
3. **Plans sprint tasks with dependencies** (Scrum Master agent)
4. **Writes real, executable Python code** into a sandboxed workspace (Developer agent)
5. **Writes and runs `pytest` tests** against the code (QA agent)
6. **Runs `bandit` SAST + `pip-audit` SCA** security scans (Security agent)
7. **Reviews code for maintainability and correctness** (Reviewer agent)
8. **Auto-reworks code** if quality agents find issues (Aggregate + feedback loop)
9. **Pauses for human approval** (Human-in-the-loop gate)
10. **Generates a GCP deployment plan** (DevOps agent)
11. **Zips the workspace** into a downloadable archive (Archiver node)

### Key Differentiator
The **only human intervention required is the approval gate** — everything else is fully autonomous, including writing files, running tests, and fixing bugs in a feedback loop.

---

## 🏗️ Multi-Agent Architecture (How It Works)

### The Agent Roster (10 Agents + 2 Infrastructure Nodes)

| Agent | What It Does | LLM Pattern |
|-------|-------------|-------------|
| **Product Owner** | Parses user request → structured JSON requirements (summary, functional, non-functional, acceptance criteria, priority) | Single-shot `invoke_json_model` with Pydantic validation |
| **Architect** | Designs API surface, service boundaries, data layer, security controls | Single-shot `invoke_json_model` |
| **Scrum Master** | Breaks plan into prioritized tasks with dependency ordering | Single-shot `invoke_json_model` |
| **Developer** | Writes actual Python files into a sandboxed temp directory | **ReAct loop** — multi-step tool use (`write_file`, `read_file`, `run_command`) |
| **QA Engineer** | Writes pytest tests, runs them, iterates on failures | **ReAct loop** with tools |
| **Security Agent** | Runs `bandit` (SAST) + `pip-audit` (SCA) via tool use | **ReAct loop** with tools |
| **Reviewer** | Reads workspace files, evaluates maintainability/correctness | **ReAct loop** with tools |
| **Aggregate** | Decision node: auto-rework or forward to human review | Deterministic (no LLM) |
| **Human Review** | Pauses the graph for manual approve/reject | Deterministic gate |
| **DevOps** | Generates a GCP Cloud Run deployment plan | Single-shot `invoke_json_model` |
| **Archiver** | Zips workspace → base64 for download | Deterministic (no LLM) |

### Two LLM Execution Patterns

**1. `invoke_json_model`** — Single-shot structured output
- LLM is called once, response is parsed as JSON, validated against a **Pydantic schema**
- If the LLM returns malformed JSON → Pydantic `ValidationError` → agent falls back to deterministic output
- Used by: Product Owner, Architect, Scrum Master, DevOps

**2. `invoke_agent_with_tools` (ReAct Loop)** — Multi-step autonomous execution
- Uses LangChain's `create_react_agent` — the LLM autonomously calls tools in a loop:
  - **Thinks** → generates reasoning
  - **Acts** → calls a tool (`write_file`, `run_command`, etc.)
  - **Observes** → reads the tool result
  - **Repeats** until done (up to 30 iterations)
- Used by: Developer, QA, Security, Reviewer

### Workflow Graph (State Machine)

```
START → entry → product_owner → architect → scrum_master → developer
                                                              ↓
                                              ┌───────────────┼───────────────┐
                                              ↓               ↓               ↓
                                             QA           Security        Reviewer
                                              ↓               ↓               ↓
                                              └───────────────┼───────────────┘
                                                              ↓
                                                          aggregate
                                                         ↙         ↘
                                            (issues found)     (clean or budget exhausted)
                                                ↓                      ↓
                                            developer            human_review
                                                                ↙    ↓     ↘
                                                         approved  waiting  rejected
                                                            ↓        ↓        ↓
                                                          devops    END    developer
                                                            ↓
                                                         archiver → END
```

### Key Routing Decisions

| Decision Point | Logic |
|---------------|-------|
| **After Developer** | Fan-out: QA, Security, and Reviewer run **in parallel** |
| **After Aggregate** | If issues found AND rework budget remaining → loop back to Developer. Otherwise → Human Review |
| **After Human Review** | Approved → DevOps. Rejected (iterations left) → Developer. Waiting → END (graph pauses) |

### Auto-Rework Feedback Loop
1. Developer writes code
2. QA + Security + Reviewer evaluate in parallel
3. `_has_actionable_findings()` checks if any agent found real issues
4. If yes, the workflow loops back to Developer with feedback injected via `agent_feedback_context()`
5. Developer re-generates code addressing all findings
6. Loop repeats up to `max_auto_reworks` times (default: 1)

---

## 🛠️ Technology Stack

### Core Application
| Technology | Purpose | Why This Choice |
|-----------|---------|-----------------|
| **Python 3.10+** | Primary language | De facto standard for AI/ML; LangChain/LangGraph are Python-first |
| **FastAPI** | REST API framework | Async SSE streaming, auto OpenAPI docs, Pydantic validation, `StreamingResponse` |
| **Uvicorn** | ASGI server | Recommended production server for FastAPI, HTTP/1.1 keep-alive for SSE |
| **Pydantic v2** | Data validation | API request/response validation + LLM output schema enforcement |

### AI Orchestration
| Technology | Purpose | Why This Choice |
|-----------|---------|-----------------|
| **LangGraph** | Multi-agent orchestration | State machine semantics, built-in checkpointing, parallel fan-out, conditional edges |
| **LangChain** | LLM interface layer | Standardized interface to Gemini; `create_react_agent` for tool-using agents |
| **Google Gemini 2.5 Pro** | LLM backbone (via Vertex AI) | No API key needed (IAM auth), enterprise SLAs, VPC-native traffic |

### Data & Persistence
| Technology | Purpose | Why This Choice |
|-----------|---------|-----------------|
| **Google Cloud Firestore** | Workflow state storage (NoSQL) | Zero ops, serverless, native GCP IAM, document model fits nested workflow state |
| **Redis (GCP Memorystore)** | LLM response caching (24h TTL) + LangGraph checkpointing | Complex data types, persistence; saves API costs via caching |

### Security Scanning
| Technology | Purpose | Why This Choice |
|-----------|---------|-----------------|
| **Bandit** | SAST (Static Application Security Testing) | Industry-standard Python SAST, offline, non-interactive |
| **pip-audit** | SCA (Software Composition Analysis) | Checks PyPI CVE database; replaced `safety` (which hangs in headless environments) |

### Observability
| Technology | Purpose | Why This Choice |
|-----------|---------|-----------------|
| **LangSmith** | LLM tracing & evaluation | Full traces of every LLM call, tool invocation, ReAct step; cost tracking; evaluation datasets |
| **Python `logging`** | Structured application logs | Every agent emits `workflow_id`, `agent_name`, `status` for searchability |

### Deployment & Infrastructure
| Technology | Purpose | Why This Choice |
|-----------|---------|-----------------|
| **Google Cloud Run** | Serverless container hosting | Scale to zero, source deploy, managed HTTPS, direct VPC egress |
| **Docker** | Containerization | `python:3.10-slim` base, non-root user, health check endpoint |
| **Google Cloud Secret Manager** | API key storage | Prevents hardcoded secrets; injected via `--set-secrets` at deploy time |

### Frontend
| Technology | Purpose | Why This Choice |
|-----------|---------|-----------------|
| **Vanilla HTML/CSS/JS** | Primary UI (terminal-style log viewer + approval modal) | Zero build step, served directly as static files by FastAPI |
| **Server-Sent Events (SSE)** | Real-time streaming | Simpler than WebSocket for unidirectional server→client push |
| **Streamlit** | Secondary UI (developer dashboard with tabs) | Rapid prototyping, tabbed output views, JSON viewer |

---

## 🚀 Deployment Architecture

```
Cloud Run Backend (FastAPI + Uvicorn)
  ├─ Firestore (Workflow storage)
  ├─ Memorystore Redis (LLM response caching)
  ├─ Vertex AI (Gemini LLM calls)
  ├─ Secret Manager (API keys)
  └─ Cloud Logging (Logs)

Cloud Run Frontend (Streamlit) — optional
  └─ Calls Backend API
```

### Deployment Pipeline
1. **Infrastructure Setup** — PowerShell/Bash scripts create Firestore database, Redis instance, IAM bindings
2. **Build & Deploy** — `gcloud run deploy --source` builds Docker image in Cloud Build → pushes to Artifact Registry → deploys to Cloud Run
3. **Secrets Injection** — `--set-secrets="LANGCHAIN_API_KEY=langchain-api-key:latest"` pulls secrets from Secret Manager at runtime
4. **VPC Networking** — `--vpc-egress=private-ranges-only` routes only internal traffic (Redis) through VPC; public API calls (Vertex AI, LangSmith) go through normal internet
5. **Scaling** — Cloud Run auto-scales 0→N instances based on traffic

### Estimated Monthly Cost
| Service | Monthly Cost |
|---------|-------------|
| Cloud Run (2M req/month) | ~$5-15 |
| Firestore | ~$1-5 |
| Memorystore Redis (1GB) | ~$7-10 |
| Vertex AI (pay per request) | ~$0.001-0.01/req |
| **Total** | **~$15-30/month** |

---

## 🐛 Issues Resolved (9 Major Issues)

### Critical Issues

| # | Issue | Root Cause | Resolution |
|---|-------|-----------|------------|
| **3** | **SSE stream killed on first ping** | `return` instead of `continue` in SSE parser — exited the entire `streamResponse` function | Changed `return` to `continue` in the event loop |
| **4** | **`safety` tool hangs in CI/CD** | `safety` 3.7+ introduced interactive authentication prompt — blocks forever in headless containers | Replaced `safety` with `pip-audit` (non-interactive, maintained by PyPA) |
| **5** | **Infinite rejection loop** | Stale `approved=False` flag not reset after aggregate → human_review immediately re-rejected without waiting | Added `"approved": None` reset in `aggregate_agent` when forwarding to human review |
| **6** | **Firestore 1MB document limit crash** | 11.5MB base64 archive stored in workflow state → Firestore rejected the write, SSE froze browser | 3-part fix: strip archive before Firestore save, strip from SSE events, selectively inject `generated_code`/`test_cases` into approval payload |
| **7** | **Cloud Run agents hang forever** | `--vpc-egress=all-traffic` routed ALL outbound traffic through VPC (including Vertex AI, LangSmith) — no Cloud NAT configured → traffic blackholed | Changed to `--vpc-egress=private-ranges-only` |

### High/Medium Issues

| # | Issue | Root Cause | Resolution |
|---|-------|-----------|------------|
| **1** | **Dockerfile build failure** | `pip install` ran before `COPY src` — build system couldn't find source | Reordered Dockerfile layers |
| **2** | **Artifact Registry permission denied** | Missing `roles/artifactregistry.writer` IAM role on compute service account | Added IAM binding in deployment script |
| **8** | **RedisSaver initialization failure** | `langgraph-checkpoint-redis` API mismatch + Memorystore Basic tier lacks RedisJSON module | Graceful fallback to in-memory `MemorySaver` |
| **9** | **Hardcoded API key in deployment script** | Quick iteration led to plaintext key in source code | Migrated to Google Cloud Secret Manager + `--set-secrets` |

---

## 🛡️ Hallucination Defense (6 Layers)

| Layer | Mechanism | How It Prevents Hallucination |
|-------|-----------|------------------------------|
| **1. Tool Grounding** | Agents actually execute code (`pytest`, `bandit`) — not just generate text about it | LLM can hallucinate anything in text, but cannot fake a passing `pytest` run |
| **2. Pydantic Validation** | Every `invoke_json_model` validates LLM output against strict schemas | Catches missing fields, wrong types, invalid enums |
| **3. Deterministic Security** | `bandit` + `pip-audit` are pattern-matched, not AI-interpreted | Even if LLM says "code is secure", bandit shows real vulnerabilities |
| **4. Multi-Agent Adversarial** | 3 independent agents (QA, Security, Reviewer) with different prompts evaluate the same code in parallel | Developer's hallucinations must survive 3 independent AI reviewers |
| **5. Human-in-the-Loop** | Graph physically pauses at approval gate — cannot proceed without human click | Final human check on generated code and test results |
| **6. Context Management** | Each agent gets only relevant fields, truncated to safe token limits | Reduces irrelevant context → reduces hallucination probability |

---

## 📝 Resume Bullet Points (Copy-Paste Ready)

### Short Version (2-3 bullets)
- Built a multi-agent AI platform using **LangGraph + FastAPI + Gemini** that automates the full SDLC pipeline — requirements analysis, architecture design, code generation, testing, security scanning, and deployment planning — with a human-in-the-loop approval gate
- Implemented **10 specialized AI agents** using two execution patterns: single-shot structured JSON output and multi-step ReAct tool-use loops with sandboxed file I/O and command execution
- Deployed on **GCP Cloud Run** with Firestore persistence, Redis caching, Secret Manager, LangSmith observability, and SSE real-time streaming

### Detailed Version (5-6 bullets)
- Architected and built a **multi-agent workflow orchestration platform** using LangGraph state machine with 10 AI agents (Product Owner, Architect, Scrum Master, Developer, QA, Security, Reviewer, Aggregate, Human Review, DevOps) that converts a natural-language feature request into production-ready code
- Designed a **dual LLM execution pattern**: `invoke_json_model` for single-shot structured output with Pydantic schema validation, and `invoke_agent_with_tools` (ReAct loop) for multi-step autonomous code generation with sandboxed `write_file`, `read_file`, and `run_command` tools
- Built a **parallel fan-out/fan-in architecture** where QA, Security, and Reviewer agents evaluate the Developer's code concurrently, with an auto-rework feedback loop that routes issues back to the Developer
- Implemented **6-layer hallucination defense**: tool-grounded execution (actual pytest runs), Pydantic schema validation, deterministic security scanning (bandit + pip-audit), multi-agent adversarial review, human approval gate, and context window management
- Deployed to **GCP Cloud Run** with Firestore (NoSQL storage), Memorystore Redis (LLM caching), Secret Manager (API keys), Vertex AI (Gemini 2.5 Pro), and LangSmith (tracing/evaluation)
- Resolved 9 production issues including VPC egress misconfiguration, Firestore 1MB document limits, SSE streaming bugs, infinite state machine loops, and API key security — all documented with root cause analysis

---

## 🎤 Interview Talking Points

### "Tell me about this project"
> "I built an autonomous software delivery platform where a single natural-language prompt triggers a full SDLC pipeline. It has 10 AI agents — Product Owner, Architect, Developer, QA, Security, Reviewer, etc. — orchestrated as a LangGraph state machine. The Developer agent doesn't just generate text — it actually writes files into a sandboxed workspace and runs pytest. QA, Security, and Reviewer evaluate the code in parallel. If they find issues, the workflow auto-reworks. A human approval gate provides the final checkpoint before deployment planning."

### "How does the multi-agent orchestration work?"
> "It's a LangGraph StateGraph with conditional edges. After the Developer finishes, we fan out to 3 quality agents in parallel. They converge at an aggregate node that checks for actionable findings. If issues exist and we haven't exhausted the rework budget, it loops back to the Developer with feedback. Otherwise, it pauses at a human review gate. The graph uses LangGraph checkpointing so it can pause and resume — even hours later when the user clicks Approve."

### "What was the hardest bug you fixed?"
> "The Firestore 1MB crash. The Archiver was base64-encoding the entire workspace (~11.5MB) and storing it in the workflow state. When we saved to Firestore, it silently failed. The SSE event also tried to send 11MB to the browser, freezing the UI. And the approval modal showed 'N/A' because the agent_update event didn't include the code fields. It was a 3-part fix: strip the archive from Firestore saves, strip it from SSE events, and selectively inject code/test summaries into the approval payload."

### "How do you handle LLM hallucinations?"
> "Six layers: First, tool grounding — the QA agent actually runs pytest, so the LLM can't fake passing tests. Second, Pydantic validation catches malformed JSON. Third, bandit and pip-audit are deterministic — they don't depend on AI. Fourth, three independent agents review the same code with different focuses. Fifth, a human approval gate. Sixth, context window management — each agent only gets the fields it needs, truncated to safe limits."

### "Why these tech choices?"
> "LangGraph over raw LangChain because we needed state machine semantics — conditional edges, parallel fan-out, checkpointing for human-in-the-loop. FastAPI over Flask for native async and SSE streaming. Firestore over PostgreSQL because workflow state is a nested dict that maps perfectly to documents, and it's zero-ops. Vertex AI over the Gemini Developer API because it uses IAM auth — no API key to manage — and traffic stays within Google's network when deployed on Cloud Run."

---

## 📊 Project Metrics

| Metric | Value |
|--------|-------|
| Total source files | 12 Python modules + 3 frontend files |
| Total lines of code | ~1,800+ (backend) + 200 (frontend) |
| AI agents | 10 specialized + 2 infrastructure nodes |
| LLM execution patterns | 2 (structured JSON + ReAct tool-use) |
| API endpoints | 8 (REST + SSE streaming) |
| Pydantic schemas | 8 validation models |
| Tools for agent sandbox | 4 (write_file, read_file, list_directory, run_command) |
| Issues resolved | 9 documented with root cause analysis |
| Hallucination defense layers | 6 |
| Deployment infrastructure | 5 GCP services (Cloud Run, Firestore, Redis, Secret Manager, Vertex AI) |
| Documentation pages | 5 detailed docs + README + DEPLOYMENT guide |
