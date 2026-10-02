resource "vercel_project" "beit" {
  name           = "beit"
  framework      = "nextjs"
  root_directory = "frontend"
  node_version   = "24.x"

  git_repository = {
    type              = "github"
    repo              = "AliiAssi/ai-commerce"
    production_branch = "main"
  }

  vercel_authentication = {
    deployment_type = "standard_protection_new"
  }

  resource_config = {
    fluid                    = true
    function_default_regions = ["pdx1"]
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "vercel_project_environment_variable" "api_base_url" {
  project_id = vercel_project.beit.id
  key        = "API_BASE_URL"
  value      = "https://ai-commerce.duckdns.org"
  target     = ["production", "preview"]
  sensitive  = true
}

resource "vercel_project_environment_variable" "ai_enabled" {
  project_id = vercel_project.beit.id
  key        = "AI_ENABLED"
  value      = "true"
  target     = ["production", "preview"]
  sensitive  = true
}
