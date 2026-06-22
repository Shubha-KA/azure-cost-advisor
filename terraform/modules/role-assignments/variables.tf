variable "role_assignments" {
  description = "Role assignments keyed by logical name."
  type = map(object({
    scope                = string
    role_definition_name = string
    principal_id         = string
  }))
}
