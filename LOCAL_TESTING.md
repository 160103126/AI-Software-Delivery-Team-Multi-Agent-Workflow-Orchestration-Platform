# Local Testing Guide - E2E

Simple steps to test the application locally without Cloud Run.

## Setup

### 1. Create local environment files

**`backend/.env.local`:**
```env
AI_SDLC_USE_LLM=false
LOG_LEVEL=INFO
```

**`frontend/.env.local`:**
```env
API_BASE_URL=http://127.0.0.1:8000
LOG_LEVEL=INFO
```

### 2. Install dependencies

```bash
# Backend
pip install -e backend/

# Frontend
pip install -e frontend/
```

## Run Locally

### Terminal 1 - Backend

```bash
cd backend/src
uvicorn ai_sdlc.api:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
Uvicorn running on http://127.0.0.1:8000
Press CTRL+C to quit
```

### Terminal 2 - Frontend

```bash
streamlit run frontend/streamlit_app.py --server.port 8501
```

You should see:
```
You can now view your Streamlit app in your browser.
Local URL: http://localhost:8501
```

---

## Test E2E (End-to-End)

### 1. Open Frontend
- Go to http://localhost:8501

### 2. Create a workflow
- Enter a request: "Build a user authentication system"
- Click submit
- You should see the workflow running through all agent steps

### 3. Approve workflow
- Once it reaches "Awaiting Approval", click "Approve"
- It should transition to deployment planning

### 4. Check Backend Logs
- Terminal 1 should show all agent logs
- Look for lines like: "Product Owner completed", "Architect completed", etc.

### 5. Verify Backend API
```bash
# Get all workflows
curl http://127.0.0.1:8000/workflows

# Get specific workflow (replace WORKFLOW_ID)
curl http://127.0.0.1:8000/workflows/{WORKFLOW_ID}

# View API docs
# Open http://127.0.0.1:8000/docs
```

---

## Troubleshooting

### "Firestore connection error"
**Expected!** Firestore isn't available locally. 

To disable Firestore locally, the app automatically falls back to in-memory storage when Firestore isn't available. Check the backend logs - should show:
```
Failed to initialize Firestore: ...
```

If you want to test with Firestore locally, install the emulator:
```bash
gcloud components install cloud-firestore-emulator
gcloud beta emulators firestore start
```

Then in another terminal set:
```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8081
```

### Frontend can't reach backend
Check `API_BASE_URL` in frontend `.env` - should be `http://127.0.0.1:8000`

### Port already in use
Change ports:
```bash
# Backend on 9000
uvicorn ai_sdlc.api:app --reload --host 0.0.0.0 --port 9000

# Frontend on 9501
streamlit run frontend/streamlit_app.py --server.port 9501
```

---

## What to Test

✅ **Core Workflow:**
- [ ] Submit workflow request
- [ ] See all agents process (Product Owner → Architect → Dev → QA → etc)
- [ ] Workflow reaches approval gate
- [ ] Approve workflow
- [ ] See deployment plan generated

✅ **Frontend UI:**
- [ ] Form accepts user input
- [ ] Streaming updates show in real-time
- [ ] Agents show in order
- [ ] Approval buttons work

✅ **Backend API:**
- [ ] POST /workflows creates workflow
- [ ] GET /workflows lists all workflows
- [ ] GET /workflows/{id} retrieves specific workflow
- [ ] POST /workflows/{id}/approval handles approval

✅ **Logs:**
- [ ] Backend logs show agent execution
- [ ] Frontend shows execution log
- [ ] No errors in terminal

---

## Next: Deploy to Cloud Run

Once E2E works locally:

1. Make sure Firestore/Redis are set up:
   ```bash
   bash scripts/setup-gcp-infrastructure.sh YOUR_PROJECT us-central1
   ```

2. Deploy:
   ```bash
   bash scripts/deploy-cloud-run.sh YOUR_PROJECT us-central1
   ```
