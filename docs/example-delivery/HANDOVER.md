# Docker deployment starter

Job: e7bc4f08e00e

Status: generated starter files, not deployed or runtime-verified.

## Prerequisites
Confirm that the existing image `example/synthetic-app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` is trusted and listens on port 8000. Docker Compose is required. No application code or image is built by this package. Review capabilities and writable paths for your application.

## Review and validation
Run `docker compose config --quiet` to validate the Compose file before starting anything. We use it to catch configuration errors.
Run `docker compose up -d` only in the agreed test environment to start the application after approval.
Run `curl --fail http://127.0.0.1:8080/health` to check the agreed readiness endpoint. We use this to check an actual application response; it is not a load or security test.
Inspect application logs locally and redact secrets before sharing.

## Rollback
Record the previous immutable image digest before deployment. Restore that digest in compose.yaml and recreate the service only after approval. Data changes and database rollback require a separate backup plan.

## Still required
Registry access, runtime validation, DNS/TLS, backups, application configuration and customer acceptance. No infrastructure was changed.
