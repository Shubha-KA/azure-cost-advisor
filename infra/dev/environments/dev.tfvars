subscription_id          = "e54a7ca3-4b6b-4b0f-889d-2508c85f4f30"
platform_tenant_id       = "22dc2419-3ab3-4f27-905a-945315d19d95"
environment              = "dev"
location                 = "eastus2"
search_location          = "eastus"
aks_admin_principal_ids  = ["c0774e78-056b-4d04-9afb-1daa972fd25e"]
private_cluster_enabled  = false
create_private_endpoints = false
cosmos_serverless        = true

system_node_vm_size   = "Standard_D2s_v3"
system_node_count     = 1
system_node_min_count = 1
system_node_max_count = 1

existing_openai_resource_group_name = "open-ai-rg"
existing_openai_account_name        = "azure-cost-advisor-openai"
openai_chat_deployment              = "gpt-4.1-mini"
openai_embedding_deployment         = "text-embedding-3-small"

tags = {
  owner       = "finops-platform"
  cost_center = "dev"
}

frontend_url = "https://vkcolors.shop"
entra_post_logout_redirect_uri = "https://vkcolors.shop"
api_cors_origins = "https://vkcolors.shop"
entra_login_redirect_uris = ["https://vkcolors.shop/api/auth/callback"]
