# PowerShell Developer Startup Script for VARUNA
# Launches FastAPI Investigation Engine on port 8000 and Ops Console UI on port 8080.

$ScriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$ProjectDir = Split-Path -Path $ScriptDir -Parent
Set-Location $ProjectDir

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "VARUNA — DEVELOPER WORKSTATION STARTUP" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$env:PYTHONPATH = $ProjectDir

Write-Host "[1/2] Launching FastAPI Backend on http://localhost:8000..." -ForegroundColor Green
Start-Process -FilePath $VenvPython -ArgumentList "-m uvicorn backend.app.main:app --port 8000 --reload" -WindowStyle Normal

Write-Host "[2/2] Launching Ops Console UI on http://localhost:8080..." -ForegroundColor Green
Start-Process -FilePath $VenvPython -ArgumentList "-m http.server 8080 --directory ops_console" -WindowStyle Normal

Write-Host "`nVARUNA is running!" -ForegroundColor Yellow
Write-Host "-> Ops Console UI : http://localhost:8080" -ForegroundColor White
Write-Host "-> FastAPI API    : http://localhost:8000/docs" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
