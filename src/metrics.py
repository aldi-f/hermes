import logging
from typing import Optional

from prometheus_client import CollectorRegistry, Counter, Gauge

logger = logging.getLogger(__name__)


class Metrics:
    def __init__(self):
        self.registry = CollectorRegistry()

        self.alerts_received = Counter(
            "spreader_alerts_received_total",
            "Total alerts received",
            registry=self.registry,
        )

        self.alerts_matched = Counter(
            "spreader_alerts_matched_total",
            "Total alerts matched to groups",
            ["group"],
            registry=self.registry,
        )

        self.alerts_sent = Counter(
            "spreader_alerts_sent_total",
            "Total alerts sent to destinations",
            ["group", "destination", "status"],
            registry=self.registry,
        )

        self.alerts_deduplicated = Counter(
            "spreader_alerts_deduplicated_total",
            "Total alerts deduplicated",
            ["group"],
            registry=self.registry,
        )

        self.send_attempts = Counter(
            "spreader_send_attempts_total",
            "Total send attempts",
            ["destination", "status"],
            registry=self.registry,
        )

        self.active_alerts = Gauge(
            "spreader_active_alerts",
            "Active alerts per group",
            ["group"],
            registry=self.registry,
        )

        self.config_reload_success = Counter(
            "spreader_config_reload_success_total",
            "Successful config reloads",
            registry=self.registry,
        )

        self.config_reload_failure = Counter(
            "spreader_config_reload_failure_total",
            "Failed config reloads",
            registry=self.registry,
        )

        self.fingerprint_strategy = Gauge(
            "spreader_fingerprint_strategy",
            "Fingerprint strategy (0=auto, 1=alertmanager, 2=custom)",
            registry=self.registry,
        )

        self.fingerprint_computed = Counter(
            "spreader_fingerprint_computed_total",
            "Total fingerprints computed",
            registry=self.registry,
        )

        self.fingerprint_used_alertmanager = Counter(
            "spreader_fingerprint_used_alertmanager_total",
            "Total fingerprints from Alertmanager",
            registry=self.registry,
        )

        self.redis_connected = Gauge(
            "spreader_redis_connected",
            "Redis connection status (1=connected, 0=disconnected)",
            registry=self.registry,
        )

        self.redis_operations = Counter(
            "spreader_redis_operations_total",
            "Total Redis operations",
            ["operation", "status"],
            registry=self.registry,
        )

        self.redis_queue_size = Gauge(
            "spreader_redis_queue_size",
            "Current replay queue size",
            registry=self.registry,
        )

        self.redis_circuit_breaker_state = Gauge(
            "spreader_redis_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open, 2=half_open)",
            registry=self.registry,
        )


_metrics: Optional[Metrics] = None


def init_metrics() -> Metrics:
    global _metrics
    _metrics = Metrics()
    return _metrics


def get_metrics() -> Metrics:
    global _metrics
    if _metrics is None:
        return init_metrics()
    return _metrics
