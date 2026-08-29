<#
.SYNOPSIS
    Loads .env from project root and runs the SageMaker pipeline.
.DESCRIPTION
    Reads the Terraform-generated .env file, exports each variable into the
    current session, then invokes ml/sagemaker_pipeline.py.
    Run from the project root: .\scripts\run_pipeline.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot '.env'

if (-not (Test-Path $EnvFile)) {
    Write-Error @"
.env file not found at $EnvFile

Run 'terraform apply' in infra/terraform/ first — it auto-generates .env.
"@
    exit 1
}

# Parse .env: skip comments and blank lines, export each KEY=VALUE
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#')) {
        $key, $value = $line -split '=', 2
        [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), 'Process')
    }
}

Write-Host "Loaded environment from .env" -ForegroundColor Green
Write-Host "  AWS_REGION            = $env:AWS_REGION"
Write-Host "  SAGEMAKER_ROLE_ARN    = $env:SAGEMAKER_ROLE_ARN"
Write-Host "  FRAUDGUARD_S3_BUCKET  = $env:FRAUDGUARD_S3_BUCKET"
Write-Host ""

# Run the pipeline
Set-Location $ProjectRoot
python (Join-Path $ProjectRoot 'ml\sagemaker_pipeline.py')
