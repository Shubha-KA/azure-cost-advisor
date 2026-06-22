output "credential_ids" {
  description = "Federated identity credential IDs keyed by workload name."
  value       = { for key, credential in azurerm_federated_identity_credential.this : key => credential.id }
}

output "subjects" {
  description = "Federated identity subjects keyed by workload name."
  value       = { for key, credential in azurerm_federated_identity_credential.this : key => credential.subject }
}
