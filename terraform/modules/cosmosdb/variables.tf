variable "account_name" {
  description = "Cosmos DB account name."
  type        = string
}

variable "database_name" {
  description = "Cosmos DB SQL database name."
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

variable "consistency_level" {
  description = "Cosmos DB consistency level."
  type        = string
}

variable "database_throughput" {
  description = "Optional database throughput."
  type        = number
  default     = null
}

variable "containers" {
  description = "Cosmos SQL containers keyed by logical name."
  type = map(object({
    name                = string
    partition_key_paths = list(string)
    throughput          = optional(number)
  }))
}

variable "public_network_access_enabled" {
  description = "Allow public network access."
  type        = bool
}

variable "local_authentication_disabled" {
  description = "Disable Cosmos DB local keys."
  type        = bool
}

variable "free_tier_enabled" {
  description = "Enable Cosmos DB free tier."
  type        = bool
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
