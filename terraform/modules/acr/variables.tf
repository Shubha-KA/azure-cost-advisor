variable "name" {
  description = "Azure Container Registry name."
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
  description = "ACR SKU."
  type        = string
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
