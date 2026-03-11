from datetime import datetime

import pytest

from src.fingerprint import compute_fingerprint, get_fingerprint
from src.matcher import alert_matches_group, get_matching_groups, matches_rule
from src.models import (
    Alert,
    AlertContext,
    Config,
    FingerprintStrategy,
    Group,
    GroupedAlertContext,
    MatchRule,
    MatchType,
    Settings,
    TemplateConfig,
)
from src.state import StateManager
from src.templates import TemplateEngine
from src.webhooks import AlertProcessor


class TestMatcher:
    def test_label_equals_match(self):
        alert = Alert(
            status="firing",
            labels={"namespace": "team-a"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_EQUALS,
            label="namespace",
            values=["team-a", "dhc"],
        )
        assert matches_rule(alert, rule) is True

    def test_label_equals_no_match(self):
        alert = Alert(
            status="firing",
            labels={"namespace": "team-b"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_EQUALS,
            label="namespace",
            values=["team-a", "dhc"],
        )
        assert matches_rule(alert, rule) is False

    def test_label_contains_match(self):
        alert = Alert(
            status="firing",
            labels={"queueName": "team-a-queue-abc"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_CONTAINS,
            label="queueName",
            substring="team-a",
        )
        assert matches_rule(alert, rule) is True

    def test_label_contains_no_match(self):
        alert = Alert(
            status="firing",
            labels={"queueName": "team-b-queue"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_CONTAINS,
            label="queueName",
            substring="team-a",
        )
        assert matches_rule(alert, rule) is False

    def test_label_matches_regex(self):
        alert = Alert(
            status="firing",
            labels={"container": "team-a-exporter"},
            startsAt=datetime.now(),
        )
        rule = MatchRule(
            type=MatchType.LABEL_MATCHES,
            label="container",
            pattern=r"^team-a-.*$",
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
            labels={"namespace": "namespace-a"},
            startsAt=datetime.now(),
        )
        group = Group(
            name="team-a",
            destinations=["slack-team-a"],
            match=[
                MatchRule(
                    type=MatchType.LABEL_EQUALS,
                    label="namespace",
                    values=["namespace-a"],
                ),
                MatchRule(
                    type=MatchType.LABEL_EQUALS,
                    label="namespace",
                    values=["namespace-b"],
                ),
            ],
        )
        assert alert_matches_group(alert, group) is True

    def test_get_matching_groups(self):
        alert = Alert(
            status="firing",
            labels={"namespace": "namespace-a"},
            startsAt=datetime.now(),
        )
        groups = [
            Group(
                name="team-a",
                destinations=["slack-team-a"],
                match=[
                    MatchRule(
                        type=MatchType.LABEL_EQUALS,
                        label="namespace",
                        values=["namespace-a"],
                    )
                ],
            ),
            Group(
                name="team-b",
                destinations=["slack-team-b"],
                match=[
                    MatchRule(
                        type=MatchType.LABEL_EQUALS,
                        label="namespace",
                        values=["namespace-b"],
                    )
                ],
            ),
        ]
        matching = get_matching_groups(alert, groups)
        assert len(matching) == 1
        assert matching[0].name == "team-a"


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

    def test_render_grouped_with_common_labels(self):
        engine = TemplateEngine()
        template_config = TemplateConfig(
            content="*Alert:* `{{ common_labels.severity }}` - {{ common_labels.alertname }}\n*Cluster:* `{{ common_labels.cluster }}`\n*Messages:*\n{% for alert in alerts %}\n• {{ alert.annotations.description }}\n{% endfor %}"
        )
        alerts = [
            Alert(
                status="firing",
                labels={
                    "alertname": "HighMemory",
                    "severity": "warning",
                    "cluster": "prod",
                    "pod": "pod-1",
                },
                annotations={"description": "Pod pod-1 memory high"},
                startsAt=datetime.now(),
            ),
            Alert(
                status="firing",
                labels={
                    "alertname": "HighMemory",
                    "severity": "warning",
                    "cluster": "prod",
                    "pod": "pod-2",
                },
                annotations={"description": "Pod pod-2 memory high"},
                startsAt=datetime.now(),
            ),
        ]
        context = GroupedAlertContext(
            alerts=alerts,
            group_labels={"alertname": "HighMemory", "cluster": "prod"},
            common_labels={"alertname": "HighMemory", "severity": "warning", "cluster": "prod"},
            common_annotations={},
            status="firing",
            group_name="test-group",
            destination_name="slack",
        )
        result = engine.render_grouped(template_config, context)
        assert "*Alert:* `warning` - HighMemory" in result
        assert "*Cluster:* `prod`" in result
        assert "• Pod pod-1 memory high" in result
        assert "• Pod pod-2 memory high" in result

    def test_render_grouped_iterate_alerts(self):
        engine = TemplateEngine()
        template_config = TemplateConfig(
            content="{% for alert in alerts %}{{ alert.labels.pod }},{% endfor %}"
        )
        alerts = [
            Alert(
                status="firing",
                labels={"pod": "pod-a"},
                annotations={},
                startsAt=datetime.now(),
            ),
            Alert(
                status="firing",
                labels={"pod": "pod-b"},
                annotations={},
                startsAt=datetime.now(),
            ),
            Alert(
                status="firing",
                labels={"pod": "pod-c"},
                annotations={},
                startsAt=datetime.now(),
            ),
        ]
        context = GroupedAlertContext(
            alerts=alerts,
            group_labels={},
            common_labels={},
            common_annotations={},
            status="firing",
            group_name="test-group",
            destination_name="slack",
        )
        result = engine.render_grouped(template_config, context)
        assert result == "pod-a,pod-b,pod-c,"


class TestCommonLabelsComputation:
    def test_compute_common_labels_all_same(self):
        config = Config(settings=Settings())
        state_manager = StateManager(config)
        processor = AlertProcessor(config, state_manager)

        alerts = [
            Alert(
                status="firing",
                labels={"alertname": "Test", "severity": "warning", "cluster": "prod"},
                startsAt=datetime.now(),
            ),
            Alert(
                status="firing",
                labels={"alertname": "Test", "severity": "warning", "cluster": "prod"},
                startsAt=datetime.now(),
            ),
        ]
        common = processor._compute_common_labels(alerts)
        assert common == {"alertname": "Test", "severity": "warning", "cluster": "prod"}

    def test_compute_common_labels_partial_overlap(self):
        config = Config(settings=Settings())
        state_manager = StateManager(config)
        processor = AlertProcessor(config, state_manager)

        alerts = [
            Alert(
                status="firing",
                labels={"alertname": "Test", "severity": "warning", "pod": "pod-1"},
                startsAt=datetime.now(),
            ),
            Alert(
                status="firing",
                labels={"alertname": "Test", "severity": "warning", "pod": "pod-2"},
                startsAt=datetime.now(),
            ),
        ]
        common = processor._compute_common_labels(alerts)
        assert common == {"alertname": "Test", "severity": "warning"}
        assert "pod" not in common

    def test_compute_common_labels_no_overlap(self):
        config = Config(settings=Settings())
        state_manager = StateManager(config)
        processor = AlertProcessor(config, state_manager)

        alerts = [
            Alert(
                status="firing",
                labels={"foo": "bar"},
                startsAt=datetime.now(),
            ),
            Alert(
                status="firing",
                labels={"baz": "qux"},
                startsAt=datetime.now(),
            ),
        ]
        common = processor._compute_common_labels(alerts)
        assert common == {}

    def test_compute_common_labels_empty_list(self):
        config = Config(settings=Settings())
        state_manager = StateManager(config)
        processor = AlertProcessor(config, state_manager)

        common = processor._compute_common_labels([])
        assert common == {}

    def test_compute_common_labels_single_alert(self):
        config = Config(settings=Settings())
        state_manager = StateManager(config)
        processor = AlertProcessor(config, state_manager)

        alerts = [
            Alert(
                status="firing",
                labels={"alertname": "Test", "severity": "critical"},
                startsAt=datetime.now(),
            ),
        ]
        common = processor._compute_common_labels(alerts)
        assert common == {"alertname": "Test", "severity": "critical"}

    def test_compute_common_annotations_partial_overlap(self):
        config = Config(settings=Settings())
        state_manager = StateManager(config)
        processor = AlertProcessor(config, state_manager)

        alerts = [
            Alert(
                status="firing",
                labels={},
                annotations={"summary": "High memory", "description": "Pod pod-1 high"},
                startsAt=datetime.now(),
            ),
            Alert(
                status="firing",
                labels={},
                annotations={"summary": "High memory", "description": "Pod pod-2 high"},
                startsAt=datetime.now(),
            ),
        ]
        common = processor._compute_common_annotations(alerts)
        assert common == {"summary": "High memory"}
        assert "description" not in common

    def test_compute_common_annotations_empty_list(self):
        config = Config(settings=Settings())
        state_manager = StateManager(config)
        processor = AlertProcessor(config, state_manager)

        common = processor._compute_common_annotations([])
        assert common == {}


def test_group_model_with_deduplication_window():
    from src.models import Group, MatchRule, MatchType

    group = Group(
        name="test-group",
        destinations=["slack"],
        match=[MatchRule(type=MatchType.ALWAYS_MATCH)],
        group_by=["alertname"],
        deduplication_window=3600,
    )

    assert group.deduplication_window == 3600
    assert group.name == "test-group"


def test_group_deduplication_window_negative_raises_error():
    from src.models import Group, MatchRule, MatchType
    import pytest

    with pytest.raises(ValueError, match="deduplication_window must be >= 0"):
        Group(
            name="test-group",
            destinations=["slack"],
            match=[MatchRule(type=MatchType.ALWAYS_MATCH)],
            deduplication_window=-1,
        )


@pytest.mark.asyncio
async def test_should_send_group_with_deduplication_window():
    import time
    from src.models import Alert, Config, Settings
    from src.state import StateManager
    from src.fingerprint import FingerprintStrategy

    config = Config(settings=Settings(fingerprint_strategy=FingerprintStrategy.AUTO))
    state_mgr = StateManager(config)

    alert1 = Alert(
        status="firing",
        labels={"alertname": "TestAlert", "severity": "critical"},
        startsAt=datetime.now(),
        fingerprint="fp1",
    )
    alert2 = Alert(
        status="firing",
        labels={"alertname": "TestAlert", "severity": "warning"},
        startsAt=datetime.now(),
        fingerprint="fp2",
    )

    result1 = await state_mgr.should_send_group(
        [alert1, alert2], "alertname=TestAlert", "test-group", deduplication_window=0
    )
    assert result1 is True

    result2 = await state_mgr.should_send_group(
        [alert1, alert2], "alertname=TestAlert", "test-group", deduplication_window=0
    )
    assert result2 is False

    time.sleep(2)

    result3 = await state_mgr.should_send_group(
        [alert1, alert2], "alertname=TestAlert", "test-group", deduplication_window=0
    )
    assert result3 is False


@pytest.mark.asyncio
async def test_should_send_group_with_one_second_window():
    import time
    from src.models import Alert, Config, Settings
    from src.state import StateManager
    from src.fingerprint import FingerprintStrategy

    config = Config(settings=Settings(fingerprint_strategy=FingerprintStrategy.AUTO))
    state_mgr = StateManager(config)

    alert = Alert(
        status="firing",
        labels={"alertname": "TestAlert"},
        startsAt=datetime.now(),
        fingerprint="fp1",
    )

    result1 = await state_mgr.should_send_group(
        [alert], "alertname=TestAlert", "test-group", deduplication_window=1
    )
    assert result1 is True

    result2 = await state_mgr.should_send_group(
        [alert], "alertname=TestAlert", "test-group", deduplication_window=1
    )
    assert result2 is False

    time.sleep(1.1)

    result3 = await state_mgr.should_send_group(
        [alert], "alertname=TestAlert", "test-group", deduplication_window=1
    )
    assert result3 is True


@pytest.mark.asyncio
async def test_should_send_group_with_zero_window_never_resends():
    import time
    from src.models import Alert, Config, Settings
    from src.state import StateManager
    from src.fingerprint import FingerprintStrategy

    config = Config(settings=Settings(fingerprint_strategy=FingerprintStrategy.AUTO))
    state_mgr = StateManager(config)

    alert = Alert(
        status="firing",
        labels={"alertname": "TestAlert"},
        startsAt=datetime.now(),
        fingerprint="fp1",
    )

    result1 = await state_mgr.should_send_group(
        [alert], "alertname=TestAlert", "test-group", deduplication_window=0
    )
    assert result1 is True

    time.sleep(0.5)

    result2 = await state_mgr.should_send_group(
        [alert], "alertname=TestAlert", "test-group", deduplication_window=0
    )
    assert result2 is False
