from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, model_validator


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


class TemplatePart(BaseModel):
    content: str


class SlackBlockKitStructured(BaseModel):
    header: Optional[TemplatePart] = None
    body: Optional[TemplatePart] = None
    footer: Optional[TemplatePart] = None


class SlackAttachmentStructured(BaseModel):
    color: str
    body: TemplatePart


class DiscordEmbedStructured(BaseModel):
    header: Optional[TemplatePart] = None
    body: Optional[TemplatePart] = None
    footer: Optional[TemplatePart] = None


class StructuredTemplate(BaseModel):
    blockkit: Optional[SlackBlockKitStructured] = None
    attachment: Optional[SlackAttachmentStructured] = None
    embed: Optional[DiscordEmbedStructured] = None


class TemplateConfig(BaseModel):
    path: Optional[str] = None
    content: Optional[str] = None
    structured: Optional[StructuredTemplate] = None


class Destination(BaseModel):
    name: str
    type: str
    webhook_url: Optional[str] = None
    template: TemplateConfig = Field(default_factory=TemplateConfig)

    @model_validator(mode="after")
    def validate_template(self):
        has_raw = self.template.content is not None or self.template.path is not None
        has_structured = self.template.structured is not None

        if has_raw and has_structured:
            raise ValueError(
                f"Destination '{self.name}' cannot have both 'raw' and 'structured' in template. "
                "Specify only one."
            )

        if not has_raw and not has_structured:
            raise ValueError(
                f"Destination '{self.name}' must have either 'raw' or 'structured' in template."
            )

        if has_structured:
            st = self.template.structured
            if self.type.lower() == "slack":
                structured_count = sum(1 for x in [st.blockkit, st.attachment] if x is not None)
                if structured_count != 1:
                    raise ValueError(
                        f"Slack destination '{self.name}' must have exactly one of 'blockkit' or 'attachment' in structured template."
                    )
            elif self.type.lower() == "discord":
                if st.embed is None:
                    raise ValueError(
                        f"Discord destination '{self.name}' must have 'embed' in structured template."
                    )
        elif self.type.lower() == "stdout":
            raise ValueError(f"Stdout destination '{self.name}' must have a template configured.")

        return self


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
    filters: list[MatchRule] = Field(default_factory=list)
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
    common_labels: Dict[str, str] = Field(default_factory=dict)
    common_annotations: Dict[str, str] = Field(default_factory=dict)
    status: str
    group_name: str
    destination_name: str


class AlertState(BaseModel):
    fingerprint: str
    group_name: str
    status: str
    last_seen: float
    alert: Optional[Alert] = None
    metadata: Optional[Dict[str, Any]] = None
