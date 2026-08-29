<#
.SYNOPSIS
    Packages and deploys the FraudGuard Lambda function.
.DESCRIPTION
    Loads .env from project root, packages the lambda/ directory into
    lambda/lambda_package.zip (excluding __pycache__, bytecode, requirements.txt,
    and existing zip files), uploads the zip archive to S3, and updates Lambda
    function code if the function exists.
    Run from project root: .\scripts\deploy_lambda.ps1
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
    Write-Error "FRAUDGUARD_S3_BUCKET is not set in .env."
    exit 1
}

$FunctionName = if ($env:LAMBDA_FUNCTION_NAME) { $env:LAMBDA_FUNCTION_NAME } else { "fraudguard-bedrock-explain-dev" }
$Region = if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-1" }
$LambdaDir = Join-Path $ProjectRoot 'lambda'
$ZipPath = Join-Path $LambdaDir 'lambda_package.zip'

Write-Host "Deploying FraudGuard Lambda..." -ForegroundColor Cyan
Write-Host "  Lambda Dir:     $LambdaDir"
Write-Host "  Target Zip:     $ZipPath"
Write-Host "  S3 Bucket:      $Bucket"
Write-Host "  Function Name:  $FunctionName"
Write-Host "  AWS Region:     $Region"
Write-Host ""

# 1. Clean previous zip
if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}

# 2. Stage clean files into a temporary packaging folder
$TempStage = Join-Path ([System.IO.Path]::GetTempPath()) ("fg_lambda_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempStage -Force | Out-Null

try {
    # Copy files excluding __pycache__, bytecode, requirements.txt, and zip files
    Get-ChildItem -Path $LambdaDir -Recurse | Where-Object {
        -not $_.PSIsContainer -and
        $_.FullName -notmatch '[\\/](__pycache__|\.pytest_cache|\.venv|\.git)([\\/]|$)' -and
        $_.Extension -notin @('.pyc', '.pyo', '.pyd', '.zip') -and
        $_.Name -ne 'requirements.txt' -and
        $_.Name -ne 'lambda_package.zip'
    } | ForEach-Object {
        $relPath = $_.FullName.Substring($LambdaDir.Length).TrimStart('\', '/')
        $destPath = Join-Path $TempStage $relPath
        $destDir = Split-Path -Parent $destPath
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Copy-Item -Path $_.FullName -Destination $destPath -Force
    }

    # Create zip package
    Compress-Archive -Path "$TempStage\*" -DestinationPath $ZipPath -Force
    Write-Host "Package created: $ZipPath" -ForegroundColor Green
}
finally {
    if (Test-Path $TempStage) {
        Remove-Item -Recurse -Force $TempStage -ErrorAction SilentlyContinue
    }
}

# 3. Upload zip to S3
$S3ZipKey = "lambda/lambda_package.zip"
$S3ZipUri = "s3://$Bucket/$S3ZipKey"
Write-Host "Uploading package to $S3ZipUri..." -ForegroundColor Cyan
aws s3 cp $ZipPath $S3ZipUri

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to upload lambda package to S3. AWS CLI exited with code $LASTEXITCODE."
    exit $LASTEXITCODE
}

# 4. Check if Lambda function exists in AWS
Write-Host "Checking if Lambda function '$FunctionName' exists in AWS ($Region)..." -ForegroundColor Cyan
$FunctionExists = $false
try {
    $null = aws lambda get-function --function-name $FunctionName --region $Region 2>$null
    if ($LASTEXITCODE -eq 0) {
        $FunctionExists = $true
    }
} catch {
    $FunctionExists = $false
}

if ($FunctionExists) {
    Write-Host "Updating Lambda function code for '$FunctionName'..." -ForegroundColor Cyan
    aws lambda update-function-code `
        --function-name $FunctionName `
        --s3-bucket $Bucket `
        --s3-key $S3ZipKey `
        --region $Region | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to update Lambda function code. AWS CLI exited with code $LASTEXITCODE."
        exit $LASTEXITCODE
    }
    Write-Host "Lambda function '$FunctionName' updated successfully." -ForegroundColor Green
} else {
    Write-Host "Lambda function '$FunctionName' does not exist yet." -ForegroundColor Yellow
    Write-Host "Zip package uploaded to S3. Run 'terraform apply' in infra/terraform/ to create the Lambda function." -ForegroundColor Yellow
    exit 0
}
