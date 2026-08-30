param (
    [ValidateSet("web", "server")]
    [string]$Mode = "web",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " 🛡️  FraudGuard -- Live DynamoDB Ops Console" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

switch ($Mode) {
    "web" {
        $ServerPath = Join-Path $ProjectRoot "dashboard\server.py"
        Write-Host "🚀 Starting Live DynamoDB Web Console on http://localhost:8000..." -ForegroundColor Green
        Start-Process "http://localhost:8000"
        python $ServerPath
        break
    }
    "server" {
        $ServerPath = Join-Path $ProjectRoot "dashboard\server.py"
        Write-Host "🚀 Starting Live DynamoDB Backend API on http://localhost:8000..." -ForegroundColor Green
        python $ServerPath
        break
    }
}
