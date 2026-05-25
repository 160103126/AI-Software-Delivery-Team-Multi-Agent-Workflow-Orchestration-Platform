# AI Software Delivery Team — Issues Faced & Resolutions

This document catalogues every significant issue encountered during development and deployment, ordered chronologically. Each entry includes the **symptom**, **root cause**, **resolution**, and **lesson learned**.

---

## Issue #1: Dockerfile Build Failure — `src` Directory Not Found

### Symptom
`pip install -e .` failed during Docker build with an error that the `src/` directory could not be found.

### Root Cause
The `Dockerfile` ran `pip install` **before** the `COPY src ./src` step. Since `pyproject.toml` references `[tool.setuptools.packages.find] where = ["src"]`, pip couldn't locate the package.

### Resolution
Reordered `Dockerfile` layers so that `COPY src ./src` and `COPY frontend ./frontend` come **before** `RUN pip install`:

```diff
 COPY pyproject.toml .
+COPY src ./src
+COPY frontend ./frontend
 RUN pip install --no-cache-dir -e .
```

See: [Dockerfile](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/Dockerfile)

### Lesson
Always ensure all source files referenced by your build system are copied into the container before running the install step.

---

## Issue #2: Cloud Build Permission Denied — Artifact Registry

### Symptom
`gcloud run deploy --source` failed with a permission error when trying to push the built container image to Artifact Registry.

### Root Cause
The default Compute Engine service account (`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`) did not have the `roles/artifactregistry.writer` IAM role.

### Resolution
Added an IAM policy binding in [deploy-cloud-run.ps1](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/scripts/deploy-cloud-run.ps1#L30-L34):

```powershell
gcloud projects add-iam-policy-binding "$ProjectId" `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/artifactregistry.writer" --quiet
```

### Lesson
Cloud Run source deploys require both `roles/storage.admin` (for Cloud Build staging) and `roles/artifactregistry.writer` (for pushing the final image). Always pre-grant both.

---

## Issue #3: SSE Stream Killed on First Ping — `return` vs `continue`

### Symptom
The frontend showed "Initializing multi-agent workflow..." then immediately disconnected. No agent updates were ever received.

### Root Cause
In [app.js](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/frontend/app.js), the SSE parser used `return` when encountering a `ping` event, which **exited the entire `streamResponse` function**, killing the EventSource connection:

```javascript
// BUG: 'return' kills the entire stream
if (eventData.message) {
    appendLog(eventData.message, 'system');
    return;  // ← This exits the function!
}
```

### Resolution
Changed `return` to `continue` to skip only the current line, not exit the function:

```javascript
if (eventData.message) {
    appendLog(eventData.message, 'system');
    continue;  // ← Skip this line, keep reading the stream
}
```

### Lesson
In a streaming parser loop, `return` exits the function while `continue` skips to the next iteration. In SSE processing, always use `continue` for non-terminal events.

---

## Issue #4: `safety` Tool Hangs in CI/CD — Interactive Prompt

### Symptom
The Security Agent's ReAct loop hung indefinitely when running `safety scan` on Windows/Cloud Run. The pipeline never completed.

### Root Cause
`safety` version 3.7+ introduced an **interactive authentication prompt** that requires user input. In a headless CI/CD container, this blocks forever waiting for stdin.

### Resolution
1. Removed `safety` from `pyproject.toml`.
2. Added `pip-audit` as a non-interactive replacement for Software Composition Analysis (SCA).
3. Updated the Security Agent's system prompt to instruct it to use `bandit` (SAST) and `pip-audit` (SCA).

See: [pyproject.toml:L34-35](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/pyproject.toml#L34-L35)

### Lesson
Security scanning tools used in automated pipelines must be fully non-interactive. Always test CI tools in a headless environment before committing them to the pipeline.

---

## Issue #5: Infinite Rejection Loop — Stale `approved` Flag

### Symptom
After a human rejection, the workflow looped back to the Developer → QA → Security → Reviewer → Aggregate → Human Review cycle indefinitely, never pausing for user input again.

### Root Cause
When the Aggregate node forwarded the workflow back to `human_review`, the `approved` field still held the stale value of `False` from the previous rejection. The `human_review_node` immediately saw `approved=False` and routed back to `developer` without waiting.

### Resolution
Added an explicit reset of `approved` to `None` in the `aggregate_agent` function when forwarding to human review:

```python
# CRITICAL: Reset so the graph pauses and waits for the user again
return {"status": "awaiting_approval", "approved": None, ...}
```

See: [agents.py:L359-360](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/src/ai_sdlc/agents.py#L359-L360)

### Lesson
In stateful graph workflows, **always reset control-flow flags** when routing to gate nodes. A stale boolean can create silent infinite loops that are extremely hard to debug.

---

## Issue #6: Firestore 1MB Document Limit — 11.5MB Archive Crash

### Symptom
```
ERROR | ai_sdlc.store | Failed to save workflow: 400 Request payload size exceeds the limit: 11534336 bytes.
```
The download button showed "Archive not found" and the approval modal showed "N/A" for code and tests.

### Root Cause
The Archiver node base64-encoded the entire workspace directory (~11.5MB) and stored it in `project_archive_base64` on the workflow state. When `workflow_store.save()` tried to write this state to Firestore, it exceeded the **1MB per-document limit**.

The crash had three cascading effects:
1. The state never persisted to Firestore → download endpoint couldn't find the archive.
2. The SSE `workflow_completed` event tried to send the full 11MB state to the browser → browser froze.
3. The `agent_update` event for the approval status didn't include `generated_code`/`test_cases` → modal showed "N/A".

### Resolution (3 fixes)
1. **store.py**: Strip `project_archive_base64` before saving to Firestore:
   ```python
   state_copy.pop("project_archive_base64", None)
   ```
   See: [store.py:L45](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/src/ai_sdlc/store.py#L45)

2. **api.py**: Strip the archive from the `workflow_completed` SSE event:
   ```python
   safe_state = deepcopy(final_state)
   safe_state.pop("project_archive_base64", None)
   ```
   See: [api.py:L122-124](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/src/ai_sdlc/api.py#L122-L124)

3. **api.py**: Selectively inject `generated_code` and `test_cases` into the `agent_update` payload when `status == "awaiting_approval"`:
   ```python
   if state.get("status") == "awaiting_approval":
       payload["state"] = {
           "generated_code": state.get("generated_code"),
           "test_cases": state.get("test_cases")
       }
   ```
   See: [api.py:L146-150](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/backend/src/ai_sdlc/api.py#L146-L150)

### Lesson
Never store large binary blobs (base64 archives, images) in document databases. Keep them in the checkpointer (Redis/memory) for download, and only persist metadata to Firestore. Always strip large fields before sending data over SSE to avoid browser freezes.

---

## Issue #7: Cloud Run Agents Hang Forever — VPC Egress Misconfiguration

### Symptom
Frontend showed `> Agent is thinking...` repeated 30+ times. No agent names ever appeared. The workflow never completed.

### Root Cause
The deployment script used `--vpc-egress=all-traffic` to enable connectivity to the internal Redis instance. This routed **all** outbound traffic through the VPC, including calls to:
- **Vertex AI API** (`aiplatform.googleapis.com`) — LLM calls hung indefinitely.
- **LangSmith API** (`api.smith.langchain.com`) — traces were silently dropped.

The VPC had no Cloud NAT configured, so public internet traffic was blackholed.

### Resolution
Changed the egress mode from `all-traffic` to `private-ranges-only`:

```diff
-  --vpc-egress=all-traffic `
+  --vpc-egress=private-ranges-only `
```

See: [deploy-cloud-run.ps1:L62](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/scripts/deploy-cloud-run.ps1#L62)

This routes only internal/private IP traffic (like Redis at `10.x.x.x`) through the VPC, while public API calls go through the normal internet path.

### Lesson
`--vpc-egress=all-traffic` requires a Cloud NAT to be configured on the VPC for outbound internet access. Use `private-ranges-only` when you only need internal connectivity (e.g., Redis, Firestore) and your service also needs to call public APIs.

---

## Issue #8: RedisSaver Initialization Failure — API Mismatch

### Symptom
Cloud Run logs showed:
```
Failed to create RedisSaver, falling back to MemorySaver: '_GeneratorContextManager' object has no attribute 'setup'
```

### Root Cause
The `langgraph-checkpoint-redis` library's `RedisSaver.from_conn_string()` returns an async context manager in newer versions, but the code called `.setup()` on it directly as if it were a synchronous object.

The GCP Memorystore Redis instance (basic tier) also lacks the RedisJSON/RediSearch modules that `RedisSaver` requires.

### Current Status
The system gracefully falls back to `MemorySaver` (in-memory). This works for single-instance Cloud Run but means workflow state is lost on container restart. The archive download still works because it's served from the checkpointer during the same session.

### Lesson
Always verify that your managed Redis service supports the specific modules your library requires. GCP Memorystore Basic tier does not include RedisJSON — you need Redis Enterprise or a self-managed Redis Stack instance.

---

## Issue #9: Hardcoded API Key in Deployment Script

### Symptom
The `LANGCHAIN_API_KEY` was hardcoded directly in the `--set-env-vars` flag of the deployment script, visible in plain text in source control and in the Cloud Run console.

### Root Cause
Quick iteration during development led to hardcoding the key for convenience.

### Resolution
1. Created a secret named `langchain-api-key` in **Google Cloud Secret Manager**.
2. Granted `roles/secretmanager.secretAccessor` to the compute service account.
3. Replaced `--set-env-vars "LANGCHAIN_API_KEY=..."` with `--set-secrets="LANGCHAIN_API_KEY=langchain-api-key:latest"`.

See: [deploy-cloud-run.ps1:L36-40](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/scripts/deploy-cloud-run.ps1#L36-L40), [deploy-cloud-run.ps1:L64](file:///c:/MachineLearning/AI%20Software%20Delivery%20Team/scripts/deploy-cloud-run.ps1#L64)

### Lesson
Never hardcode secrets in deployment scripts or source code. Use a secrets manager (GCP Secret Manager, AWS Secrets Manager, HashiCorp Vault) and reference secrets by name at deploy time.

---

## Issue #10: Dropped Events in SSE Stream (Frontend)

### Symptom
In the HTML frontend (`app.js`), agents that finished very quickly (e.g., Product Owner and Architect) would sometimes only show the Architect's output. The Product Owner's log would vanish.

### Root Cause
The browser's `reader.read()` was fetching multiple SSE events in a single network chunk. The parser was splitting by `\n` and overriding the `eventData` before logging all of it.

### Resolution
Rewrote the `streamResponse` loop to buffer incomplete chunks and split by the official SSE delimiter `\n\n` (blank line), ensuring each complete frame is processed independently.

---

## Issue #11: Archiver Zipping Entire Virtual Environment

### Symptom
The downloadable project zip file was 50-200MB, taking a long time to download and risking Firestore limits again.

### Root Cause
The `archiver_node` used `shutil.make_archive()` on the entire workspace directory, which included the `.venv` folder created by the `run_command` tool.

### Resolution
Switched to `zipfile.ZipFile` and added an explicit `EXCLUDE_DIRS = {".venv", "__pycache__", ".pytest_cache"}` filter during `os.walk()`. The zip now only contains source code and `requirements.txt` (~10KB).

---

## Issue #12: Human Rejection "Immediately Bypassed"

### Symptom
When a user clicked "Reject" and provided feedback in the approval modal, the workflow would almost immediately return to the approval modal without rewriting any code.

### Root Cause
The `developer_agent` was extracting `human_feedback` from the state but only using it in the `except` block for the fallback message. It was **never appended to the `user_prompt`**. The Developer agent woke up, saw the code was already written, saw no complaints from QA/Sec/Rev, and instantly declared it was finished.

### Resolution
Injected `CRITICAL HUMAN FEEDBACK: {human_feedback}` directly into the developer's `user_prompt`. The agent now correctly reads the rejection reason and spends the required time rewriting the code.

---

## Summary Table

| # | Issue | Category | Severity | Resolution Time |
|---|-------|----------|----------|-----------------|
| 1 | Dockerfile layer ordering | Build | High | Quick fix |
| 2 | Artifact Registry IAM | Deployment | High | Quick fix |
| 3 | `return` vs `continue` in SSE parser | Frontend | Critical | Quick fix |
| 4 | `safety` interactive hang | Security tooling | Critical | Tool replacement |
| 5 | Stale `approved` flag loop | State management | Critical | Logic fix |
| 6 | Firestore 1MB limit crash | Data layer | Critical | 3-part fix |
| 7 | VPC egress blackhole | Networking | Critical | Config change |
| 8 | RedisSaver API mismatch | Infrastructure | Medium | Graceful fallback |
| 9 | Hardcoded API key | Security | Medium | Secret Manager migration |
