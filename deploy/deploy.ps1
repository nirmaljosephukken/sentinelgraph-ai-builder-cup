# Deploy SentinelGraph to Cloud Run (Windows PowerShell, run from the repo root).
#
#   .\deploy\deploy.ps1 -Project my-gcp-project
#   .\deploy\deploy.ps1 -Project my-gcp-project -Region asia-south1 -Model gemini-3.5-flash-lite
#
# What it does:
#   1. enables Cloud Run, Cloud Build, Artifact Registry, Secret Manager and Vertex AI
#   2. copies TG_SECRET from .env into Secret Manager (value never printed); Gemini runs on Vertex AI, no API key
#   3. creates a service account that may read those secrets and call Gemini on Vertex AI
#   4. builds the Dockerfile with Cloud Build and deploys it to Cloud Run
# Re-running is safe: existing secrets get a new version, existing roles are kept.

param(
    [Parameter(Mandatory = $true)][string]$Project,
    [string]$Region = "asia-south1",
    [string]$Service = "sentinelgraph",
    [string]$Model = "",
    [string]$VertexLocation = "global"
)
$ErrorActionPreference = "Stop"

# ---- read .env (KEY=VALUE lines) without echoing anything
$envFile = Join-Path (Get-Location) ".env"
if (-not (Test-Path $envFile)) { throw "No .env in $(Get-Location). Run this from the repo root." }
$cfg = @{}
Get-Content $envFile | ForEach-Object {
    $l = $_.Trim()
    if ($l -and -not $l.StartsWith("#") -and $l.Contains("=")) {
        $k, $v = $l.Split("=", 2)
        $cfg[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
    }
}
foreach ($k in @("TG_HOST", "TG_SECRET")) { if (-not $cfg[$k]) { throw "$k missing in .env" } }
$graph = if ($cfg["TG_GRAPH"]) { $cfg["TG_GRAPH"] } else { "FraudGraph" }
if (-not $Model) { $Model = if ($cfg["GEMINI_MODEL"]) { $cfg["GEMINI_MODEL"] } else { "gemini-3.5-flash-lite" } }

function Test-Gcloud([string[]]$GArgs) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & gcloud @GArgs *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

gcloud config set project $Project | Out-Null
$number = gcloud projects describe $Project --format="value(projectNumber)"

Write-Host "1/4 Enabling APIs ..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
    secretmanager.googleapis.com aiplatform.googleapis.com

Write-Host "2/4 Secrets ..."
function Set-Secret([string]$name, [string]$value) {
    $tmp = New-TemporaryFile
    [IO.File]::WriteAllText($tmp.FullName, $value)   # no trailing newline
    if (Test-Gcloud @("secrets", "describe", $name)) { gcloud secrets versions add $name --data-file="$($tmp.FullName)" | Out-Null }
    else { gcloud secrets create $name --replication-policy=automatic --data-file="$($tmp.FullName)" | Out-Null }
    Remove-Item $tmp.FullName -Force
}
Set-Secret "tg-secret" $cfg["TG_SECRET"]
$secrets = "TG_SECRET=tg-secret:latest"
# No Gemini API key in the cloud: the agent and the case writer both call Gemini on Vertex AI as the service account.

Write-Host "3/4 Service account ..."
$sa = "$Service-run@$Project.iam.gserviceaccount.com"
$saExists = gcloud iam service-accounts list --filter="email=$sa" --format="value(email)"
if (-not $saExists) { gcloud iam service-accounts create "$Service-run" --display-name="SentinelGraph Cloud Run" | Out-Null }
gcloud secrets add-iam-policy-binding tg-secret --member="serviceAccount:$sa" `
    --role="roles/secretmanager.secretAccessor" --condition=None | Out-Null
gcloud projects add-iam-policy-binding $Project --member="serviceAccount:$sa" --role="roles/aiplatform.user" `
    --condition=None | Out-Null
# Cloud Build (source deploys) runs as the default compute service account on newer projects
gcloud projects add-iam-policy-binding $Project `
    --member="serviceAccount:$number-compute@developer.gserviceaccount.com" `
    --role="roles/run.builder" --condition=None | Out-Null

Write-Host "4/4 Build and deploy (takes a few minutes) ..."
# create the image repository up front: letting `run deploy` create it on a new project can time out
if (-not (Test-Gcloud @("artifacts", "repositories", "describe", "cloud-run-source-deploy", "--location=$Region"))) {
    gcloud artifacts repositories create cloud-run-source-deploy --repository-format=docker `
        --location=$Region --description="Cloud Run source deploys" --quiet
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Artifact Registry repository. Wait a few minutes and run the script again." }
}
$vars = "TG_HOST=$($cfg['TG_HOST']),TG_GRAPH=$graph,GOOGLE_GENAI_USE_VERTEXAI=TRUE," +
        "GOOGLE_CLOUD_PROJECT=$Project,GOOGLE_CLOUD_LOCATION=$VertexLocation,ADK_MODEL=$Model,GEMINI_MODEL=$Model," +
        "LLM_PROVIDER=gemini"
gcloud run deploy $Service --source . --region $Region --service-account $sa `
    --set-env-vars $vars --set-secrets $secrets `
    --allow-unauthenticated --session-affinity --timeout 3600 `
    --cpu 2 --memory 2Gi --min-instances 0 --max-instances 2 --concurrency 20
if ($LASTEXITCODE -ne 0) { throw "Deploy failed (see the error above). Running the script again is safe." }

$url = gcloud run services describe $Service --region $Region --format="value(status.url)"
Write-Host ""
Write-Host "Deployed: $url"
