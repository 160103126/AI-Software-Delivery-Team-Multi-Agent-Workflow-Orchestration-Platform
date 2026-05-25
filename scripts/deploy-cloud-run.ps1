# Simple Cloud Run deployment script for PowerShell

param(
    [string]$ProjectId = "",
    [string]$Region = "us-central1"
)

$BackendService = "ai-sdlc-backend"
$FrontendService = "ai-sdlc-frontend"

if (-not $ProjectId) {
    Write-Host "Usage: .\deploy-cloud-run.ps1 -ProjectId YOUR_PROJECT_ID [-Region REGION]"
    exit 1
}

Write-Host "Deploying to project: $ProjectId in region: $Region"
Write-Host ""

# --- FIXED SELF-HEALING PERMISSION CHECK ---
Write-Host "Verifying Cloud Build storage and repository access permissions..."
$ProjectNumber = (gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$ServiceAccount = $ProjectNumber + "-compute@developer.gserviceaccount.com"

# Grant storage access
gcloud projects add-iam-policy-binding "$ProjectId" `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/storage.admin" `
  --quiet

# Grant Artifact Registry push permissions to resolve repository upload errors
gcloud projects add-iam-policy-binding "$ProjectId" `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/artifactregistry.writer" `
  --quiet

# Grant Secret Manager access to read API keys
gcloud projects add-iam-policy-binding "$ProjectId" `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/secretmanager.secretAccessor" `
  --quiet

Write-Host "All infrastructure build permissions verified for: $ServiceAccount"
Write-Host ""
# -------------------------------------

Write-Host "Fetching Redis instance IP..."
$RedisIp = (gcloud redis instances describe ai-sdlc-redis --region=$Region --project=$ProjectId --format="value(host)").Trim()
$RedisUrl = "redis://$($RedisIp):6379/0"
Write-Host "Redis URL: $RedisUrl"

Write-Host "Deploying Unified Backend + Frontend App..."
# Uses single continuous string block to bypass PowerShell array sorting bugs
gcloud run deploy $BackendService `
  --source backend/ `
  --region=$Region `
  --project=$ProjectId `
  --allow-unauthenticated `
  --memory=1Gi `
  --cpu=1 `
  --timeout=600 `
  --network=default `
  --vpc-egress=private-ranges-only `
  --set-env-vars "AI_SDLC_USE_LLM=true,AI_SDLC_LLM_PROVIDER=vertex,GOOGLE_CLOUD_PROJECT=$ProjectId,GOOGLE_CLOUD_LOCATION=$Region,GEMINI_MODEL=gemini-2.5-pro,GEMINI_TEMPERATURE=0.2,LOG_LEVEL=INFO,LANGCHAIN_TRACING_V2=true,LANGCHAIN_PROJECT=ai-sdlc,LANGCHAIN_ENDPOINT=https://api.smith.langchain.com,REDIS_URL=$RedisUrl" `
  --set-secrets="LANGCHAIN_API_KEY=langchain-api-key:latest"

Write-Host ""
Write-Host "Deployment successful!"

$BackendUrl = (gcloud run services describe $BackendService `
  --platform managed --region=$Region --project=$ProjectId --format='value(status.url)').Trim()

Write-Host "Application URL: $BackendUrl"
Write-Host ""
Write-Host "Deployment complete!"
