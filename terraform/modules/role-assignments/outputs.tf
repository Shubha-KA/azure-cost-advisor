output "assignment_ids" {
  description = "Role assignment resource IDs keyed by logical name."
  value       = { for key, assignment in azurerm_role_assignment.this : key => assignment.id }
}
