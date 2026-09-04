<#
.SYNOPSIS
    FraudGuard - Test Real-Time Inference & Explainability Endpoint
.DESCRIPTION
    Sends sample transaction payloads (high-risk fraud and clean approval)
    to the real-time endpoint or local web dashboard server and prints
    the latency breakdown, ML fraud score, and Bedrock explanation.
.PARAMETER EndpointUrl
    The URL of the real-time endpoint (defaults to local dashboard server or API Gateway)
#>

[CmdletBinding()]
param (
    [string]$EndpointUrl = "http://localhost:8080/api/realtime-predict"
)

$ErrorActionPreference = "Stop"

Write-Host "`n=======================================================" -ForegroundColor Cyan
Write-Host " [>] FraudGuard Real-Time Inference Tester" -ForegroundColor Cyan
Write-Host " [*] Target Endpoint: $EndpointUrl" -ForegroundColor Gray
Write-Host "=======================================================`n" -ForegroundColor Cyan

# Test Case 1: High-Risk Transaction (Night Surge with Velocity Anomaly)
$HighRiskPayload = @{
    txn_id = "TEST-RT-$((Get-Date).Ticks.ToString().Substring(12))"
    TransactionAmt = 2850.00
    ProductCD = "R"
    card4 = "visa"
    card6 = "credit"
    hour_of_day = 3.0
    P_emaildomain = "protonmail.com"
    V189 = 5.0
    V201 = 5.0
    V258 = 4.0
    D2 = 1.0
    D8 = 1.5
    D10 = 1.0
    include_explanation = $true
} | ConvertTo-Json

Write-Host "[1/2] Sending High-Risk Suspicious Payload..." -ForegroundColor Yellow
$Start = Get-Date
try {
    $Resp1 = Invoke-RestMethod -Uri $EndpointUrl -Method Post -Body $HighRiskPayload -ContentType "application/json"
    $Elapsed = [math]::Round(((Get-Date) - $Start).TotalMilliseconds, 1)

    Write-Host "  -> Status: 200 OK ($Elapsed ms roundtrip)" -ForegroundColor Green
    Write-Host "  -> Txn ID:         $($Resp1.txn_id)" -ForegroundColor White
    Write-Host "  -> Fraud Score:    $($Resp1.fraud_score)" -ForegroundColor Red
    Write-Host "  -> Decision:       $($Resp1.decision)" -ForegroundColor Red
    Write-Host "  -> ML Latency:     $($Resp1.latency_ms.ml_inference) ms" -ForegroundColor Gray
    Write-Host "  -> Bedrock Latency:$($Resp1.latency_ms.bedrock_explainability) ms" -ForegroundColor Gray
    Write-Host "  -> Bedrock Claude Explanation:" -ForegroundColor Cyan
    Write-Host "     $($Resp1.explanation)" -ForegroundColor White
} catch {
    Write-Host "  [!] Request failed: $_" -ForegroundColor Red
}

Write-Host "`n-------------------------------------------------------`n" -ForegroundColor Gray

# Test Case 2: Legitimate Transaction (Daylight Retail)
$CleanPayload = @{
    txn_id = "TEST-RT-CLEAN-$((Get-Date).Ticks.ToString().Substring(12))"
    TransactionAmt = 34.50
    ProductCD = "W"
    card4 = "visa"
    card6 = "debit"
    hour_of_day = 14.0
    P_emaildomain = "gmail.com"
    include_explanation = $false
} | ConvertTo-Json

Write-Host "[2/2] Sending Clean Legitimate Payload..." -ForegroundColor Yellow
$Start = Get-Date
try {
    $Resp2 = Invoke-RestMethod -Uri $EndpointUrl -Method Post -Body $CleanPayload -ContentType "application/json"
    $Elapsed = [math]::Round(((Get-Date) - $Start).TotalMilliseconds, 1)

    Write-Host "  -> Status: 200 OK ($Elapsed ms roundtrip)" -ForegroundColor Green
    Write-Host "  -> Txn ID:         $($Resp2.txn_id)" -ForegroundColor White
    Write-Host "  -> Fraud Score:    $($Resp2.fraud_score)" -ForegroundColor Green
    Write-Host "  -> Decision:       $($Resp2.decision)" -ForegroundColor Green
    Write-Host "  -> ML Latency:     $($Resp2.latency_ms.ml_inference) ms" -ForegroundColor Gray
    Write-Host "  -> Bedrock Claude: Bypassed ($0 cost protection)" -ForegroundColor Cyan
} catch {
    Write-Host "  [!] Request failed: $_" -ForegroundColor Red
}

Write-Host "`n=======================================================" -ForegroundColor Cyan
Write-Host " [+] Real-Time Test Complete!" -ForegroundColor Green
Write-Host "=======================================================`n" -ForegroundColor Cyan
