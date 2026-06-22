output "identity_ids" {
  description = "Managed identity resource IDs keyed by workload name."
  value       = { for key, identity in azurerm_user_assigned_identity.this : key => identity.id }
}

output "client_ids" {
  description = "Managed identity client IDs keyed by workload name."
  value       = { for key, identity in azurerm_user_assigned_identity.this : key => identity.client_id }
}

output "principal_ids" {
  description = "Managed identity principal IDs keyed by workload name."
  value       = { for key, identity in azurerm_user_assigned_identity.this : key => identity.principal_id }
}
