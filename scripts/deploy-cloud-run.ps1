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

# FIXED: Grant Artifact Registry push permissions to resolve repository upload errors
gcloud projects add-iam-policy-binding "$ProjectId" `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/artifactregistry.writer" `
  --quiet

Write-Host "All infrastructure build permissions verified for: $ServiceAccount"
Write-Host ""
# -------------------------------------

Write-Host "Deploying backend..."
# Uses single continuous string block to bypass PowerShell array sorting bugs
gcloud run deploy $BackendService `
  --source backend/ `
  --region=$Region `
  --project=$ProjectId `
  --allow-unauthenticated `
  --memory=1Gi `
  --cpu=1 `
  --timeout=600 `
  --set-env-vars "AI_SDLC_USE_LLM=true,AI_SDLC_LLM_PROVIDER=vertex,GOOGLE_CLOUD_PROJECT=$ProjectId,GOOGLE_CLOUD_LOCATION=$Region,GEMINI_MODEL=gemini-2.5-flash-lite,GEMINI_TEMPERATURE=0.2,LOG_LEVEL=INFO"

Write-Host ""
Write-Host "Backend deployed!"

$BackendUrl = (gcloud run services describe $BackendService `
  --platform managed --region=$Region --project=$ProjectId --format='value(status.url)').Trim()

Write-Host "Backend URL: $BackendUrl"
Write-Host ""
Write-Host "Deploying frontend..."

gcloud run deploy $FrontendService `
  --source frontend/ `
  --region=$Region `
  --project=$ProjectId `
  --allow-unauthenticated `
  --memory=512Mi `
  --cpu=1 `
  --timeout=600 `
  --set-env-vars "API_BASE_URL=$BackendUrl,LOG_LEVEL=INFO"

Write-Host ""
Write-Host "Frontend deployed!"

$FrontendUrl = (gcloud run services describe $FrontendService `
  --platform managed --region=$Region --project=$ProjectId --format='value(status.url)').Trim()

Write-Host "Frontend URL: $FrontendUrl"
Write-Host ""
Write-Host "Deployment complete!"
