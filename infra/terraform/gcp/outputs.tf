output "launchpilot_url" {
  value = google_cloud_run_v2_service.api.uri
}
output "migration_job" {
  value = google_cloud_run_v2_job.migrate.name
}
output "cloudsql_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}
output "redis_host" {
  value = google_redis_instance.cache.host
}
output "estimated_scope" {
  value = "Cloud Run, Cloud SQL, Redis, VPC, Secret Manager; managed Kafka external. Billable resources."
}
