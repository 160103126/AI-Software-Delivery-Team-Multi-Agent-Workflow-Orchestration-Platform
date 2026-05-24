# Cloud Run Deployment Guide

This guide covers deploying the AI Software Delivery Team application to Google Cloud Run with Firestore, Redis, and Cloud Logging.

## Prerequisites

- GCP account with billing enabled
- `gcloud` CLI installed ([install](https://cloud.google.com/sdk/docs/install))
- Docker (for local testing)
- Authenticated gcloud: `gcloud auth login`

## Architecture

```
Cloud Run Backend (FastAPI + Uvicorn)
  ├─ Firestore (Workflow storage)
  ├─ Memorystore Redis (LLM response caching)
  └─ Cloud Logging (Logs)

Cloud Run Frontend (Streamlit)
  └─ Calls Backend API
```

---

## Deployment Steps

### 1. Set GCP Project

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"  # Or your preferred region

gcloud config set project $PROJECT_ID
```

### 2. Setup Infrastructure (One-time)

Creates Firestore, Memorystore Redis, and grants IAM permissions.

**On Linux/MacOS/Cloud Shell:**
```bash
bash scripts/setup-gcp-infrastructure.sh $PROJECT_ID $REGION
```

**On Windows (PowerShell):**
```powershell
gcloud firestore databases create --region=$REGION --project=$PROJECT_ID
gcloud redis instances create ai-sdlc-redis --size=1 --region=$REGION --project=$PROJECT_ID
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member=serviceAccount:$PROJECT_ID@appspot.gserviceaccount.com `
  --role=roles/datastore.user
```

### 3. Deploy Services

**Option A: Full Deployment (Linux/MacOS/Cloud Shell)**
```bash
bash scripts/deploy-cloud-run.sh $PROJECT_ID $REGION
```

**Option B: Full Deployment (Windows PowerShell)**
```powershell
.\scripts\deploy-cloud-run.ps1 -ProjectId $PROJECT_ID -Region $REGION
```

**Option C: Deploy Only Backend**
```bash
bash scripts/deploy-cloud-run.sh $PROJECT_ID $REGION
# OR (PowerShell)
.\scripts\deploy-cloud-run.ps1 -ProjectId $PROJECT_ID -Region $REGION -BackendOnly
```

**Option D: Dry Run (preview commands without executing)**
```bash
DRY_RUN=true bash scripts/deploy-cloud-run.sh $PROJECT_ID $REGION
```

### 4. Configure Redis Connection

After deployment, add Redis URL to backend environment variables:

```bash
# Get Redis host
REDIS_HOST=$(gcloud redis instances describe ai-sdlc-redis \
  --region=$REGION \
  --format='value(host)')

REDIS_PORT=6379

# Update backend service
gcloud run services update ai-sdlc-backend \
  --region=$REGION \
  --update-env-vars REDIS_URL=redis://$REDIS_HOST:$REDIS_PORT
```

---

## Post-Deployment

### View Logs

**Backend logs:**
```bash
gcloud run services logs read ai-sdlc-backend --region=$REGION
```

**Frontend logs:**
```bash
gcloud run services logs read ai-sdlc-frontend --region=$REGION
```

**Tail logs in real-time:**
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.service_name=ai-sdlc-backend" \
  --limit 50 --follow
```

### Get Service URLs

```bash
# Backend
gcloud run services describe ai-sdlc-backend --region=$REGION --format='value(status.url)'

# Frontend
gcloud run services describe ai-sdlc-frontend --region=$REGION --format='value(status.url)'
```

### Update Environment Variables

```bash
gcloud run services update ai-sdlc-backend \
  --region=$REGION \
  --update-env-vars \
    GEMINI_MODEL=gemini-2.0-pro,\
    LOG_LEVEL=DEBUG
```

### View Firestore Data

```bash
gcloud firestore databases describe
```

Or use GCP Console: https://console.cloud.google.com/firestore

---

## Configuration

### Environment Variables

**Backend:**
- `AI_SDLC_USE_LLM` - Enable/disable LLM (default: true)
- `AI_SDLC_LLM_PROVIDER` - Provider: "vertex" or "google" (default: vertex)
- `GOOGLE_CLOUD_PROJECT` - GCP project ID
- `GOOGLE_CLOUD_LOCATION` - Region (default: global)
- `GEMINI_MODEL` - Model name (default: gemini-2.5-flash-lite)
- `GEMINI_TEMPERATURE` - Temperature 0-1 (default: 0.2)
- `REDIS_URL` - Redis connection string (optional, caching disabled if not set)
- `LOG_LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)

**Frontend:**
- `API_BASE_URL` - Backend API URL (default: http://127.0.0.1:8000)

### Scaling

Update resource allocation:

```bash
gcloud run services update ai-sdlc-backend \
  --region=$REGION \
  --memory=2Gi \
  --cpu=2 \
  --max-instances=100
```

---

## Troubleshooting

### Backend won't connect to Firestore

Check service account permissions:
```bash
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --format='table(bindings.role)' \
  --filter="bindings.members:serviceAccount:$PROJECT_ID@appspot.gserviceaccount.com"
```

Should have:
- `roles/datastore.user`
- `roles/aiplatform.user` (for Vertex AI)
- `roles/logging.logWriter` (for Cloud Logging)

### Redis connection fails

Check Redis instance is running:
```bash
gcloud redis instances describe ai-sdlc-redis --region=$REGION
```

Verify REDIS_URL format: `redis://HOST:6379` (no password by default)

### Firestore read/write errors

Enable Firestore API:
```bash
gcloud services enable firestore.googleapis.com
```

### Frontend can't reach backend

Verify backend URL in frontend environment variables:
```bash
gcloud run services describe ai-sdlc-frontend --region=$REGION --format='value(spec.template.spec.containers[0].env)'
```

---

## Cost Estimation

| Service | Tier | Monthly Cost |
|---------|------|--------------|
| Cloud Run | 2M requests/month | ~$5-15 |
| Firestore | 1M reads + storage | ~$1-5 |
| Memorystore Redis | 1 GB instance | ~$7-10 |
| Cloud Logging | < 50GB logs | Free |
| Vertex AI | Pay per request | ~$0.001-0.01 per request |

**Total:** ~$15-30/month for light usage

---

## Local Development

### Without Cloud Run

```bash
# Install dependencies
pip install -e backend/
pip install -e frontend/

# Run backend
cd backend/src
uvicorn ai_sdlc.api:app --reload

# Run frontend (separate terminal)
streamlit run frontend/streamlit_app.py
```

### With Docker (local)

```bash
# Backend
docker build -t ai-sdlc-backend backend/
docker run -p 8000:8080 \
  -e AI_SDLC_USE_LLM=false \
  ai-sdlc-backend

# Frontend
docker run -p 8501:8080 \
  -e API_BASE_URL=http://host.docker.internal:8000 \
  ai-sdlc-frontend
```

---

## Cleanup

Delete all resources:

```bash
# Delete Cloud Run services
gcloud run services delete ai-sdlc-backend ai-sdlc-frontend --region=$REGION

# Delete Redis
gcloud redis instances delete ai-sdlc-redis --region=$REGION

# Delete Firestore (careful!)
gcloud firestore databases delete
```

---

## Support

For issues:
1. Check logs: `gcloud run services logs read ai-sdlc-backend`
2. Verify IAM permissions
3. Ensure APIs are enabled: `gcloud services list --enabled`
4. Check quotas: https://console.cloud.google.com/quotas
