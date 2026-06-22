output "id" {
  description = "AKS cluster resource ID."
  value       = azurerm_kubernetes_cluster.this.id
}

output "name" {
  description = "AKS cluster name."
  value       = azurerm_kubernetes_cluster.this.name
}

output "oidc_issuer_url" {
  description = "AKS OIDC issuer URL for Workload Identity."
  value       = azurerm_kubernetes_cluster.this.oidc_issuer_url
}

output "kubelet_identity_object_id" {
  description = "AKS kubelet identity object ID."
  value       = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id
}

output "node_resource_group" {
  description = "AKS node resource group."
  value       = azurerm_kubernetes_cluster.this.node_resource_group
}

output "user_node_pool_ids" {
  description = "User node pool IDs keyed by logical name."
  value       = { for key, pool in azurerm_kubernetes_cluster_node_pool.user : key => pool.id }
}
