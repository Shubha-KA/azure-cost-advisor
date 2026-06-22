variable "resource_group_name" {
  description = "Resource group name."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "identities" {
  description = "User-assigned managed identities keyed by workload name."
  type = map(object({
    name = string
  }))
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
