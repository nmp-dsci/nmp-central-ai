# infra/terraform (M2)

Planned layout, built in milestone 2:

- `bootstrap/` — state bucket, ECR repository, GitHub OIDC role (same pattern as the siblings).
- `central/` — VPC (public subnet only), one t4g.small EC2 (AL2023, Docker, SSM agent, no SSH),
  Caddy for HTTPS + basic-auth, RDS Postgres db.t4g.micro, S3 artifacts bucket, Secrets Manager.
- `modules/` — `compose-host`, `rds-postgres`, `github-oidc`; later `ecs-express-service`.

No load balancer, no NAT gateway. Sleep/wake via `make aws-sleep` / `make aws-wake`.
