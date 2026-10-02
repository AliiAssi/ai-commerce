provider "google" {
  project = var.gcp_project
  region  = var.gcp_region
  zone    = var.gcp_zone
}

provider "vercel" {
  team = var.vercel_team
}

provider "supabase" {}
