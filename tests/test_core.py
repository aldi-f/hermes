from datetime import datetime

import pytest
import pytest_asyncio

from src.matcher import alert_matches_group, get_matching_groups, matches_rule
from src.fingerprint import compute_fingerprint, get_fingerprint
from src.state import StateManager
from src.templates import TemplateEngine
from src.models import (
    Alert,
    AlertContext,
    Config,
    Group,
    MatchRule,
    MatchType,
    Settings,
    TemplateConfig,
    FingerprintStrategy,
)


class TestMatcher:
    def test_label_equals_match(self):
        alert = Alert(
            status="firing",
            labels={"namespace": "oxygen"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_EQUALS,
            label="namespace",
            values=["oxygen", "dhc"],
        )
        assert matches_rule(alert, rule) is True

    def test_label_equals_no_match(self):
        alert = Alert(
            status="firing",
            labels={"namespace": "mercury"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_EQUALS,
            label="namespace",
            values=["oxygen", "dhc"],
        )
        assert matches_rule(alert, rule) is False

    def test_label_contains_match(self):
        alert = Alert(
            status="firing",
            labels={"queueName": "oxygen-queue-abc"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_CONTAINS,
            label="queueName",
            substring="oxygen",
        )
        assert matches_rule(alert, rule) is True

    def test_label_contains_no_match(self):
        alert = Alert(
            status="firing",
            labels={"queueName": "mercury-queue"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_CONTAINS,
            label="queueName",
            substring="oxygen",
        )
        assert matches_rule(alert, rule) is False

    def test_label_matches_regex(self):
        alert = Alert(
            status="firing",
            labels={"container": "oxygen-exporter"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_MATCHES,
            label="container",
            pattern=r"^oxygen-.*$",
        )
        assert matches_rule(alert, rule) is True

    def test_label_not_equals_match(self):
        alert = Alert(
            status="firing",
            labels={"namespace": "prod"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_NOT_EQUALS,
            label="namespace",
            values=["test"],
        )
        assert matches_rule(alert, rule) is True

    def test_annotation_equals(self):
        alert = Alert(
            status="firing",
            annotations={"summary": "High memory usage"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.ANNOTATION_EQUALS,
            label="summary",
            values=["High memory usage"],
        )
        assert matches_rule(alert, rule) is True

    def test_always_match(self):
        alert = Alert(
            status="firing",
            labels={"foo": "bar"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(type=MatchType.ALWAYS_MATCH)
        assert matches_rule(alert, rule) is True

    def test_alert_matches_group_or_logic(self):
        alert = Alert(
            status="firing",
            labels={"namespace": "oxygen"},
            startsAt=datetime.now(),
        )
        group = Group(
            name="oxygen",
            destinations=["slack-oxygen"],
            match=[
                MatchRule(
                    type=MatchType.LABEL_EQUALS,
                    label="namespace",
                    values=["oxygen"],
                ),
                MatchRule(
                    type=MatchType.LABEL_EQUALS,
                    label="namespace",
                    values=["mercury"],
                ),
            ],
        )
        assert alert_matches_group(alert, group) is True

    def test_get_matching_groups(self):
        alert = Alert(
            status="firing",
            labels={"namespace": "oxygen"},
            startsAt=datetime.now(),
        )
        groups = [
            Group(
                name="oxygen",
                destinations=["slack-oxygen"],
                match=[
                    MatchRule(
                        type=MatchType.LABEL_EQUALS,
                        label="namespace",
                        values=["oxygen"],
                    )
                ],
            ),
            Group(
                name="mercury",
                destinations=["slack-mercury"],
                match=[
                    MatchRule(
                        type=MatchType.LABEL_EQUALS,
                        label="namespace",
                        values=["mercury"],
                    )
                ],
            ),
        ]
        matching = get_matching_groups(alert, groups)
        assert len(matching) == 1
        assert matching[0].name == "oxygen"


class TestFingerprint:
    def test_compute_fingerprint(self):
        labels = {"a": "1", "b": "2"}
        fp = compute_fingerprint(labels)
        assert isinstance(fp, str)
        assert len(fp) == 16

    def test_compute_fingerprint_order_independent(self):
        labels1 = {"a": "1", "b": "2"}
        labels2 = {"b": "2", "a": "1"}
        assert compute_fingerprint(labels1) == compute_fingerprint(labels2)

    def test_get_fingerprint_auto_uses_alertmanager(self):
        alert = Alert(
            status="firing",
            labels={"foo": "bar"},
            fingerprint="custom-fp-123",
            startsAt=datetime.now(),
        )
        fp = get_fingerprint(alert, FingerprintStrategy.AUTO)
        assert fp == "custom-fp-123"

    def test_get_fingerprint_auto_fallback_to_custom(self):
        alert = Alert(
            status="firing",
            labels={"foo": "bar"},
            startsAt=datetime.now(),
        )
        fp = get_fingerprint(alert, FingerprintStrategy.AUTO)
        expected = compute_fingerprint({"foo": "bar"})
        assert fp == expected

    def test_get_fingerprint_custom(self):
        alert = Alert(
            status="firing",
            labels={"foo": "bar"},
            fingerprint="ignored-fp",
            startsAt=datetime.now(),
        )
        fp = get_fingerprint(alert, FingerprintStrategy.CUSTOM)
        expected = compute_fingerprint({"foo": "bar"})
        assert fp == expected

    def test_get_fingerprint_alertmanager_requires_fingerprint(self):
        alert = Alert(
            status="firing",
            labels={"foo": "bar"},
            startsAt=datetime.now(),
        )
        with pytest.raises(ValueError, match="Alertmanager fingerprint required"):
            get_fingerprint(alert, FingerprintStrategy.ALERTMANAGER)


class TestStateManager:
    @pytest.mark.asyncio
    async def test_first_firing_should_send(self):
        config = Config(settings=Settings(fingerprint_strategy=FingerprintStrategy.CUSTOM))
        manager = StateManager(config)
        alert = Alert(
            status="firing",
            labels={"alertname": "TestAlert"},
            startsAt=datetime.now(),
        )
        result = await manager.should_send(alert, "test-group")
        assert result is True

    @pytest.mark.asyncio
    async def test_duplicate_firing_should_not_send(self):
        config = Config(settings=Settings(fingerprint_strategy=FingerprintStrategy.CUSTOM))
        manager = StateManager(config)
        alert = Alert(
            status="firing",
            labels={"alertname": "TestAlert"},
            startsAt=datetime.now(),
        )
        await manager.should_send(alert, "test-group")
        result = await manager.should_send(alert, "test-group")
        assert result is False

    @pytest.mark.asyncio
    async def test_resolved_after_firing_should_send(self):
        config = Config(settings=Settings(fingerprint_strategy=FingerprintStrategy.CUSTOM))
        manager = StateManager(config)
        firing_alert = Alert(
            status="firing",
            labels={"alertname": "TestAlert"},
            startsAt=datetime.now(),
        )
        await manager.should_send(firing_alert, "test-group")
        resolved_alert = Alert(
            status="resolved",
            labels={"alertname": "TestAlert"},
            startsAt=datetime.now(),
        )
        result = await manager.should_send(resolved_alert, "test-group")
        assert result is True

    @pytest.mark.asyncio
    async def test_resolved_without_firing_should_not_send(self):
        config = Config(settings=Settings(fingerprint_strategy=FingerprintStrategy.CUSTOM))
        manager = StateManager(config)
        resolved_alert = Alert(
            status="resolved",
            labels={"alertname": "TestAlert"},
            startsAt=datetime.now(),
        )
        result = await manager.should_send(resolved_alert, "test-group")
        assert result is False

    @pytest.mark.asyncio
    async def test_different_groups_independent(self):
        config = Config(settings=Settings(fingerprint_strategy=FingerprintStrategy.CUSTOM))
        manager = StateManager(config)
        alert = Alert(
            status="firing",
            labels={"alertname": "TestAlert"},
            startsAt=datetime.now(),
        )
        result1 = await manager.should_send(alert, "group-a")
        result2 = await manager.should_send(alert, "group-b")
        assert result1 is True
        assert result2 is True


class TestTemplateEngine:
    def test_render_inline_template(self):
        engine = TemplateEngine()
        template_config = TemplateConfig(content="Alert: {{ status }} - {{ labels.alertname }}")
        context = AlertContext(
            status="firing",
            labels={"alertname": "TestAlert"},
            annotations={},
            startsAt=datetime.now(),
            endsAt=None,
            generatorURL=None,
            fingerprint="abc123",
            group_name="test-group",
            destination_name="slack",
        )
        result = engine.render(template_config, context)
        assert result == "Alert: firing - TestAlert"

    def test_render_with_labels(self):
        engine = TemplateEngine()
        template_config = TemplateConfig(
            content="Namespace: {{ labels.namespace }}, Severity: {{ labels.severity }}"
        )
        context = AlertContext(
            status="firing",
            labels={"namespace": "production", "severity": "critical"},
            annotations={},
            startsAt=datetime.now(),
            endsAt=None,
            generatorURL=None,
            fingerprint="abc123",
            group_name="test-group",
            destination_name="slack",
        )
        result = engine.render(template_config, context)
        assert result == "Namespace: production, Severity: critical"
