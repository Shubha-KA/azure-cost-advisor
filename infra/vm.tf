# =============================================================================
# VM Scale Set — Streamlit dashboard (Spoke VNet)
#
# - Ubuntu 22.04 LTS
# - Cloud-init bootstraps Python, pip deps, and Streamlit as a systemd service
# - Password authentication
# - Internal Load Balancer exposes port 8501 to Application Gateway via peering
# - Azure Monitor autoscale (CPU-based, 1–N instances)
# =============================================================================

# -----------------------------------------------------------------------------
# Cloud-init script — installs app and starts Streamlit on boot
# -----------------------------------------------------------------------------
locals {
  cloud_init = base64encode(templatefile("${path.module}/cloud_init.tpl", {
    streamlit_port               = var.streamlit_port
    azure_openai_endpoint        = var.azure_openai_endpoint
    azure_openai_api_key         = var.azure_openai_api_key
    azure_openai_deployment_name = var.azure_openai_deployment_name
    azure_openai_embedding       = var.azure_openai_embedding_deployment
    azure_openai_api_version     = var.azure_openai_api_version
  }))
}

# -----------------------------------------------------------------------------
# Internal Load Balancer — routes AppGW → VMSS instances on port 8501
# -----------------------------------------------------------------------------
resource "azurerm_lb" "spoke" {
  name                = "lb-${var.project_name}-spoke-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"
  tags                = var.tags

  frontend_ip_configuration {
    name                          = "frontend-internal"
    subnet_id                     = azurerm_subnet.spoke_vmss.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_lb_backend_address_pool" "spoke" {
  name            = "bepool-streamlit"
  loadbalancer_id = azurerm_lb.spoke.id
}

resource "azurerm_lb_probe" "streamlit" {
  name                = "probe-streamlit"
  loadbalancer_id     = azurerm_lb.spoke.id
  protocol            = "Http"
  port                = var.streamlit_port
  request_path        = "/_stcore/health"
  interval_in_seconds = 15
  number_of_probes    = 3
}

resource "azurerm_lb_rule" "streamlit" {
  name                           = "rule-streamlit"
  loadbalancer_id                = azurerm_lb.spoke.id
  protocol                       = "Tcp"
  frontend_port                  = var.streamlit_port
  backend_port                   = var.streamlit_port
  frontend_ip_configuration_name = "frontend-internal"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.spoke.id]
  probe_id                       = azurerm_lb_probe.streamlit.id
  disable_outbound_snat          = true
}

# -----------------------------------------------------------------------------
# VM Scale Set — Ubuntu 22.04 LTS, password auth, cloud-init
# -----------------------------------------------------------------------------
resource "azurerm_linux_virtual_machine_scale_set" "streamlit" {
  name                            = "vmss-${var.project_name}-${random_string.suffix.result}"
  location                        = azurerm_resource_group.main.location
  resource_group_name             = azurerm_resource_group.main.name
  sku                             = var.vmss_vm_size
  instances                       = var.vmss_min_instances
  admin_username                  = var.vm_admin_username
  admin_password                  = var.vm_admin_password
  disable_password_authentication = false
  upgrade_mode                    = "Rolling"
  health_probe_id                 = azurerm_lb_probe.streamlit.id
  tags                            = var.tags

  # Cloud-init bootstrap
  custom_data = local.cloud_init

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 64
  }

  network_interface {
    name    = "nic-vmss-streamlit"
    primary = true

    ip_configuration {
      name                                   = "ipconfig-streamlit"
      primary                                = true
      subnet_id                              = azurerm_subnet.spoke_vmss.id
      load_balancer_backend_address_pool_ids = [azurerm_lb_backend_address_pool.spoke.id]
    }
  }

  rolling_upgrade_policy {
    max_batch_instance_percent              = 20
    max_unhealthy_instance_percent          = 20
    max_unhealthy_upgraded_instance_percent = 20
    pause_time_between_batches              = "PT0S"
  }

  automatic_instance_repair {
    enabled      = true
    grace_period = "PT30M"
  }

  depends_on = [
    azurerm_virtual_network_peering.hub_to_spoke,
    azurerm_virtual_network_peering.spoke_to_hub,
    azurerm_lb_rule.streamlit,
  ]

  lifecycle {
    ignore_changes = [instances]
  }
}

# -----------------------------------------------------------------------------
# Azure Monitor Autoscale — CPU-based scale out/in
# -----------------------------------------------------------------------------
resource "azurerm_monitor_autoscale_setting" "streamlit" {
  name                = "autoscale-${var.project_name}-vmss"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  target_resource_id  = azurerm_linux_virtual_machine_scale_set.streamlit.id
  tags                = var.tags

  profile {
    name = "cpu-autoscale"

    capacity {
      default = var.vmss_min_instances
      minimum = var.vmss_min_instances
      maximum = var.vmss_max_instances
    }

    # Scale OUT — add 1 instance when avg CPU > 70% for 5 minutes
    rule {
      metric_trigger {
        metric_name        = "Percentage CPU"
        metric_resource_id = azurerm_linux_virtual_machine_scale_set.streamlit.id
        time_grain         = "PT1M"
        statistic          = "Average"
        time_window        = "PT5M"
        time_aggregation   = "Average"
        operator           = "GreaterThan"
        threshold          = 70
      }
      scale_action {
        direction = "Increase"
        type      = "ChangeCount"
        value     = "1"
        cooldown  = "PT5M"
      }
    }

    # Scale IN — remove 1 instance when avg CPU < 25% for 10 minutes
    rule {
      metric_trigger {
        metric_name        = "Percentage CPU"
        metric_resource_id = azurerm_linux_virtual_machine_scale_set.streamlit.id
        time_grain         = "PT1M"
        statistic          = "Average"
        time_window        = "PT10M"
        time_aggregation   = "Average"
        operator           = "LessThan"
        threshold          = 25
      }
      scale_action {
        direction = "Decrease"
        type      = "ChangeCount"
        value     = "1"
        cooldown  = "PT10M"
      }
    }
  }

  notification {
    email {
      send_to_subscription_administrator    = true
      send_to_subscription_co_administrator = false
    }
  }
}
