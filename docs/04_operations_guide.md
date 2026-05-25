# AI Software Delivery Team — Operations Guide

## How to Build, Deploy, Monitor, Troubleshoot & Rebuild

---

## 1. Local Development Setup

### Prerequisites
- Python 3.10+
- Google Cloud SDK (`gcloud`) installed and authenticated
- A GCP project with billing enabled

### Step-by-step

```powershell
# 1. Clone the repository
cd c:\MachineLearning\
git clone <repo-url> "AI Software Delivery Team"
cd "AI Software Delivery Team"

# 2. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies (including dev tools)
cd backend
pip install -e ".[dev]"
cd ..

# 4. Authenticate with Google Cloud (for Vertex AI)
gcloud auth application-default login

# 5. Configure environment variables
# Copy the example and fill in your values:
cp backend\.env.example backend\.env
# Edit backend\.env with your GOOGLE_CLOUD_PROJECT, LANGCHAIN_API_KEY, etc.

# 6. Start the development server
cd backend
uvicorn ai_sdlc.api:app --reload --host 0.0.0.0 --port 8000 --app-dir src
```

### Local Environment Variables

Create `backend/.env` with:
```env
AI_SDLC_USE_LLM=true
AI_SDLC_LLM_PROVIDER=vertex
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-2.5-pro
GEMINI_TEMPERATURE=0.2
APP_ENV=local
LOG_LEVEL=DEBUG

# LangSmith (optional for local dev)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-langsmith-api-key
LANGCHAIN_PROJECT=ai-sdlc
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

> [!NOTE]
> When running locally, the app uses `MemorySaver` (in-memory checkpointer) since no `REDIS_URL` is set. This is fine for development.

---

## 2. GCP Infrastructure Provisioning (First-Time Setup)

Run this **once** per GCP project to create the required infrastructure:

```powershell
.\scripts\setup-gcp-infrastructure-simple.ps1 -ProjectId YOUR_PROJECT_ID -Region us-central1
```

### What it creates:

| Resource | Purpose | GCP Service |
|----------|---------|-------------|
| Firestore database | Workflow state persistence | Cloud Firestore (Native mode) |
| Redis instance (`ai-sdlc-redis`) | LLM response caching + checkpointing | Memorystore for Redis |
| Secret Manager API | Secure API key storage | Secret Manager |
| IAM bindings | Service account permissions | IAM |

### APIs Enabled:
- `firestore.googleapis.com`
- `redis.googleapis.com`
- `run.googleapis.com`
- `logging.googleapis.com`
- `aiplatform.googleapis.com`
- `secretmanager.googleapis.com`

### Manual Step: Create the LangSmith Secret
After running the infra script, create the API key secret manually:

1. Go to [Secret Manager Console](https://console.cloud.google.com/security/secret-manager).
2. Click **+ CREATE SECRET**.
3. Name: `langchain-api-key`
4. Value: your LangSmith API key.
5. Click **Create Secret**.

See: [setup-gcp-infrastructure-simple.ps1](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/scripts/setup-gcp-infrastructure-simple.ps1)

---

## 3. Deployment to Cloud Run

### Deploy Command

```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId YOUR_PROJECT_ID -Region us-central1
```

### What the script does (in order):

1. **Resolves the project number** and computes the service account email.
2. **Grants IAM roles**: `storage.admin`, `artifactregistry.writer`, `secretmanager.secretAccessor`.
3. **Fetches the Redis IP** from Memorystore and constructs the `REDIS_URL`.
4. **Deploys** the unified backend + frontend via `gcloud run deploy --source backend/`:
   - Builds a Docker image in Cloud Build.
   - Pushes the image to Artifact Registry.
   - Creates a new Cloud Run revision.
   - Sets environment variables and secrets.
   - Configures VPC egress (`private-ranges-only`) for Redis connectivity.
5. **Outputs** the application URL.

### Key Deployment Flags

| Flag | Value | Purpose |
|------|-------|---------|
| `--source backend/` | Build from source | Cloud Build will use the `Dockerfile` in `backend/` |
| `--memory=1Gi` | 1 GB RAM | Sufficient for LangGraph + ReAct agents |
| `--cpu=1` | 1 vCPU | Cost-effective for single-threaded Python |
| `--timeout=600` | 10 minutes | Long enough for complex multi-agent workflows |
| `--network=default` | Default VPC | Required for Redis connectivity |
| `--vpc-egress=private-ranges-only` | Selective routing | Only internal traffic (Redis) goes through VPC; public APIs use normal internet |
| `--set-secrets` | Secret Manager ref | Securely injects `LANGCHAIN_API_KEY` |

> [!WARNING]
> **Do NOT use `--vpc-egress=all-traffic`** unless you have Cloud NAT configured on your VPC. It will blackhole all public API calls (Vertex AI, LangSmith) and the agents will hang forever.

See: [deploy-cloud-run.ps1](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/scripts/deploy-cloud-run.ps1)

---

## 4. Monitoring

### 4.1 Cloud Run Logs (Real-Time)

**Via CLI:**
```powershell
# Stream live logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ai-sdlc-backend" --limit=100 --format="json" --freshness=5m

# Filter for errors only
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ai-sdlc-backend AND severity>=ERROR" --limit=50 --format="json"

# Search for a specific workflow
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ai-sdlc-backend" --limit=200 --format="json" | findstr "YOUR_WORKFLOW_ID"
```

**Via Console:**
1. Go to [Cloud Run Console](https://console.cloud.google.com/run).
2. Click on `ai-sdlc-backend`.
3. Click the **Logs** tab.
4. Use the filter bar to search by severity or text.

### 4.2 LangSmith Dashboard

1. Go to [smith.langchain.com](https://smith.langchain.com).
2. Select your project (`ai-sdlc`).
3. You will see a list of all workflow traces, each showing:
   - **Timeline**: Every agent invocation with duration.
   - **Token usage**: Input/output token counts per LLM call.
   - **Tool calls**: Every `write_file`, `read_file`, `run_command` invocation.
   - **Full prompts**: The exact system prompt and user prompt sent to Gemini.
   - **Raw responses**: The exact JSON or text returned by Gemini.

### 4.3 Health Check

```powershell
# Quick health check
curl https://ai-sdlc-backend-YOUR_HASH.run.app/health
# Expected: {"status":"ok"}
```

### 4.4 Key Log Messages to Watch

| Log Message | Meaning |
|------------|---------|
| `Product Owner started: workflow_id=...` | Agent began execution |
| `Developer used ReAct loop successfully` | Developer finished writing code |
| `Aggregate: auto-rework triggered` | Quality agents found issues, looping back |
| `Aggregate: forwarding to human review` | Code passed quality gates |
| `Human review gate: approved=None` | Graph paused, waiting for user |
| `Streaming workflow completed: status=awaiting_approval` | SSE stream ended, waiting for approval |
| `Failed to create RedisSaver, falling back to MemorySaver` | Redis checkpointing failed (expected on basic tier) |
| `Cache hit for schema=RequirementsOutput` | Redis LLM cache working correctly |

---

## 5. Troubleshooting Guide

### Problem: Agents hang forever ("Agent is thinking..." repeated)

**Check 1: VPC Egress**
```powershell
gcloud run services describe ai-sdlc-backend --region=us-central1 --format="yaml" | findstr "vpcAccess"
```
If you see `egress: ALL_TRAFFIC`, that's the problem. Redeploy with `--vpc-egress=private-ranges-only`.

**Check 2: Vertex AI Quota**
Go to [IAM & Admin > Quotas](https://console.cloud.google.com/iam-admin/quotas) and check if `aiplatform.googleapis.com` has hit rate limits.

**Check 3: Network connectivity**
```powershell
# Check if the container can reach Vertex AI
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ai-sdlc-backend" --limit=200 --format="json" | findstr "Gemini call failed"
```

---

### Problem: "Archive not found" on download

**Cause**: The workflow state wasn't saved properly, or the checkpointer lost state (MemorySaver after container restart).

**Fix**: Re-run the workflow. On Cloud Run with MemorySaver, downloads must happen during the same session.

---

### Problem: Approval modal shows "N/A" for code and tests

**Cause**: The SSE `agent_update` event didn't include `generated_code`/`test_cases`.

**Fix**: Ensure [api.py:L146-150](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/src/ai_sdlc/api.py#L146-L150) injects state fields when status is `awaiting_approval`.

---

### Problem: No traces in LangSmith

**Check 1**: Verify the secret is configured:
```powershell
gcloud run services describe ai-sdlc-backend --region=us-central1 --format="yaml" | findstr "LANGCHAIN"
```
You should see `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` referenced as a secret.

**Check 2**: Check startup logs for:
```
LangSmith tracing ENABLED: project=ai-sdlc
```
If you see `LANGCHAIN_API_KEY is not set — tracing will fail`, the secret isn't being injected.

**Check 3**: VPC egress. If set to `all-traffic`, LangSmith API calls are blackholed.

---

### Problem: Firestore save fails with size error

**Cause**: The `project_archive_base64` field wasn't stripped before saving.

**Fix**: Verify [store.py:L45](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/src/ai_sdlc/store.py#L45) has `state_copy.pop("project_archive_base64", None)`.

---

## 6. Rebuilding From Scratch

If you need to tear everything down and rebuild:

### Step 1: Delete Cloud Run Service
```powershell
gcloud run services delete ai-sdlc-backend --region us-central1 --project YOUR_PROJECT_ID
```

### Step 2: Delete Redis Instance
```powershell
gcloud redis instances delete ai-sdlc-redis --region us-central1 --project YOUR_PROJECT_ID
```

### Step 3: Delete Firestore Data (optional)
Go to [Firestore Console](https://console.cloud.google.com/firestore) → select `workflows` collection → delete all documents.

### Step 4: Delete Secret (optional)
```powershell
gcloud secrets delete langchain-api-key --project YOUR_PROJECT_ID
```

### Step 5: Rebuild
```powershell
# Re-provision infrastructure
.\scripts\setup-gcp-infrastructure-simple.ps1 -ProjectId YOUR_PROJECT_ID

# Re-create the LangSmith secret in the console (see Section 2)

# Re-deploy
.\scripts\deploy-cloud-run.ps1 -ProjectId YOUR_PROJECT_ID
```

---

## 7. Cost Estimation

| Resource | Cost Model | Estimated Monthly Cost |
|----------|-----------|----------------------|
| Cloud Run | Per-request, scale to zero | $0-5 (low traffic) |
| Memorystore Redis (1GB) | Always-on | ~$35/month |
| Firestore | Per read/write/storage | $0-1 (low traffic) |
| Vertex AI (Gemini 2.5 Pro) | Per 1M tokens | $1.25-5/run depending on complexity |
| Secret Manager | Per secret version access | <$0.10/month |
| **Total** | | **~$40-50/month** (mostly Redis) |

> [!TIP]
> If cost is a concern, you can delete the Redis instance when not in use and recreate it before deploying. The LLM caching is optional — the system works without it, just slower and more expensive per run.
