variable "name" {
  description = "Azure OpenAI account name."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group name."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "sku_name" {
  description = "Azure OpenAI account SKU."
  type        = string
}

variable "custom_subdomain_name" {
  description = "Custom subdomain name."
  type        = string
}

variable "public_network_access_enabled" {
  description = "Allow public network access."
  type        = bool
}

variable "local_auth_enabled" {
  description = "Enable local key authentication."
  type        = bool
}

variable "deployments" {
  description = "Azure OpenAI model deployments keyed by logical name."
  type = map(object({
    name          = string
    model_format  = string
    model_name    = string
    model_version = string
    sku_name      = string
    capacity      = number
  }))
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
