variable "gcp_project" {
  type    = string
  default = "beit-503910"
}

variable "gcp_region" {
  type    = string
  default = "us-west1"

  validation {
    condition     = contains(["us-west1", "us-central1", "us-east1"], var.gcp_region)
    error_message = "The e2-micro free tier only covers us-west1, us-central1 and us-east1."
  }
}

variable "gcp_zone" {
  type    = string
  default = "us-west1-b"
}

variable "supabase_project_ref" {
  type    = string
  default = "geholhromutuiqdmappr"
}

variable "vercel_team" {
  type    = string
  default = "team_cUhOtz8hrJYUpHHGECnzi7p5"
}
