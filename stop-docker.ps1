$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host "Docker is not installed or not in PATH." -ForegroundColor Red
  exit 1
}

docker compose down
Write-Host "Enterprise RAG stack stopped." -ForegroundColor Green
