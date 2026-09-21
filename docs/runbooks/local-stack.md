# Runbook: the local stack

| symptom | do |
|---|---|
| `make status` says DOWN | `make up`; then `make logs` if it does not become healthy in ~60 s |
| port 5000 already in use | `lsof -nP -iTCP:5000 -sTCP:LISTEN`. A sibling's old MLflow container is the usual culprit: `docker ps` and stop it. AirPlay Receiver on macOS also uses 5000. |
| exporter gets HTTP 403 | the Host you used is not in `MLFLOW_SERVER_ALLOWED_HOSTS` in `docker-compose.yml`; add it |
| artifacts fail to upload | `docker compose logs minio-init` (bucket created?), then `docker compose logs mlflow` for S3 errors |
| MLflow says the schema is out of date | you bumped the image: `make mlflow-db-upgrade` |
| start from scratch | `make nuke` (asks), then `make up && make mlflow-init` |
| where is the data | Docker volumes `nmp-central_pgdata` and `nmp-central_miniodata`; MinIO console at http://localhost:9001 |
