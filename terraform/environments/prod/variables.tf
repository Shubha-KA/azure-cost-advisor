variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "tenant_id" {
  description = "Microsoft Entra tenant ID."
  type        = string
}

variable "environment" {
  description = "Deployment environment represented by this root module."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group name."
  type        = string
}

variable "owner" {
  description = "Required Owner tag value."
  type        = string
}

variable "extra_tags" {
  description = "Optional Project, CostCenter, and other tags."
  type        = map(string)
  default     = {}
}

variable "helm_namespace" {
  description = "Kubernetes namespace used by the Helm release."
  type        = string
}

variable "workload_service_accounts" {
  description = "Workload Identity service accounts keyed by managed identity key."
  type        = map(string)
}

variable "network" {
  description = "Virtual network configuration."
  type = object({
    name          = string
    address_space = list(string)
    subnets = map(object({
      name              = string
      address_prefixes  = list(string)
      service_endpoints = optional(list(string), [])
    }))
  })
}

variable "monitor" {
  description = "Log Analytics configuration."
  type = object({
    name              = string
    sku               = string
    retention_in_days = number
  })
}

variable "application_insights" {
  description = "Application Insights configuration."
  type = object({
    name             = string
    application_type = string
  })
}

variable "acr" {
  description = "Azure Container Registry configuration."
  type = object({
    name = string
    sku  = string
  })
}

variable "keyvault" {
  description = "Key Vault configuration."
  type = object({
    name                          = string
    sku_name                      = string
    enable_rbac_authorization     = bool
    purge_protection_enabled      = bool
    soft_delete_retention_days    = number
    public_network_access_enabled = bool
  })
}

variable "cosmosdb" {
  description = "Cosmos DB configuration."
  type = object({
    account_name                  = string
    database_name                 = string
    consistency_level             = string
    database_throughput           = optional(number)
    public_network_access_enabled = bool
    local_authentication_disabled = bool
    free_tier_enabled             = bool
    containers = map(object({
      name                = string
      partition_key_paths = list(string)
      throughput          = optional(number)
    }))
  })
}

variable "servicebus" {
  description = "Service Bus configuration."
  type = object({
    namespace_name = string
    topic_name     = string
    sku            = string
    capacity       = optional(number, 0)
  })
}

variable "storage" {
  description = "Storage account configuration."
  type = object({
    account_name                  = string
    container_name                = string
    account_tier                  = string
    account_replication_type      = string
    public_network_access_enabled = bool
  })
}

variable "ai_search" {
  description = "Azure AI Search configuration."
  type = object({
    name                          = string
    sku                           = string
    replica_count                 = number
    partition_count               = number
    public_network_access_enabled = bool
    local_authentication_enabled  = bool
  })
}

variable "openai" {
  description = "Azure OpenAI configuration."
  type = object({
    name                          = string
    sku_name                      = string
    custom_subdomain_name         = string
    public_network_access_enabled = bool
    local_auth_enabled            = bool
    deployments = map(object({
      name          = string
      model_format  = string
      model_name    = string
      model_version = string
      sku_name      = string
      capacity      = number
    }))
  })
}

variable "managed_identities" {
  description = "User-assigned managed identities keyed by workload name."
  type = map(object({
    name = string
  }))
}

variable "aks" {
  description = "AKS configuration."
  type = object({
    name                 = string
    dns_prefix           = string
    kubernetes_version   = string
    subnet_key           = string
    cluster_identity_key = string
    kubelet_identity_key = string
    network_policy       = string
    service_cidr         = string
    dns_service_ip       = string
    azure_rbac_enabled   = bool
    system_node_pool = object({
      name                = string
      vm_size             = string
      node_count          = number
      enable_auto_scaling = bool
      min_count           = number
      max_count           = number
      max_pods            = number
      os_disk_size_gb     = number
    })
    user_node_pools = map(object({
      name                = string
      vm_size             = string
      node_count          = number
      enable_auto_scaling = bool
      min_count           = number
      max_count           = number
      max_pods            = number
      os_disk_size_gb     = number
    }))
  })
}
