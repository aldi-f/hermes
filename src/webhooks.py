import asyncio
import logging
from typing import Dict, List

from src.models import Alert, AlertContext, Config, Group, WebhookPayload
from src.matcher import get_matching_groups
from src.state import StateManager
from src.senders.base import create_sender, BaseSender
from src.templates import TemplateEngine
from src.fingerprint import get_fingerprint

logger = logging.getLogger(__name__)


class AlertProcessor:
    def __init__(self, config: Config, state_manager: StateManager):
        self._config = config
        self._state_manager = state_manager
        self._template_engine = TemplateEngine()
        self._senders: Dict[str, BaseSender] = {}
        self._init_senders()

    def _init_senders(self):
        for dest in self._config.destinations:
            self._senders[dest.name] = create_sender(dest, self._template_engine)

    def update_config(self, config: Config):
        self._config = config
        self._state_manager.update_config(config)
        self._init_senders()

    async def process_webhook(self, payload: WebhookPayload, metrics) -> Dict[str, int]:
        results = {"received": 0, "matched": 0, "sent": 0, "deduplicated": 0}

        for alert in payload.alerts:
            results["received"] += 1
            metrics.alerts_received.inc()

            matching_groups = get_matching_groups(alert, self._config.groups)

            if not matching_groups:
                continue

            for group in matching_groups:
                results["matched"] += 1
                metrics.alerts_matched.labels(group=group.name).inc()

                if not await self._state_manager.should_send(alert, group.name, metrics):
                    results["deduplicated"] += 1
                    continue

                active = await self._state_manager.get_active_count(group.name)
                metrics.active_alerts.labels(group=group.name).set(active)

                for dest_name in group.destinations:
                    sender = self._senders.get(dest_name)
                    if not sender:
                        logger.warning(f"Unknown destination: {dest_name}")
                        continue

                    fingerprint = get_fingerprint(
                        alert,
                        self._config.settings.fingerprint_strategy,
                        metrics
                    )

                    context = AlertContext(
                        status=alert.status,
                        labels=alert.labels,
                        annotations=alert.annotations,
                        startsAt=alert.startsAt,
                        endsAt=alert.endsAt,
                        generatorURL=alert.generatorURL,
                        fingerprint=fingerprint,
                        group_name=group.name,
                        destination_name=dest_name,
                    )

                    success = await sender.send_async(context)
                    status = "success" if success else "failure"
                    results["sent"] += 1 if success else 0
                    metrics.alerts_sent.labels(
                        group=group.name,
                        destination=dest_name,
                        status=status
                    ).inc()
                    metrics.send_attempts.labels(
                        destination=dest_name,
                        status=status
                    ).inc()

        return results
