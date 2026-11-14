variable "project_id" {
  type = string
}
variable "region" {
  type    = string
  default = "us-central1"
}
variable "image_url" {
  type        = string
  description = "Docker image prebuilt with VITE_AUTH_MODE=oidc and public HTTPS OIDC issuer"
}
variable "oidc_issuer" {
  type        = string
  description = "HTTPS issuer configured in external IdP; register the Cloud Run redirect URI"
}
variable "oidc_audience" {
  type    = string
  default = "launchpilot-api"
}
variable "db_password" {
  type        = string
  sensitive   = true
  description = "Use TF_VAR_db_password; never commit passwords"
}
variable "kafka_bootstrap_servers" {
  type        = string
  default     = ""
  description = "Optional managed Kafka broker host:port; needs network reachability"
}
variable "kafka_sasl_username" {
  type    = string
  default = ""
}
variable "kafka_sasl_password" {
  type      = string
  default   = ""
  sensitive = true
}
variable "enable_cloud_slo" {
  type        = bool
  default     = false
  description = "Enable after verifying Cloud Monitoring service filters on your project"
}
