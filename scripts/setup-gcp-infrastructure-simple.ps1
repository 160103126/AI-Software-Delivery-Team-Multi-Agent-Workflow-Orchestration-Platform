# Simple GCP infrastructure setup

param(
    [string]$ProjectId = "",
    [string]$Region = "us-central1"
)

if (-not $ProjectId) {
    Write-Host "Usage: .\setup-gcp-infrastructure-simple.ps1 -ProjectId YOUR_PROJECT_ID [-Region REGION]"
    exit 1
}

Write-Host "Setting up infrastructure for project: $ProjectId in region: $Region"
Write-Host ""

Write-Host "1. Enabling APIs..."
gcloud services enable firestore.googleapis.com --project=$ProjectId
gcloud services enable redis.googleapis.com --project=$ProjectId
gcloud services enable run.googleapis.com --project=$ProjectId
gcloud services enable logging.googleapis.com --project=$ProjectId
gcloud services enable aiplatform.googleapis.com --project=$ProjectId

Write-Host ""
Write-Host "2. Creating Firestore database..."
# Added a fallback try/catch case so it won't crash if the database is already built
try {
    gcloud firestore databases create --location=$Region --type=firestore-native --project=$ProjectId
} catch {
    Write-Host "Firestore database already exists, skipping..."
}

Write-Host ""
Write-Host "3. Creating Redis instance..."
try {
    gcloud redis instances create ai-sdlc-redis --size=1 --region=$Region --project=$ProjectId
} catch {
    Write-Host "Redis instance already exists, skipping..."
}

Write-Host ""
Write-Host "4. Granting service account permissions..."
# FIXED: Casing matched properly to $ProjectId to capture the input parameter
$ProjectNumber = (gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$ServiceAccount = "$ProjectNumber-compute@developer.gserviceaccount.com"

Write-Host "Configuring access permissions for: $ServiceAccount"

gcloud projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/datastore.user" `
  --quiet

gcloud projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/logging.logWriter" `
  --quiet

gcloud projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/aiplatform.user" `
  --quiet

Write-Host ""
Write-Host "Done! Infrastructure is ready."
Write-Host ""
Write-Host "Next: Deploy with:"
Write-Host "  .\deploy-cloud-run-simple.ps1 -ProjectId $ProjectId -Region $Region"
