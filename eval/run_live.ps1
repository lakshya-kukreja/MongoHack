# PowerShell Live Evaluation Runner (eval/run_live.ps1)
# Usage: .\eval\run_live.ps1

param(
    [string]$ApiBaseUrl = $(if ($env:API_BASE_URL) { $env:API_BASE_URL } else { "http://localhost:8000" }),
    [string]$IncidentId = $(if ($env:INCIDENT_ID) { $env:INCIDENT_ID } else { "incident_001" })
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   INCIDENT TIMELINE INVESTIGATOR - LIVE EVALUATION RUN   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Healthcheck probe
$HealthUrl = "$($ApiBaseUrl.TrimEnd('/'))/api/health"
Write-Host "`n[*] Step 1: Checking backend health at $HealthUrl..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 3
    Write-Host "[PASS] Backend is alive and reachable." -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Cannot reach backend server at $HealthUrl!" -ForegroundColor Red
    Write-Host "Please start Person 1's backend in another terminal window:" -ForegroundColor DarkYellow
    Write-Host "    cd backend" -ForegroundColor DarkYellow
    Write-Host "    uvicorn app.main:app --reload --port 8000" -ForegroundColor DarkYellow
    exit 1
}

# 2. Seed data
Write-Host "`n[*] Step 2: Seeding incident datasets (incident_001 & incident_000)..." -ForegroundColor Yellow
if (-not $env:MONGODB_URI) {
    python demo/seed.py --offline
} else {
    python demo/seed.py
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] demo/seed.py encountered an error!" -ForegroundColor Red
    exit 1
}
Write-Host "[PASS] Datasets loaded successfully." -ForegroundColor Green

# 3. Run Pytest in LIVE mode
Write-Host "`n[*] Step 3: Running Pytest evaluation suite in LIVE mode..." -ForegroundColor Yellow
$env:ADAPTER_MODE = "live"
$env:API_BASE_URL = $ApiBaseUrl
$env:INCIDENT_ID = $IncidentId

$startTime = Get-Date
python -m pytest eval/tests -v --tb=short
$exitCode = $LASTEXITCODE
$duration = ((Get-Date) - $startTime).TotalSeconds

# 4. Write results report
New-Item -ItemType Directory -Force -Path "eval/results" | Out-Null
$nowUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$statusStr = if ($exitCode -eq 0) { "PASSED (100%)" } else { "FAILED" }

python eval/run_live.py

exit $exitCode
