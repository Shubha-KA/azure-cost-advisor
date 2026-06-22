resource "azurerm_kubernetes_cluster" "this" {
  name                      = var.name
  resource_group_name       = var.resource_group_name
  location                  = var.location
  dns_prefix                = var.dns_prefix
  kubernetes_version        = var.kubernetes_version
  oidc_issuer_enabled       = true
  workload_identity_enabled = true
  tags                      = var.tags

  default_node_pool {
    name                         = var.system_node_pool.name
    vm_size                      = var.system_node_pool.vm_size
    vnet_subnet_id               = var.aks_subnet_id
    auto_scaling_enabled         = var.system_node_pool.enable_auto_scaling
    node_count                   = var.system_node_pool.node_count
    min_count                    = var.system_node_pool.min_count
    max_count                    = var.system_node_pool.max_count
    max_pods                     = var.system_node_pool.max_pods
    os_disk_size_gb              = var.system_node_pool.os_disk_size_gb
    only_critical_addons_enabled = true
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [var.cluster_identity_id]
  }

  kubelet_identity {
    client_id                 = var.kubelet_identity.client_id
    object_id                 = var.kubelet_identity.object_id
    user_assigned_identity_id = var.kubelet_identity.identity_id
  }

  network_profile {
    network_plugin = "azure"
    network_policy = var.network_policy
    service_cidr   = var.service_cidr
    dns_service_ip = var.dns_service_ip
  }

  azure_active_directory_role_based_access_control {
    azure_rbac_enabled = var.azure_rbac_enabled
    tenant_id          = var.tenant_id
  }

  oms_agent {
    log_analytics_workspace_id = var.log_analytics_workspace_id
  }
}

resource "azurerm_kubernetes_cluster_node_pool" "user" {
  for_each = var.user_node_pools

  name                  = each.value.name
  kubernetes_cluster_id = azurerm_kubernetes_cluster.this.id
  vm_size               = each.value.vm_size
  vnet_subnet_id        = var.aks_subnet_id
  mode                  = "User"
  auto_scaling_enabled  = each.value.enable_auto_scaling
  node_count            = each.value.node_count
  min_count             = each.value.min_count
  max_count             = each.value.max_count
  max_pods              = each.value.max_pods
  os_disk_size_gb       = each.value.os_disk_size_gb
  tags                  = var.tags
}
