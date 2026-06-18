variable "subscription_id" {
  type        = string
  description = "Azure subscription receiving the platform resources."
}

variable "platform_tenant_id" {
  type        = string
  description = "Microsoft Entra tenant that owns the SaaS platform."
}

variable "environment" {
  type = string
  validation {
    condition     = var.environment == "dev"
    error_message = "environment must be dev"
  }
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "project_name" {
  type    = string
  default = "finops"
}

variable "address_space" {
  type    = list(string)
  default = ["10.42.0.0/16"]
}

variable "aks_subnet_prefix" {
  type    = string
  default = "10.42.0.0/22"
}

variable "application_gateway_subnet_prefix" {
  type    = string
  default = "10.42.4.0/24"
}

variable "private_endpoint_subnet_prefix" {
  type    = string
  default = "10.42.5.0/24"
}

variable "system_node_vm_size" {
  type    = string
  default = "Standard_D4as_v5"
}

variable "system_node_count" {
  type    = number
  default = 1
}

variable "system_node_min_count" {
  type    = number
  default = 1
}

variable "system_node_max_count" {
  type    = number
  default = 2
}

variable "private_cluster_enabled" {
  type    = bool
  default = true
}

variable "admin_group_object_ids" {
  type        = list(string)
  description = "Entra group object IDs granted AKS cluster administrator access."
  default     = []
}

variable "aks_admin_principal_ids" {
  type        = set(string)
  description = "Entra user, group, or service-principal object IDs granted the Azure Kubernetes Service RBAC Cluster Admin role."
  default     = []
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "cosmos_serverless" {
  type    = bool
  default = true
}

variable "cosmos_max_throughput" {
  type    = number
  default = 1000
}

variable "search_sku" {
  type    = string
  default = "basic"
}

variable "search_location" {
  type        = string
  description = "Azure region for Azure AI Search. Defaults to the platform location when empty."
  default     = ""
}

variable "existing_openai_resource_group_name" {
  type        = string
  description = "Resource group containing the existing Azure AI Services/OpenAI account."
  default     = "open-ai-rg"
}

variable "existing_openai_account_name" {
  type        = string
  description = "Existing Azure AI Services/OpenAI account used by the platform."
  default     = "azure-cost-advisor-openai"
}

variable "openai_chat_deployment" {
  type    = string
  default = "gpt-4.1-mini"
}

variable "openai_embedding_deployment" {
  type    = string
  default = "text-embedding-3-small"
}

variable "create_private_endpoints" {
  type        = bool
  description = "Create private endpoints for supported PaaS resources."
  default     = false
}

variable "application_gateway_capacity" {
  type    = number
  default = 1
}

variable "entra_login_redirect_uris" {
  type        = list(string)
  description = "Exact OAuth callback URIs registered for the multi-tenant login application."
  default     = ["http://localhost:8000/api/auth/callback"]
}

variable "entra_post_logout_redirect_uri" {
  type    = string
  default = "http://localhost:3000"
}

variable "frontend_url" {
  type    = string
  default = "http://localhost:3000"
}

variable "api_cors_origins" {
  type    = string
  default = "http://localhost:3000"
}

variable "collection_interval_minutes" {
  type    = number
  default = 1440
}

variable "tags" {
  type    = map(string)
  default = {}
}
