locals {
  zone_path         = "projects/${var.gcp_project}/zones/${var.gcp_zone}"
  global_path       = "projects/${var.gcp_project}/global"
  vercel_project_id = "prj_cffj0vTSufFzCmn6RuVlBxDAWnAo"
}

import {
  to = google_compute_instance.beit
  id = "${local.zone_path}/instances/beit"
}

import {
  to = google_compute_disk.boot
  id = "${local.zone_path}/disks/beit-std"
}

import {
  to = google_compute_address.public
  id = "projects/${var.gcp_project}/regions/${var.gcp_region}/addresses/beit-ip"
}

import {
  to = google_compute_firewall.allow_http
  id = "${local.global_path}/firewalls/default-allow-http"
}

import {
  to = google_compute_firewall.allow_https
  id = "${local.global_path}/firewalls/default-allow-https"
}

import {
  to = google_compute_firewall.allow_icmp
  id = "${local.global_path}/firewalls/default-allow-icmp"
}

import {
  to = google_compute_firewall.allow_internal
  id = "${local.global_path}/firewalls/default-allow-internal"
}

import {
  to = google_compute_firewall.allow_ssh
  id = "${local.global_path}/firewalls/default-allow-ssh"
}

import {
  to = vercel_project.beit
  id = "${var.vercel_team}/${local.vercel_project_id}"
}

import {
  to = supabase_project.beit
  id = var.supabase_project_ref
}

import {
  to = vercel_project_environment_variable.api_base_url
  id = "${var.vercel_team}/${local.vercel_project_id}/AyPEkmaworGWckfm"
}

import {
  to = vercel_project_environment_variable.ai_enabled
  id = "${var.vercel_team}/${local.vercel_project_id}/Ix7A4c1MuXG4uRa2"
}
