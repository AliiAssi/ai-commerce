locals {
  free_tier = {
    machine_type = "e2-micro"
    disk_type    = "pd-standard"
    disk_size_gb = 30
  }
}

data "google_compute_default_service_account" "default" {}

resource "google_compute_address" "public" {
  name    = "beit-ip"
  region  = var.gcp_region
  address = "136.67.35.182"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_disk" "boot" {
  name = "beit-std"
  zone = var.gcp_zone
  type = local.free_tier.disk_type
  size = local.free_tier.disk_size_gb

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [snapshot]
  }
}

resource "google_compute_instance" "beit" {
  name         = "beit"
  zone         = var.gcp_zone
  machine_type = local.free_tier.machine_type
  tags         = ["http-server", "https-server"]

  key_revocation_action_type = "NONE"
  deletion_protection        = true

  metadata = {
    enable-osconfig = "TRUE"
  }

  boot_disk {
    source      = google_compute_disk.boot.self_link
    auto_delete = false
  }

  network_interface {
    network    = "default"
    subnetwork = "default"

    access_config {
      nat_ip = google_compute_address.public.address
    }
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    provisioning_model  = "STANDARD"
  }

  service_account {
    email = data.google_compute_default_service_account.default.email
    scopes = [
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring.write",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/servicecontrol",
      "https://www.googleapis.com/auth/trace.append",
    ]
  }

  shielded_instance_config {
    enable_secure_boot          = false
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [metadata["ssh-keys"]]
  }
}

resource "google_compute_firewall" "allow_http" {
  name          = "default-allow-http"
  network       = "default"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["http-server"]

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }
}

resource "google_compute_firewall" "allow_https" {
  name          = "default-allow-https"
  network       = "default"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["https-server"]

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }
}

resource "google_compute_firewall" "allow_ssh" {
  name          = "default-allow-ssh"
  description   = "Allow SSH from anywhere"
  network       = "default"
  priority      = 65534
  source_ranges = ["0.0.0.0/0"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_firewall" "allow_icmp" {
  name          = "default-allow-icmp"
  description   = "Allow ICMP from anywhere"
  network       = "default"
  priority      = 65534
  source_ranges = ["0.0.0.0/0"]

  allow {
    protocol = "icmp"
  }
}

resource "google_compute_firewall" "allow_internal" {
  name          = "default-allow-internal"
  description   = "Allow internal traffic on the default network"
  network       = "default"
  priority      = 65534
  source_ranges = ["10.128.0.0/9"]

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }
}
