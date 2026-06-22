variable "name" {
  description = "Azure AI Search service name."
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
  description = "Search SKU."
  type        = string
}

variable "replica_count" {
  description = "Search replica count."
  type        = number
}

variable "partition_count" {
  description = "Search partition count."
  type        = number
}

variable "public_network_access_enabled" {
  description = "Allow public network access."
  type        = bool
}

variable "local_authentication_enabled" {
  description = "Enable local API key authentication."
  type        = bool
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
