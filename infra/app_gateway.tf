# =============================================================================
# Application Gateway — public entry point routing to Streamlit VMSS backend
# =============================================================================

resource "azurerm_application_gateway" "main" {
  name                = "appgw-${var.project_name}-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
  enable_http2        = true

  sku {
    name     = var.app_gateway_sku
    tier     = var.app_gateway_sku
    capacity = var.app_gateway_capacity
  }

  gateway_ip_configuration {
    name      = "gw-ip-config"
    subnet_id = azurerm_subnet.hub_appgw.id
  }

  # Frontend — Internet-facing listener on port 80
  frontend_port {
    name = "http-port"
    port = 80
  }

  frontend_ip_configuration {
    name                 = "frontend-ip"
    public_ip_address_id = azurerm_public_ip.appgw.id
  }

  # Backend pool — Internal Load Balancer frontend IP (spoke)
  backend_address_pool {
    name         = "streamlit-backend-pool"
    ip_addresses = [azurerm_lb.spoke.frontend_ip_configuration[0].private_ip_address]
  }

  # Backend HTTP settings — Streamlit port 8501
  backend_http_settings {
    name                  = "streamlit-http-settings"
    cookie_based_affinity = "Disabled"
    port                  = var.streamlit_port
    protocol              = "Http"
    request_timeout       = 120
    probe_name            = "streamlit-health-probe"
  }

  # HTTP listener
  http_listener {
    name                           = "http-listener"
    frontend_ip_configuration_name = "frontend-ip"
    frontend_port_name             = "http-port"
    protocol                       = "Http"
  }

  # Routing rule — listener → backend pool
  request_routing_rule {
    name                       = "streamlit-route"
    rule_type                  = "Basic"
    priority                   = 100
    http_listener_name         = "http-listener"
    backend_address_pool_name  = "streamlit-backend-pool"
    backend_http_settings_name = "streamlit-http-settings"
  }

  # Health probe — Streamlit /_stcore/health on port 8501
  probe {
    name                                      = "streamlit-health-probe"
    protocol                                  = "Http"
    path                                      = "/_stcore/health"
    port                                      = var.streamlit_port
    interval                                  = 30
    timeout                                   = 30
    unhealthy_threshold                       = 3
    pick_host_name_from_backend_http_settings = false
    host                                      = "127.0.0.1"

    match {
      status_code = ["200-399"]
    }
  }

  dynamic "waf_configuration" {
    for_each = var.app_gateway_sku == "WAF_v2" ? [1] : []
    content {
      enabled          = true
      firewall_mode    = "Prevention"
      rule_set_type    = "OWASP"
      rule_set_version = "3.2"
    }
  }

  depends_on = [
    azurerm_linux_virtual_machine_scale_set.streamlit,
    azurerm_lb_rule.streamlit,
    azurerm_virtual_network_peering.hub_to_spoke,
    azurerm_virtual_network_peering.spoke_to_hub,
  ]

  lifecycle {
    create_before_destroy = true
  }
}
