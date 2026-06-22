variable "namespace_name" {
  description = "Service Bus namespace name."
  type        = string
}

variable "topic_name" {
  description = "Service Bus topic name."
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
  description = "Service Bus SKU."
  type        = string
}

variable "capacity" {
  description = "Service Bus Messaging Units for Premium SKU."
  type        = number
  default     = 0
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
}
