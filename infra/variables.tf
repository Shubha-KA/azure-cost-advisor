# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------
variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "cost-advisor"
}

variable "location" {
  description = "Azure region for all resources (hub + spoke)"
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default = {
    project     = "azure-cost-advisor"
    managed_by  = "terraform"
    cost_center = "finops"
  }
}

# ---------------------------------------------------------------------------
# Networking — Hub-and-Spoke
# ---------------------------------------------------------------------------
variable "hub_vnet_address_space" {
  description = "Address space for hub VNet (Application Gateway)"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "spoke_vnet_address_space" {
  description = "Address space for spoke VNet (VMSS)"
  type        = list(string)
  default     = ["10.1.0.0/16"]
}

variable "hub_appgw_subnet_prefix" {
  description = "Hub subnet for Application Gateway (minimum /24)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "spoke_vmss_subnet_prefix" {
  description = "Spoke subnet for VMSS (Streamlit instances)"
  type        = string
  default     = "10.1.2.0/24"
}

# ---------------------------------------------------------------------------
# Application Gateway
# ---------------------------------------------------------------------------
variable "app_gateway_sku" {
  description = "Application Gateway SKU name (Standard_v2 or WAF_v2)"
  type        = string
  default     = "WAF_v2"
}

variable "app_gateway_capacity" {
  description = "Application Gateway capacity units"
  type        = number
  default     = 2
}

variable "streamlit_port" {
  description = "Streamlit server port (backend + health probe)"
  type        = number
  default     = 8501
}

# ---------------------------------------------------------------------------
# VM Scale Set (Streamlit runtime)
# ---------------------------------------------------------------------------
variable "vmss_vm_size" {
  description = "VM size for VMSS instances"
  type        = string
  default     = "Standard_B2s"
}

variable "vm_admin_username" {
  description = "Admin username for VMSS instances"
  type        = string
  default     = "azureuser"
}

variable "vm_admin_password" {
  description = "Admin password for VMSS instances (min 12 chars, requires complexity)"
  type        = string
  sensitive   = true
}

variable "vmss_min_instances" {
  description = "Minimum number of VMSS instances (autoscale floor)"
  type        = number
  default     = 1
}

variable "vmss_max_instances" {
  description = "Maximum number of VMSS instances (autoscale ceiling)"
  type        = number
  default     = 3
}

# ---------------------------------------------------------------------------
# Application secrets (.env equivalents — pass via TF_VAR_ in CI/CD)
# ---------------------------------------------------------------------------
variable "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint URL"
  type        = string
  default     = ""
  sensitive   = true
}

variable "azure_openai_api_key" {
  description = "Azure OpenAI API key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "azure_openai_api_version" {
  description = "Azure OpenAI API version"
  type        = string
  default     = "2024-08-01-preview"
}

variable "azure_openai_deployment_name" {
  description = "Azure OpenAI chat deployment name"
  type        = string
  default     = "gpt-4o"
}

variable "azure_openai_embedding_deployment" {
  description = "Azure OpenAI embedding deployment name"
  type        = string
  default     = "text-embedding-3-small"
}
