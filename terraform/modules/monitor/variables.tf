variable "name" {
  description = "Log Analytics workspace name."
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

variable "sku" {
  description = "Log Analytics SKU."
  type        = string
}

variable "retention_in_days" {
  description = "Workspace retention in days."
  type        = number
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
