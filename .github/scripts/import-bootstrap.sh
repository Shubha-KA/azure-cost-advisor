#!/bin/bash
set -e

# Change to the bootstrap directory where terraform init has already been run
cd infra/bootstrap

echo "========================================="
echo "Terraform Import Existing Resources"
echo "========================================="

# The project name corresponds to the default in variables.tf
PROJECT_NAME="finops"
RG_NAME="rg-${PROJECT_NAME}-tfstate"

# Ensure subscription is used
SUB_ARG=""
if [ -n "$ARM_SUBSCRIPTION_ID" ]; then
    SUB_ARG="--subscription $ARM_SUBSCRIPTION_ID"
fi

# 1. Resource Group
echo "Checking if Resource Group exists..."
if ! terraform state show azurerm_resource_group.state >/dev/null 2>&1; then
    RG_ID=$(az group show -n "$RG_NAME" $SUB_ARG --query id -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$RG_ID" ]; then
        echo "Resource Group exists, importing..."
        terraform import -var-file=environments/platform.tfvars azurerm_resource_group.state "$RG_ID"
        echo "Resource exists and imported"
    else
        echo "Resource not found, will be created"
    fi
else
    echo "Resource already in state"
fi

# 2. Storage Account
echo "Checking Storage Account..."
if ! terraform state show azurerm_storage_account.state >/dev/null 2>&1; then
    SA_NAME=$(az storage account list -g "$RG_NAME" $SUB_ARG --query "[?starts_with(name, 'st${PROJECT_NAME}tf')].name | [0]" -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$SA_NAME" ]; then
        SA_ID=$(az storage account show -n "$SA_NAME" -g "$RG_NAME" $SUB_ARG --query id -o tsv | tr -d '\r')
        echo "Storage Account exists ($SA_NAME), importing..."
        terraform import -var-file=environments/platform.tfvars azurerm_storage_account.state "$SA_ID"
        echo "Resource exists and imported"
        
        # 3. Import the random string suffix
        if ! terraform state show random_string.suffix >/dev/null 2>&1; then
            SUFFIX=${SA_NAME: -6}
            echo "Importing random_string.suffix with value $SUFFIX"
            terraform import -var-file=environments/platform.tfvars random_string.suffix "$SUFFIX"
        fi
    else
        echo "Resource not found, will be created"
    fi
else
    echo "Resource already in state"
    SA_NAME=$(terraform state show azurerm_storage_account.state | grep -o 'name * = "st.*"' | awk -F'"' '{print $2}' || true)
fi

# 4. Storage Container
if [ -n "$SA_NAME" ]; then
    echo "Checking Storage Container..."
    if ! terraform state show azurerm_storage_container.state >/dev/null 2>&1; then
        CONTAINER_EXISTS=$(az storage container exists --account-name "$SA_NAME" -n tfstate --auth-mode login $SUB_ARG --query exists -o tsv 2>/dev/null | tr -d '\r' || true)
        if [ "$CONTAINER_EXISTS" = "true" ]; then
            SA_ID=$(az storage account show -n "$SA_NAME" -g "$RG_NAME" $SUB_ARG --query id -o tsv | tr -d '\r')
            CONTAINER_ID="${SA_ID}/blobServices/default/containers/tfstate"
            echo "Storage Container exists, importing..."
            terraform import -var-file=environments/platform.tfvars azurerm_storage_container.state "$CONTAINER_ID"
            echo "Resource exists and imported"
        else
            echo "Resource not found, will be created"
        fi
    else
        echo "Resource already in state"
    fi
else
    echo "Skipping container import because Storage Account does not exist in Azure."
fi

# 5. Virtual Network
VNET_NAME="vnet-${PROJECT_NAME}-tfstate"
echo "Checking Virtual Network..."
if ! terraform state show azurerm_virtual_network.state >/dev/null 2>&1; then
    VNET_ID=$(az network vnet show -n "$VNET_NAME" -g "$RG_NAME" $SUB_ARG --query id -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$VNET_ID" ]; then
        echo "Virtual Network exists, importing..."
        terraform import -var-file=environments/platform.tfvars azurerm_virtual_network.state "$VNET_ID"
        echo "Resource exists and imported"
    else
        echo "Resource not found, will be created"
    fi
else
    echo "Resource already in state"
fi

# 6. Subnet
SUBNET_NAME="snet-private-endpoints"
echo "Checking Subnet..."
if ! terraform state show azurerm_subnet.private_endpoints >/dev/null 2>&1; then
    SUBNET_ID=$(az network vnet subnet show -n "$SUBNET_NAME" --vnet-name "$VNET_NAME" -g "$RG_NAME" $SUB_ARG --query id -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$SUBNET_ID" ]; then
        echo "Subnet exists, importing..."
        terraform import -var-file=environments/platform.tfvars azurerm_subnet.private_endpoints "$SUBNET_ID"
        echo "Resource exists and imported"
    else
        echo "Resource not found, will be created"
    fi
else
    echo "Resource already in state"
fi

# 7. Private DNS Zone
DNS_ZONE_NAME="privatelink.blob.core.windows.net"
echo "Checking Private DNS Zone..."
if ! terraform state show azurerm_private_dns_zone.blob >/dev/null 2>&1; then
    DNS_ZONE_ID=$(az network private-dns zone show -n "$DNS_ZONE_NAME" -g "$RG_NAME" $SUB_ARG --query id -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$DNS_ZONE_ID" ]; then
        echo "Private DNS Zone exists, importing..."
        terraform import -var-file=environments/platform.tfvars azurerm_private_dns_zone.blob "$DNS_ZONE_ID"
        echo "Resource exists and imported"
    else
        echo "Resource not found, will be created"
    fi
else
    echo "Resource already in state"
fi

# 8. DNS Zone Link
VNET_LINK_NAME="terraform-state-blob-link"
echo "Checking Private DNS Zone Link..."
if ! terraform state show azurerm_private_dns_zone_virtual_network_link.blob >/dev/null 2>&1; then
    VNET_LINK_ID=$(az network private-dns link vnet show -n "$VNET_LINK_NAME" -g "$RG_NAME" -z "$DNS_ZONE_NAME" $SUB_ARG --query id -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$VNET_LINK_ID" ]; then
        echo "Private DNS Zone Link exists, importing..."
        terraform import -var-file=environments/platform.tfvars azurerm_private_dns_zone_virtual_network_link.blob "$VNET_LINK_ID"
        echo "Resource exists and imported"
    else
        echo "Resource not found, will be created"
    fi
else
    echo "Resource already in state"
fi

# 9. Private Endpoint
PE_NAME="pe-${PROJECT_NAME}-tfstate-blob"
echo "Checking Private Endpoint..."
if ! terraform state show azurerm_private_endpoint.state_blob >/dev/null 2>&1; then
    PE_ID=$(az network private-endpoint show -n "$PE_NAME" -g "$RG_NAME" $SUB_ARG --query id -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$PE_ID" ]; then
        echo "Private Endpoint exists, importing..."
        terraform import -var-file=environments/platform.tfvars azurerm_private_endpoint.state_blob "$PE_ID"
        echo "Resource exists and imported"
    else
        echo "Resource not found, will be created"
    fi
else
    echo "Resource already in state"
fi

# 10. Clean up any existing locks in Azure so Terraform isn't blocked
echo "Checking for orphaned Management Locks to delete..."
RG_LOCK_ID=$(az lock list --resource-group "$RG_NAME" $SUB_ARG --query "[?name=='terraform-state-resource-group-delete-lock'].id | [0]" -o tsv 2>/dev/null | tr -d '\r' || true)
if [ -n "$RG_LOCK_ID" ]; then
    echo "Deleting Resource Group Lock ($RG_LOCK_ID)..."
    az lock delete --ids "$RG_LOCK_ID"
fi

if [ -n "$SA_ID" ]; then
    SA_LOCK_ID=$(az lock list --resource "$SA_ID" $SUB_ARG --query "[?name=='terraform-state-storage-delete-lock'].id | [0]" -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$SA_LOCK_ID" ]; then
        echo "Deleting Storage Account Lock ($SA_LOCK_ID)..."
        az lock delete --ids "$SA_LOCK_ID"
    fi
    
    CONTAINER_ID="${SA_ID}/blobServices/default/containers/tfstate"
    CONT_LOCK_ID=$(az lock list --resource "$CONTAINER_ID" $SUB_ARG --query "[?name=='terraform-state-container-delete-lock'].id | [0]" -o tsv 2>/dev/null | tr -d '\r' || true)
    if [ -n "$CONT_LOCK_ID" ]; then
        echo "Deleting Container Lock ($CONT_LOCK_ID)..."
        az lock delete --ids "$CONT_LOCK_ID"
    fi
fi

echo "========================================="
echo "Import process completed successfully."
echo "========================================="
