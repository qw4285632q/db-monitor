# Database Monitor - Docker Build Script for Windows
# Usage: .\build.ps1 [version]
# Example: .\build.ps1 v1.4.0

param(
    [string]$Version = "latest"
)

$ErrorActionPreference = "Stop"

# Configuration
$HARBOR_URL = "harbor.uzhicai.com"
$PROJECT = "midtool"
$IMAGE_NAME = "db-monitor"
$FULL_IMAGE = "${HARBOR_URL}/${PROJECT}/${IMAGE_NAME}"

Write-Host "================================" -ForegroundColor Green
Write-Host "Database Monitor - Docker Build" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# Full image tags
$IMAGE_LATEST = "${FULL_IMAGE}:latest"
$IMAGE_VERSIONED = "${FULL_IMAGE}:${Version}"

Write-Host "Building version: $Version" -ForegroundColor Green
Write-Host ""

# Step 1: Check Docker login
Write-Host "Step 1/5: Checking Docker login" -ForegroundColor Green
try {
    $dockerInfo = docker info 2>&1 | Out-String
    if ($dockerInfo -notmatch $HARBOR_URL) {
        Write-Host "Not logged in to Harbor, attempting login..." -ForegroundColor Yellow
        docker login $HARBOR_URL
    } else {
        Write-Host "Already logged in to $HARBOR_URL" -ForegroundColor Green
    }
} catch {
    Write-Host "Please login to Harbor:" -ForegroundColor Yellow
    docker login $HARBOR_URL
}

Write-Host ""
Write-Host "Step 2/5: Building Docker image" -ForegroundColor Green
docker build -t $IMAGE_LATEST -t $IMAGE_VERSIONED .

Write-Host ""
Write-Host "Step 3/5: Image build complete" -ForegroundColor Green
docker images | Select-String $IMAGE_NAME | Select-Object -First 5

Write-Host ""
Write-Host "Step 4/5: Pushing to Harbor" -ForegroundColor Green
Write-Host "Pushing ${IMAGE_LATEST}..." -ForegroundColor Yellow
docker push $IMAGE_LATEST

if ($Version -ne "latest") {
    Write-Host "Pushing ${IMAGE_VERSIONED}..." -ForegroundColor Yellow
    docker push $IMAGE_VERSIONED
}

Write-Host ""
Write-Host "Step 5/5: Cleanup" -ForegroundColor Green
Write-Host "Cleaning up dangling images..." -ForegroundColor Yellow
docker image prune -f

Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "Build and Push Complete!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "Image URLs:"
Write-Host "  $IMAGE_LATEST" -ForegroundColor Green
if ($Version -ne "latest") {
    Write-Host "  $IMAGE_VERSIONED" -ForegroundColor Green
}
Write-Host ""
Write-Host "To deploy on server:" -ForegroundColor Yellow
Write-Host "  docker pull $IMAGE_LATEST"
Write-Host "  docker run -d -p 5000:5000 -v /path/to/config.json:/app/config.json:ro $IMAGE_LATEST"
Write-Host ""
Write-Host "Or use docker-compose:"
Write-Host "  docker-compose up -d"
Write-Host ""
