locals {

  apis = toset([
    "run.googleapis.com", "cloudbuild.googleapis.com", "artifactregistry.googleapis.com",
    "sqladmin.googleapis.com", "secretmanager.googleapis.com", "compute.googleapis.com",
    "redis.googleapis.com", "monitoring.googleapis.com"
  ])
  db_url = "postgresql+psycopg://launchpilot:${urlencode(var.db_password)}@/launchpilot?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
  event_transport = var.kafka_bootstrap_servers == "" ? "disabled" : "kafka"

}
resource "google_project_service" "apis" {

  for_each           = local.apis
  service            = each.value
  disable_on_destroy = false

}
resource "google_service_account" "app" {

  account_id   = "launchpilot-runtime"
  display_name = "LaunchPilot runtime"
  depends_on   = [google_project_service.apis]

}
resource "google_project_iam_member" "cloudsql" {

  project = var.project_id
  role = "roles/cloudsql.client"
  member = "serviceAccount:${google_service_account.app.email}"

}
resource "google_compute_network" "private" {

  name = "launchpilot-private"
  auto_create_subnetworks = false
  depends_on = [google_project_service.apis]

}
resource "google_compute_subnetwork" "private" {

  name = "launchpilot-subnet"
  network = google_compute_network.private.id
  ip_cidr_range = "10.18.0.0/24"
  region = var.region

}
resource "google_redis_instance" "cache" {

  name = "launchpilot-cache"
  region = var.region
  memory_size_gb = 1
  tier = "BASIC"
  redis_version = "REDIS_7_0"
  authorized_network = google_compute_network.private.id
  depends_on = [google_project_service.apis]

}
resource "google_sql_database_instance" "postgres" {

  name = "launchpilot-pg"
  region = var.region
  database_version = "POSTGRES_16"
  deletion_protection = true
  settings {

    tier = "db-custom-1-3840"
    backup_configuration {
 enabled = true 
}
    ip_configuration {
 ipv4_enabled = true 
}
  
}
  depends_on = [google_project_service.apis]

}
resource "google_sql_database" "database" {

  name = "launchpilot"
  instance = google_sql_database_instance.postgres.name

}
resource "google_sql_user" "user" {

  name = "launchpilot"
  instance = google_sql_database_instance.postgres.name
  password = var.db_password

}
resource "google_secret_manager_secret" "db_url" {

  secret_id = "launchpilot-db-url"
  replication {
 auto {

} 
}
  depends_on = [google_project_service.apis]

}
resource "google_secret_manager_secret_version" "db_url" {

  secret = google_secret_manager_secret.db_url.id
  secret_data = local.db_url

}
resource "google_secret_manager_secret_iam_member" "db_access" {

  secret_id = google_secret_manager_secret.db_url.id
  role = "roles/secretmanager.secretAccessor"
  member = "serviceAccount:${google_service_account.app.email}"

}
resource "google_secret_manager_secret" "kafka_password" {

  count = local.event_transport == "kafka" ? 1 : 0
  secret_id = "launchpilot-kafka-password"
  replication {
 auto {

} 
}

}
resource "google_secret_manager_secret_version" "kafka_password" {

  count = local.event_transport == "kafka" ? 1 : 0
  secret = google_secret_manager_secret.kafka_password[0].id
  secret_data = var.kafka_sasl_password

}
resource "google_secret_manager_secret_iam_member" "kafka_access" {

  count = local.event_transport == "kafka" ? 1 : 0
  secret_id = google_secret_manager_secret.kafka_password[0].id
  role = "roles/secretmanager.secretAccessor"
  member = "serviceAccount:${google_service_account.app.email}"

}
locals {

  worker_environment = {

    APP_ENV = "production"
    AUTH_MODE = "oidc"
    AUTO_CREATE_SCHEMA = "false"
    SEED_DEMO = "false"
    OIDC_ISSUER = var.oidc_issuer
    OIDC_AUDIENCE = var.oidc_audience
    EVENT_TRANSPORT = local.event_transport
    KAFKA_BOOTSTRAP_SERVERS = var.kafka_bootstrap_servers
    KAFKA_TOPIC = "launchpilot.events.v1"
    KAFKA_SECURITY_PROTOCOL = local.event_transport == "kafka" ? "SASL_SSL" : ""
    KAFKA_SASL_MECHANISM = "PLAIN"
    KAFKA_SASL_USERNAME = var.kafka_sasl_username
    REDIS_URL = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
  
}

}
resource "google_cloud_run_v2_service" "api" {

  name = "launchpilot"
  location = var.region
  deletion_protection = false
  ingress = "INGRESS_TRAFFIC_ALL"
  template {

    service_account = google_service_account.app.email
    scaling {
 max_instance_count = 3 
}
    vpc_access {

      network_interfaces {
 network = google_compute_network.private.id
  subnetwork = google_compute_subnetwork.private.id 
}
      egress = "PRIVATE_RANGES_ONLY"
    
}
    volumes {
 name = "cloudsql"
  cloud_sql_instance {
 instances = [google_sql_database_instance.postgres.connection_name] 
} 
}
    containers {

      image = var.image_url
      ports {
 container_port = 8000 
}
      resources {
 limits = {
 cpu = "1", memory = "1Gi" 
} 
}
      dynamic "env" {

        for_each = local.worker_environment
        content {
 name = env.key
  value = env.value 
}
      
}
      env {
 name = "DATABASE_URL"
  value_source {
 secret_key_ref {
 secret = google_secret_manager_secret.db_url.secret_id
  version = "latest" 
} 
} 
}
      volume_mounts {
 name = "cloudsql"
  mount_path = "/cloudsql" 
}
    
}
  
}
  depends_on = [google_project_iam_member.cloudsql, google_secret_manager_secret_iam_member.db_access, google_secret_manager_secret_version.db_url]

}
resource "google_cloud_run_v2_service_iam_member" "public" {

  location = var.region
  name = google_cloud_run_v2_service.api.name
  role = "roles/run.invoker"
  member = "allUsers" # Public UI only. API methods enforce JWT and RBAC.

}
resource "google_cloud_run_v2_job" "migrate" {

  name = "launchpilot-migrate"
  location = var.region
  template {

    template {

      service_account = google_service_account.app.email
      volumes {
 name = "cloudsql"
  cloud_sql_instance {
 instances = [google_sql_database_instance.postgres.connection_name] 
} 
}
      containers {

        image = var.image_url
        command = ["sh", "-c"]
        args = ["cd backend && alembic upgrade head"]
        env {
 name = "DATABASE_URL"
  value_source {
 secret_key_ref {
 secret = google_secret_manager_secret.db_url.secret_id
  version = "latest" 
} 
} 
}
        volume_mounts {
 name = "cloudsql"
  mount_path = "/cloudsql" 
}
      
}
    
}
  
}
  depends_on = [google_project_iam_member.cloudsql, google_secret_manager_secret_iam_member.db_access]

}
# Worker pools require a reachable, externally managed Kafka cluster (MSK, Confluent Cloud, etc).
# Enable only when Kafka endpoints and Secret Manager credentials are configured.
resource "google_cloud_run_v2_worker_pool" "event_worker" {

  for_each = local.event_transport == "kafka" ? toset(["publish", "consume"]) : toset([])
  name = "launchpilot-${each.key}"
  location = var.region
  template {

    service_account = google_service_account.app.email
    vpc_access {

      network_interfaces {
 network = google_compute_network.private.id
  subnetwork = google_compute_subnetwork.private.id 
}
      egress = "PRIVATE_RANGES_ONLY"
    
}
    volumes {
 name = "cloudsql"
  cloud_sql_instance {
 instances = [google_sql_database_instance.postgres.connection_name] 
} 
}
    containers {

      image = var.image_url
      command = ["python"]
      args = ["-m", "backend.app.worker", each.key]
      dynamic "env" {

        for_each = local.worker_environment
        content {
 name = env.key
  value = env.value 
}
      
}
      env {
 name = "DATABASE_URL"
  value_source {
 secret_key_ref {
 secret = google_secret_manager_secret.db_url.secret_id
  version = "latest" 
} 
} 
}
      env {
 name = "KAFKA_SASL_PASSWORD"
  value_source {
 secret_key_ref {
 secret = google_secret_manager_secret.kafka_password[0].secret_id
  version = "latest" 
} 
} 
}
      volume_mounts {
 name = "cloudsql"
  mount_path = "/cloudsql" 
}
    
}
  
}
  depends_on = [google_secret_manager_secret_iam_member.kafka_access, google_secret_manager_secret_iam_member.db_access]

}
# Optional native Cloud Monitoring SLO; verify project-specific filters.
resource "google_monitoring_service" "launchpilot" {

  count = var.enable_cloud_slo ? 1 : 0
  service_id = "launchpilot-service"
  display_name = "LaunchPilot API"
  
  depends_on = [google_project_service.apis]

}
resource "google_monitoring_slo" "availability" {

  count = var.enable_cloud_slo ? 1 : 0
  service = google_monitoring_service.launchpilot[0].service_id
  slo_id = "availability-999"
  display_name = "99.9% successful HTTP requests (rolling 30 days)"
  goal = 0.999
  rolling_period_days = 30
  request_based_sli {

    good_total_ratio {

      good_service_filter  = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.label.\"service_name\"=\"launchpilot\" AND metric.label.\"response_code_class\"!=\"5xx\""
      total_service_filter = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.label.\"service_name\"=\"launchpilot\""
    
}
  
}

}
