import hashlib
import logging
from typing import Dict, Optional

from src.models import Alert, FingerprintStrategy

logger = logging.getLogger(__name__)


def compute_fingerprint(labels: Dict[str, str]) -> str:
    sorted_labels = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return hashlib.sha256(sorted_labels.encode()).hexdigest()[:16]


def get_fingerprint(
    alert: Alert,
    strategy: FingerprintStrategy,
    metrics: Optional[object] = None
) -> str:
    if strategy == FingerprintStrategy.ALERTMANAGER:
        if not alert.fingerprint:
            raise ValueError("Alertmanager fingerprint required but not provided")
        if metrics:
            metrics.fingerprint_used_alertmanager.inc()
        return alert.fingerprint

    if strategy == FingerprintStrategy.CUSTOM:
        fp = compute_fingerprint(alert.labels)
        if metrics:
            metrics.fingerprint_computed.inc()
        return fp

    if strategy == FingerprintStrategy.AUTO:
        if alert.fingerprint:
            if metrics:
                metrics.fingerprint_used_alertmanager.inc()
            return alert.fingerprint
        fp = compute_fingerprint(alert.labels)
        if metrics:
            metrics.fingerprint_computed.inc()
        return fp

    raise ValueError(f"Unknown fingerprint strategy: {strategy}")
