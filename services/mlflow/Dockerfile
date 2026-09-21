# Central MLflow server image. Pinned; bump deliberately and run `make mlflow-db-upgrade`.
FROM ghcr.io/mlflow/mlflow:v3.16.1
RUN pip install --no-cache-dir "psycopg2-binary>=2.9" "boto3>=1.35"
EXPOSE 5000
