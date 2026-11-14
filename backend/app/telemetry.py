"""OpenTelemetry spans exported to OTLP; Prometheus HTTP SLIs are local/internal."""
import os
import time
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

REQUESTS = Counter("launchpilot_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("launchpilot_http_duration_seconds", "Response latency", ["method", "route"], buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5))
CACHE = Counter("launchpilot_eval_cache_total", "Evaluation cache lookups", ["result"])
EVENTS = Counter("launchpilot_events_total", "Events accepted", ["type"])

async def metrics_middleware(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    if not request.url.path.startswith("/internal"):
        path = getattr(request.scope.get("route"), "path", None) or "unmatched"
        REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
    return response

def metrics_response():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

def instrument(app):
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    provider = TracerProvider(resource=Resource.create({"service.name": "launchpilot-api"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
