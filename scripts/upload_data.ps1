<#
.SYNOPSIS
    Uploads raw transaction dataset to S3 bucket.
.DESCRIPTION
    Loads .env from project root, validates the S3 bucket configuration and
    raw data file existence, then uploads data/raw/train_transaction.csv to
    s3://{FRAUDGUARD_S3_BUCKET}/raw/train_transaction.csv.
    Run from project root: .\scripts\upload_data.ps1
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

$Bucket = $env:FRAUDGUARD_S3_BUCKET
if (-not $Bucket) {
    Write-Error "FRAUDGUARD_S3_BUCKET is not set in .env. Please re-run 'terraform apply'."
    exit 1
}

$SourceFile = Join-Path $ProjectRoot 'data\raw\train_transaction.csv'
if (-not (Test-Path $SourceFile)) {
    Write-Error @"
Raw dataset not found at $SourceFile.
Please ensure train_transaction.csv is placed in data/raw/ before running this script.
"@
    exit 1
}

$S3Destination = "s3://$Bucket/raw/train_transaction.csv"

Write-Host "Uploading raw transaction dataset to S3..." -ForegroundColor Cyan
Write-Host "  Source:      $SourceFile"
Write-Host "  Destination: $S3Destination"
Write-Host ""

aws s3 cp $SourceFile $S3Destination

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to upload dataset to S3. AWS CLI exited with code $LASTEXITCODE."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Data uploaded successfully to $S3Destination" -ForegroundColor Green
