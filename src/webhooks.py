import logging
from typing import Any, Dict, List

from src.fingerprint import get_fingerprint
from src.matcher import get_matching_groups
from src.models import Alert, AlertContext, Config, Group, GroupedAlertContext, WebhookPayload
from src.senders.base import BaseSender, create_sender
from src.state import StateManager
from src.templates import TemplateEngine

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

    def _get_grouping_key(self, alert: Alert, group_by: list[str]) -> str:
        key_parts = []
        for label in group_by:
            value = alert.labels.get(label, "")
            key_parts.append(f"{label}={value}")
        return "|".join(key_parts)

    def _compute_common_labels(self, alerts: List[Alert]) -> Dict[str, str]:
        """Compute labels that are common to all alerts in the group."""
        if not alerts:
            return {}

        # Start with all labels from the first alert
        common = dict(alerts[0].labels)

        # Intersect with labels from remaining alerts
        for alert in alerts[1:]:
            keys_to_remove = []
            for key, value in common.items():
                if key not in alert.labels or alert.labels[key] != value:
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del common[key]

        return common

    def _compute_common_annotations(self, alerts: List[Alert]) -> Dict[str, str]:
        """Compute annotations that are common to all alerts in the group."""
        if not alerts:
            return {}

        # Start with all annotations from the first alert
        common = dict(alerts[0].annotations)

        # Intersect with annotations from remaining alerts
        for alert in alerts[1:]:
            keys_to_remove = []
            for key, value in common.items():
                if key not in alert.annotations or alert.annotations[key] != value:
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del common[key]

        return common

    async def process_webhook(self, payload: WebhookPayload, metrics) -> Dict[str, int]:
        results = {"received": 0, "matched": 0, "sent": 0, "deduplicated": 0}

        logger.debug(
            "Webhook payload received",
            extra={
                "receiver": payload.receiver,
                "status": payload.status,
                "alert_count": len(payload.alerts),
                "group_labels": payload.groupLabels,
                "common_labels": payload.commonLabels,
                "common_annotations": payload.commonAnnotations,
                "external_url": payload.externalURL,
            },
        )

        for alert in payload.alerts:
            logger.debug(
                "Processing alert",
                extra={
                    "status": alert.status,
                    "labels": alert.labels,
                    "annotations": alert.annotations,
                    "starts_at": alert.startsAt.isoformat() if alert.startsAt else None,
                    "ends_at": alert.endsAt.isoformat() if alert.endsAt else None,
                    "generator_url": alert.generatorURL,
                    "fingerprint": alert.fingerprint,
                },
            )
            results["received"] += 1
            metrics.alerts_received.inc()

        groups_with_alerts: Dict[str, Dict[str, Any]] = {}
        for alert in payload.alerts:
            matching_groups = get_matching_groups(alert, self._config.groups)

            if matching_groups:
                logger.debug(
                    "Alert matched groups",
                    extra={
                        "alert_fingerprint": alert.fingerprint,
                        "matched_groups": [g.name for g in matching_groups],
                    },
                )

            if not matching_groups:
                continue

            for group in matching_groups:
                if group.name not in groups_with_alerts:
                    groups_with_alerts[group.name] = {"group": group, "alerts": []}
                groups_with_alerts[group.name]["alerts"].append(alert)

        for group_name, group_data in groups_with_alerts.items():
            group: Group = group_data["group"]
            alerts: list[Alert] = group_data["alerts"]

            results["matched"] += len(alerts)
            metrics.alerts_matched.labels(group=group.name).inc(len(alerts))

            logger.info(
                "Processing group",
                extra={
                    "group_name": group_name,
                    "alert_count": len(alerts),
                },
            )

            if group.group_by:
                alert_groups: Dict[str, list[Alert]] = {}
                for alert in alerts:
                    key = self._get_grouping_key(alert, group.group_by)
                    if key not in alert_groups:
                        alert_groups[key] = []
                    alert_groups[key].append(alert)

                logger.debug(
                    "Grouped alerts by labels",
                    extra={
                        "group_name": group_name,
                        "grouping_labels": group.group_by,
                        "unique_groups": len(alert_groups),
                    },
                )

                for key, grouped_alerts in alert_groups.items():
                    active = await self._state_manager.get_active_count(group.name)
                    metrics.active_alerts.labels(group=group.name).set(active)

                    group_labels = {}
                    for label in group.group_by:
                        if grouped_alerts:
                            group_labels[label] = grouped_alerts[0].labels.get(label, "")

                    status = grouped_alerts[0].status if grouped_alerts else "firing"
                    common_labels = self._compute_common_labels(grouped_alerts)
                    common_annotations = self._compute_common_annotations(grouped_alerts)

                    if not await self._state_manager.should_send_group(
                        grouped_alerts, key, group.name
                    ):
                        results["deduplicated"] += len(grouped_alerts)
                        logger.debug(
                            "Group deduplicated",
                            extra={
                                "group_name": group_name,
                                "grouping_key": key,
                                "alert_count": len(grouped_alerts),
                            },
                        )
                        continue

                    for dest_name in group.destinations:
                        sender = self._senders.get(dest_name)
                        if not sender:
                            logger.warning(
                                "Unknown destination",
                                extra={"destination": dest_name, "group_name": group_name},
                            )
                            continue

                        logger.debug(
                            "Sending grouped alert",
                            extra={
                                "group_name": group_name,
                                "destination": dest_name,
                                "status": status,
                                "alert_count": len(grouped_alerts),
                                "grouping_key": key,
                            },
                        )

                        context = GroupedAlertContext(
                            alerts=grouped_alerts,
                            group_labels=group_labels,
                            common_labels=common_labels,
                            common_annotations=common_annotations,
                            status=status,
                            group_name=group.name,
                            destination_name=dest_name,
                        )

                        success = await sender.send_grouped_async(context)
                        status_outcome = "success" if success else "failure"
                        results["sent"] += 1 if success else 0
                        logger.info(
                            "Send result",
                            extra={
                                "destination": dest_name,
                                "group_name": group_name,
                                "status": status_outcome,
                                "grouped": True,
                            },
                        )
                        metrics.alerts_sent.labels(
                            group=group.name, destination=dest_name, status=status_outcome
                        ).inc()
                        metrics.send_attempts.labels(
                            destination=dest_name, status=status_outcome
                        ).inc()
            else:
                for alert in alerts:
                    if not await self._state_manager.should_send(alert, group.name, metrics):
                        results["deduplicated"] += 1
                        logger.debug(
                            "Alert deduplicated",
                            extra={
                                "group_name": group_name,
                                "alert_fingerprint": alert.fingerprint,
                            },
                        )
                        continue

                    active = await self._state_manager.get_active_count(group.name)
                    metrics.active_alerts.labels(group=group.name).set(active)

                    fingerprint = get_fingerprint(
                        alert, self._config.settings.fingerprint_strategy, metrics
                    )

                    for dest_name in group.destinations:
                        sender = self._senders.get(dest_name)
                        if not sender:
                            logger.warning(
                                "Unknown destination",
                                extra={"destination": dest_name, "group_name": group_name},
                            )
                            continue

                        logger.debug(
                            "Sending single alert",
                            extra={
                                "group_name": group_name,
                                "destination": dest_name,
                                "status": alert.status,
                                "fingerprint": fingerprint,
                            },
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
                        status_outcome = "success" if success else "failure"
                        results["sent"] += 1 if success else 0
                        logger.info(
                            "Send result",
                            extra={
                                "destination": dest_name,
                                "group_name": group_name,
                                "status": status_outcome,
                                "grouped": False,
                            },
                        )
                        metrics.alerts_sent.labels(
                            group=group.name, destination=dest_name, status=status_outcome
                        ).inc()
                        metrics.send_attempts.labels(
                            destination=dest_name, status=status_outcome
                        ).inc()

        return results
