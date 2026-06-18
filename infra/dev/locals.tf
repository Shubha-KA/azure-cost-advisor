locals {
  prefix = "${var.project_name}-${var.environment}"
  tags = merge(var.tags, {
    application = "azure-cost-advisor"
    environment = var.environment
    managed_by  = "terraform"
  })

  workload_service_accounts = {
    frontend = {
      namespace       = "finops-edge"
      service_account = "frontend"
    }
    api-gateway = {
      namespace       = "finops-edge"
      service_account = "api-gateway"
    }
    auth-service = {
      namespace       = "finops-auth"
      service_account = "auth-service"
    }
    collection-service = {
      namespace       = "finops-collection"
      service_account = "collection-service"
    }
    processing-service = {
      namespace       = "finops-processing"
      service_account = "processing-service"
    }
    ai-service = {
      namespace       = "finops-ai"
      service_account = "ai-service"
    }
    notification-service = {
      namespace       = "finops-notification"
      service_account = "notification-service"
    }
  }

  workload_names = toset(keys(local.workload_service_accounts))

  cosmos_containers = {
    tenants            = {}
    subscriptions      = {}
    tenantUsers        = {}
    tenantHealth       = {}
    costFacts          = {}
    resources          = {}
    recommendations    = {}
    processingMetadata = {}
    aiExecutions       = {}
    auditEvents        = {}
  }

  private_dns_zones = {
    cosmos = "privatelink.documents.azure.com"
    blob   = "privatelink.blob.core.windows.net"
    vault  = "privatelink.vaultcore.azure.net"
    acr    = "privatelink.azurecr.io"
    search = "privatelink.search.windows.net"
    openai = "privatelink.openai.azure.com"
  }
}
