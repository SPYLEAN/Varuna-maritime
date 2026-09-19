# VARUNA — Production Local Startup Script

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " VARUNA — Production Local Launcher" -ForegroundColor Cyan
Write-Host " Version: 2.0.0-rc1" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[ERROR] Virtual environment Python not found at: $VenvPython" -ForegroundColor Red
    exit 1
}

Write-Host "[1/2] Launching FastAPI Backend on http://localhost:8000..." -ForegroundColor Green
$BackendJob = Start-Job -ScriptBlock {
    param($pythonPath, $rootDir)
    $env:PYTHONPATH = $rootDir
    Set-Location $rootDir
    & $pythonPath -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --log-level info
} -ArgumentList $VenvPython, $RootDir

Start-Sleep -Seconds 3

Write-Host "[2/2] Launching Ops Console Frontend on http://localhost:8080..." -ForegroundColor Green
$FrontendJob = Start-Job -ScriptBlock {
    param($pythonPath, $opsDir)
    Set-Location $opsDir
    & $pythonPath -m http.server 8080 --directory $opsDir
} -ArgumentList $VenvPython, (Join-Path $RootDir "ops_console")

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " VARUNA IS NOW RUNNING LOCALLY" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Ops Console Workstation : http://localhost:8080" -ForegroundColor Yellow
Write-Host " FastAPI Backend Base   : http://localhost:8000" -ForegroundColor Yellow
Write-Host " Health Endpoint        : http://localhost:8000/health" -ForegroundColor Yellow
Write-Host " Readiness Endpoint     : http://localhost:8000/ready" -ForegroundColor Yellow
Write-Host " Interactive OpenAPI Docs: http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Press Ctrl+C or stop job to terminate services." -ForegroundColor Gray
