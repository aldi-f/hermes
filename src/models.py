from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class FingerprintStrategy(str, Enum):
    AUTO = "auto"
    ALERTMANAGER = "alertmanager"
    CUSTOM = "custom"


class Settings(BaseModel):
    fingerprint_strategy: FingerprintStrategy = FingerprintStrategy.AUTO
    deduplication_ttl: int = 300
    metrics_port: int = 9090
    redis_url: Optional[str] = None
    redis_failure_threshold: int = 3
    redis_recovery_timeout: int = 60
    replay_queue_size: int = 1000
    sqlite_path: str = "/data/hermes.db"


class TemplateConfig(BaseModel):
    path: Optional[str] = None
    content: Optional[str] = None


class Destination(BaseModel):
    name: str
    type: str
    webhook_url: str
    template: TemplateConfig


class MatchType(str, Enum):
    LABEL_EQUALS = "label_equals"
    LABEL_CONTAINS = "label_contains"
    LABEL_MATCHES = "label_matches"
    LABEL_NOT_EQUALS = "label_not_equals"
    LABEL_NOT_CONTAINS = "label_not_contains"
    LABEL_NOT_MATCHES = "label_not_matches"
    ANNOTATION_EQUALS = "annotation_equals"
    ANNOTATION_CONTAINS = "annotation_contains"
    ANNOTATION_MATCHES = "annotation_matches"
    ANNOTATION_NOT_EQUALS = "annotation_not_equals"
    ANNOTATION_NOT_CONTAINS = "annotation_not_contains"
    ANNOTATION_NOT_MATCHES = "annotation_not_matches"
    ALWAYS_MATCH = "always_match"


class MatchRule(BaseModel):
    type: MatchType
    label: Optional[str] = None
    values: Optional[list[str]] = None
    pattern: Optional[str] = None
    substring: Optional[str] = None


class Group(BaseModel):
    name: str
    destinations: list[str]
    match: list[MatchRule]
    group_by: list[str] = Field(default_factory=list)


class Config(BaseModel):
    settings: Settings = Field(default_factory=Settings)
    destinations: list[Destination] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)


class Alert(BaseModel):
    status: str
    labels: Dict[str, str] = Field(default_factory=dict)
    annotations: Dict[str, str] = Field(default_factory=dict)
    startsAt: datetime
    endsAt: Optional[datetime] = None
    generatorURL: Optional[str] = None
    fingerprint: Optional[str] = None


class WebhookPayload(BaseModel):
    receiver: Optional[str] = None
    status: Optional[str] = None
    alerts: list[Alert] = Field(default_factory=list)
    groupLabels: Optional[Dict[str, str]] = None
    commonLabels: Optional[Dict[str, str]] = None
    commonAnnotations: Optional[Dict[str, str]] = None
    externalURL: Optional[str] = None


class AlertContext(BaseModel):
    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    startsAt: datetime
    endsAt: Optional[datetime]
    generatorURL: Optional[str]
    fingerprint: str
    group_name: str
    destination_name: str


class GroupedAlertContext(BaseModel):
    alerts: list[Alert]
    group_labels: Dict[str, str] = Field(default_factory=dict)
    status: str
    group_name: str
    destination_name: str


class AlertState(BaseModel):
    fingerprint: str
    group_name: str
    status: str
    last_seen: float
    alert: Optional[Alert] = None
