import logging
import re
from typing import List

from src.models import Alert, Group, MatchRule, MatchType

logger = logging.getLogger(__name__)


def matches_rule(alert: Alert, rule: MatchRule) -> bool:
    if rule.type == MatchType.ALWAYS_MATCH:
        return True

    label_or_annotation = None
    if rule.type.startswith("label_"):
        label_or_annotation = alert.labels
    elif rule.type.startswith("annotation_"):
        label_or_annotation = alert.annotations

    if label_or_annotation is None:
        return False

    key = rule.label
    if key not in label_or_annotation:
        return False

    value = label_or_annotation[key]

    if rule.type in (MatchType.LABEL_EQUALS, MatchType.ANNOTATION_EQUALS):
        return value in (rule.values or [])

    if rule.type in (MatchType.LABEL_NOT_EQUALS, MatchType.ANNOTATION_NOT_EQUALS):
        return value not in (rule.values or [])

    if rule.type in (MatchType.LABEL_CONTAINS, MatchType.ANNOTATION_CONTAINS):
        return rule.substring and rule.substring in value

    if rule.type in (MatchType.LABEL_NOT_CONTAINS, MatchType.ANNOTATION_NOT_CONTAINS):
        return rule.substring and rule.substring not in value

    if rule.type in (MatchType.LABEL_MATCHES, MatchType.ANNOTATION_MATCHES):
        if rule.pattern:
            return bool(re.match(rule.pattern, value))
        return False

    if rule.type in (MatchType.LABEL_NOT_MATCHES, MatchType.ANNOTATION_NOT_MATCHES):
        if rule.pattern:
            return not bool(re.match(rule.pattern, value))
        return True

    return False


def alert_matches_filters(alert: Alert, group: Group) -> bool:
    if not group.filters:
        return True

    for rule in group.filters:
        if not matches_rule(alert, rule):
            return False

    return True


def alert_matches_group(alert: Alert, group: Group) -> bool:
    if not alert_matches_filters(alert, group):
        return False

    for rule in group.match:
        if matches_rule(alert, rule):
            return True
    return False


def get_matching_groups(alert: Alert, groups: List[Group]) -> List[Group]:
    matching = []
    for group in groups:
        if alert_matches_group(alert, group):
            matching.append(group)

    if matching:
        logger.debug(
            "Alert matched groups",
            extra={
                "matched_group_names": [g.name for g in matching],
                "total_groups_checked": len(groups),
            },
        )

    return matching
