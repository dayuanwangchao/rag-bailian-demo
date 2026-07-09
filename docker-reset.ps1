$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host "Docker is not installed or not in PATH." -ForegroundColor Red
  exit 1
}

Write-Host "This will stop the stack and delete Docker volumes for this project." -ForegroundColor Yellow
$answer = Read-Host "Type RESET to continue"
if ($answer -ne "RESET") {
  Write-Host "Cancelled."
  exit 0
}

docker compose down -v
Write-Host "Enterprise RAG stack and Docker volumes removed." -ForegroundColor Green
