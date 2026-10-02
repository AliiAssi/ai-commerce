resource "supabase_project" "beit" {
  name              = "BEIT"
  organization_id   = "jfrqyakydsbzhiufbovt"
  region            = "us-west-2"
  database_password = "set-in-supabase-dashboard"

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [database_password]
  }
}
