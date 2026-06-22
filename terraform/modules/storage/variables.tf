variable "account_name" {
  description = "Storage account name."
  type        = string
}

variable "container_name" {
  description = "Blob container name."
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

variable "account_tier" {
  description = "Storage account tier."
  type        = string
}

variable "account_replication_type" {
  description = "Storage replication type."
  type        = string
}

variable "public_network_access_enabled" {
  description = "Allow public network access."
  type        = bool
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
