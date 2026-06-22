output "id" {
  description = "Azure OpenAI account resource ID."
  value       = azurerm_cognitive_account.this.id
}

output "name" {
  description = "Azure OpenAI account name."
  value       = azurerm_cognitive_account.this.name
}

output "endpoint" {
  description = "Azure OpenAI endpoint."
  value       = azurerm_cognitive_account.this.endpoint
}

output "principal_id" {
  description = "Azure OpenAI system-assigned identity principal ID."
  value       = azurerm_cognitive_account.this.identity[0].principal_id
}

output "deployment_names" {
  description = "Azure OpenAI deployment names."
  value       = { for key, deployment in azurerm_cognitive_deployment.this : key => deployment.name }
}
