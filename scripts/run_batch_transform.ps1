<#
.SYNOPSIS
    Runs SageMaker batch transform using the latest approved model.
.DESCRIPTION
    Loads .env from project root, sets environment variables, then invokes
    ml/batch_transform.py which fetches the latest approved model from the
    Model Registry and submits a transform job.

    Prerequisites:
      1. terraform apply has been run (.env exists)
      2. SageMaker pipeline has completed and a model is Approved in the registry
      3. Input S3 path contains preprocessed CSV data (64 features, no target column)

    Run from project root:
      .\scripts\run_batch_transform.ps1 -InputS3 s3://your-bucket/processed/test/
      .\scripts\run_batch_transform.ps1 -InputS3 s3://your-bucket/processed/test/ -Wait
#>

param(
    [Parameter(Mandatory = $false)]
    [string]$InputS3 = $null,

    [switch]$Wait
)

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

# Parse and export .env
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#')) {
        $key, $value = $line -split '=', 2
        [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), 'Process')
    }
}

Write-Host "Loaded environment from .env" -ForegroundColor Green
Write-Host "  AWS_REGION                   = $env:AWS_REGION"
Write-Host "  SAGEMAKER_ROLE_ARN           = $env:SAGEMAKER_ROLE_ARN"
Write-Host "  FRAUDGUARD_S3_BUCKET         = $env:FRAUDGUARD_S3_BUCKET"
Write-Host "  FRAUDGUARD_MODEL_PACKAGE_GROUP = $env:FRAUDGUARD_MODEL_PACKAGE_GROUP"
Write-Host ""

$ArgsList = @()
if ($InputS3 -and $InputS3.StartsWith("s3://")) {
    $ArgsList += @("--input-s3", $InputS3)
}
if ($Wait) {
    $ArgsList += "--wait"
}

$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

& $PythonExe (Join-Path $ProjectRoot 'ml\batch_transform.py') @ArgsList

