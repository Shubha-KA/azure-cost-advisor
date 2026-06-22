variable "name" {
  description = "Virtual network name."
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

variable "address_space" {
  description = "Virtual network address spaces."
  type        = list(string)
}

variable "subnets" {
  description = "Subnets keyed by logical name."
  type = map(object({
    name              = string
    address_prefixes  = list(string)
    service_endpoints = optional(list(string), [])
  }))
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
