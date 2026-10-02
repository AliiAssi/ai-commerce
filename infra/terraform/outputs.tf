output "vercel_deploy_hook_url" {
  value     = one(vercel_project.beit.git_repository.deploy_hooks).url
  sensitive = true
}
