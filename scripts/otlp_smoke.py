#!/usr/bin/env python
"""Send one OpenTelemetry span to the central MLflow server's OTLP endpoint.

Mirrors what data-qa-agent's backend does (BatchSpanProcessor + OTLP/HTTP exporter with the
x-mlflow-experiment-id header), so it proves the ingest path without starting that stack.

    uv run scripts/otlp_smoke.py --experiment-id 2 [--uri http://localhost:5000]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _registry import load_registry, resolve_uri  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uri", default=None)
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--name", default="central-otlp-smoke")
    args = ap.parse_args()
    reg = load_registry()
    uri = resolve_uri(args.uri, reg).rstrip("/")

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    exporter = OTLPSpanExporter(
        endpoint=f"{uri}/v1/traces", headers={"x-mlflow-experiment-id": args.experiment_id}
    )
    provider = TracerProvider(resource=Resource.create({"service.name": "nmp-central-smoke"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("nmp-central")
    t0 = int(time.time() * 1000)
    with tracer.start_as_current_span(args.name) as span:
        span.set_attribute("smoke", True)
        span.set_attribute("mlflow.spanInputs", '{"q": "ping"}')
        span.set_attribute("mlflow.spanOutputs", '{"a": "pong"}')
    provider.force_flush()
    provider.shutdown()

    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri=uri)
    for _ in range(10):
        try:
            traces = client.search_traces(locations=[args.experiment_id], max_results=20)
        except TypeError:
            traces = client.search_traces(experiment_ids=[args.experiment_id], max_results=20)
        fresh = [t for t in traces if int(getattr(t.info, "timestamp_ms", 0) or 0) >= t0 - 5000]
        if fresh:
            print(f"OK: {len(fresh)} trace(s) landed in experiment {args.experiment_id} at {uri}")
            return 0
        time.sleep(1)
    print(f"FAIL: no trace visible in experiment {args.experiment_id} at {uri}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
