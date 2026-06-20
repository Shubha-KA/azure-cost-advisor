$ErrorActionPreference = "Stop"

Write-Host "Building API Gateway..."
docker build -t acrfinopsdevleyf6m.azurecr.io/api-gateway:latest -f deploy/Dockerfile.service --build-arg SERVICE_NAME=gateway_service .
Write-Host "Building Auth Service..."
docker build -t acrfinopsdevleyf6m.azurecr.io/auth-service:latest -f deploy/Dockerfile.service --build-arg SERVICE_NAME=auth_service .
Write-Host "Building Frontend..."
docker build -t acrfinopsdevleyf6m.azurecr.io/frontend:latest -f frontend/Dockerfile ./frontend

Write-Host "Pushing API Gateway..."
docker push acrfinopsdevleyf6m.azurecr.io/api-gateway:latest
Write-Host "Pushing Auth Service..."
docker push acrfinopsdevleyf6m.azurecr.io/auth-service:latest
Write-Host "Pushing Frontend..."
docker push acrfinopsdevleyf6m.azurecr.io/frontend:latest

Write-Host "Restarting Deployments..."
kubectl rollout restart deployment api-gateway -n finops-edge
kubectl rollout restart deployment auth-service -n finops-auth
kubectl rollout restart deployment frontend -n finops-edge

Write-Host "Done!"
