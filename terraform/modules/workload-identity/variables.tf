variable "resource_group_name" {
  description = "Resource group name."
  type        = string
}

variable "federated_credentials" {
  description = "Federated identity credentials keyed by workload name."
  type = map(object({
    name        = string
    identity_id = string
    issuer      = string
    subject     = string
    audience    = list(string)
  }))
}
