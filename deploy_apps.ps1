$ErrorActionPreference = "Stop"
$acr = "acrfinopsdevleyf6m.azurecr.io"
$tag = "latest"

$services = @(
    @{ name = "auth-service";         module = "src.microservices.auth_service" },
    @{ name = "api-gateway";          module = "src.microservices.gateway_service" },
    @{ name = "collection-service";   module = "src.microservices.collection_service" },
    @{ name = "processing-service";   module = "src.microservices.processing_service" },
    @{ name = "ai-service";           module = "src.microservices.ai_service" },
    @{ name = "notification-service"; module = "src.microservices.notification_service" }
)

# Build & push frontend
Write-Host "==> [1/7] Building frontend..." -ForegroundColor Cyan
docker build -t "$acr/frontend:$tag" -f frontend/Dockerfile frontend/
docker push "$acr/frontend:$tag"
Write-Host "frontend pushed OK" -ForegroundColor Green

# Build & push backend services
$i = 2
foreach ($svc in $services) {
    Write-Host "==> [$i/7] Building $($svc.name)..." -ForegroundColor Cyan
    docker build -t "$acr/$($svc.name):$tag" `
        -f deploy/Dockerfile.service `
        --build-arg "SERVICE_MODULE=$($svc.module)" `
        .
    docker push "$acr/$($svc.name):$tag"
    Write-Host "$($svc.name) pushed OK" -ForegroundColor Green
    $i++
}

Write-Host ""
Write-Host "All images pushed. Deploying to AKS..." -ForegroundColor Yellow
.\deploy\scripts\Deploy-Aks.ps1 -Environment dev -ImageTag $tag

Write-Host ""
Write-Host "==> Verifying pods..." -ForegroundColor Yellow
kubectl get pods --all-namespaces -l "app.kubernetes.io/part-of=azure-cost-advisor"
