variable "name" {
  description = "Key Vault name."
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

variable "tenant_id" {
  description = "Microsoft Entra tenant ID."
  type        = string
}

variable "sku_name" {
  description = "Key Vault SKU."
  type        = string
}

variable "enable_rbac_authorization" {
  description = "Use Azure RBAC for Key Vault authorization."
  type        = bool
}

variable "purge_protection_enabled" {
  description = "Enable purge protection."
  type        = bool
}

variable "soft_delete_retention_days" {
  description = "Soft delete retention in days."
  type        = number
}

variable "public_network_access_enabled" {
  description = "Allow public network access."
  type        = bool
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
