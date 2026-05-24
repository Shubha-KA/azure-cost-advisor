# =============================================================================
# Terraform Outputs
# =============================================================================

output "resource_group_name" {
  description = "Deployed resource group name"
  value       = azurerm_resource_group.main.name
}

output "location" {
  description = "Deployment region"
  value       = azurerm_resource_group.main.location
}

# Networking
output "hub_vnet_id" {
  description = "Hub virtual network ID"
  value       = azurerm_virtual_network.hub.id
}

output "hub_vnet_name" {
  description = "Hub virtual network name"
  value       = azurerm_virtual_network.hub.name
}

output "spoke_vnet_id" {
  description = "Spoke virtual network ID"
  value       = azurerm_virtual_network.spoke.id
}

output "spoke_vnet_name" {
  description = "Spoke virtual network name"
  value       = azurerm_virtual_network.spoke.name
}

output "vnet_peering_hub_to_spoke_id" {
  description = "Hub-to-spoke VNet peering ID"
  value       = azurerm_virtual_network_peering.hub_to_spoke.id
}

output "vnet_peering_spoke_to_hub_id" {
  description = "Spoke-to-hub VNet peering ID"
  value       = azurerm_virtual_network_peering.spoke_to_hub.id
}

# Application Gateway
output "application_gateway_id" {
  description = "Application Gateway resource ID"
  value       = azurerm_application_gateway.main.id
}

output "application_gateway_public_ip" {
  description = "Public IP of Application Gateway (Internet entry point)"
  value       = azurerm_public_ip.appgw.ip_address
}

output "dashboard_url" {
  description = "Public URL for the Streamlit dashboard via Application Gateway"
  value       = "http://${azurerm_public_ip.appgw.ip_address}"
}

# VMSS
output "vmss_id" {
  description = "VM Scale Set resource ID"
  value       = azurerm_linux_virtual_machine_scale_set.streamlit.id
}

output "vmss_name" {
  description = "VM Scale Set name"
  value       = azurerm_linux_virtual_machine_scale_set.streamlit.name
}

output "internal_lb_private_ip" {
  description = "Internal Load Balancer private IP (spoke)"
  value       = azurerm_lb.spoke.frontend_ip_configuration[0].private_ip_address
}

output "streamlit_port" {
  description = "Streamlit server port"
  value       = var.streamlit_port
}
