param(
  [switch]$Build,
  [switch]$Detached = $true
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

function Test-Command($name) {
  $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "docker")) {
  Write-Host "Docker is not installed or not in PATH." -ForegroundColor Red
  Write-Host "Install Docker Desktop first: https://www.docker.com/products/docker-desktop/"
  exit 1
}

try {
  docker info *> $null
} catch {
  Write-Host "Docker Desktop is installed but not running." -ForegroundColor Red
  Write-Host "Start Docker Desktop, wait until it says Running, then run this script again."
  exit 1
}

$envPath = Join-Path $projectRoot "backend\.env"
$examplePath = Join-Path $projectRoot "backend\.env.example"
if (-not (Test-Path $envPath)) {
  Copy-Item $examplePath $envPath
  Write-Host "Created backend\.env from backend\.env.example." -ForegroundColor Yellow
  Write-Host "Open backend\.env and fill DASHSCOPE_API_KEY before asking real RAG questions." -ForegroundColor Yellow
}

$args = @("compose", "up")
if ($Detached) {
  $args += "-d"
}
if ($Build) {
  $args += "--build"
}

Write-Host "Starting Enterprise RAG stack..." -ForegroundColor Cyan
docker @args

Write-Host ""
Write-Host "Enterprise RAG is starting. Useful URLs:" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5176"
Write-Host "Backend docs: http://localhost:8000/docs"
Write-Host "Backend health: http://localhost:8000/api/health"
Write-Host "Nginx entry: http://localhost:8080"
Write-Host "MinIO console: http://localhost:9001  (ragminio / ragminio123)"
Write-Host ""
Write-Host "Demo accounts:" -ForegroundColor Green
Write-Host "admin / admin123       system_admin"
Write-Host "kbadmin / kbadmin123   kb_admin"
Write-Host "editor / editor123     editor"
Write-Host "user / user123         reader"
Write-Host ""
Write-Host "Logs: docker compose logs -f backend frontend worker"
