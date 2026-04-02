import json
import logging
import os
from pathlib import Path
from typing import Optional

from jinja2 import BaseLoader, Environment, Template, TemplateNotFound

from src.models import (
    AlertContext,
    DiscordEmbedStructured,
    GroupedAlertContext,
    SlackAttachmentStructured,
    SlackBlockKitStructured,
    TemplateConfig,
)

logger = logging.getLogger(__name__)

SLACK_BODY_MAX_LENGTH = 3000
DISCORD_BODY_MAX_LENGTH = 4096
SLACK_HEADER_MAX_LENGTH = 150
TRUNCATION_SUFFIX = "... (truncated)"


class FileTemplateLoader(BaseLoader):
    def __init__(self, template_dir: str):
        self.template_dir = Path(template_dir)

    def get_source(self, environment, template):
        path = self.template_dir / template
        if not path.exists():
            raise TemplateNotFound(template)
        with open(path) as f:
            source = f.read()
        return source, str(path), lambda: True


class TemplateEngine:
    def __init__(self, template_dir: Optional[str] = None):
        if template_dir:
            self.env = Environment(loader=FileTemplateLoader(template_dir))
        else:
            self.env = Environment(loader=BaseLoader())
        self._cache: dict = {}

    def _get_base_context(self) -> dict:
        return {"env": dict(os.environ)}

    def _render_part(self, part_content: str, context: dict) -> str:
        template = Template(part_content)
        return template.render(**context)

    def _truncate_body(self, content: str, max_length: int) -> str:
        if len(content) <= max_length:
            return content
        return content[: max_length - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX

    def render(self, template_config: TemplateConfig, context: AlertContext) -> str:
        if template_config.content:
            template = Template(template_config.content)
        elif template_config.path:
            cache_key = template_config.path
            if cache_key not in self._cache:
                self._cache[cache_key] = self.env.get_template(template_config.path)
            template = self._cache[cache_key]
        else:
            raise ValueError("Template must have either content or path or structured")

        ctx = {
            **self._get_base_context(),
            "status": context.status,
            "labels": context.labels,
            "annotations": context.annotations,
            "startsAt": context.startsAt,
            "endsAt": context.endsAt,
            "generatorURL": context.generatorURL,
            "fingerprint": context.fingerprint,
            "group_name": context.group_name,
            "destination_name": context.destination_name,
        }
        return template.render(**ctx)

    def render_grouped(self, template_config: TemplateConfig, context: GroupedAlertContext) -> str:
        if template_config.content:
            template = Template(template_config.content)
        elif template_config.path:
            cache_key = template_config.path
            if cache_key not in self._cache:
                self._cache[cache_key] = self.env.get_template(template_config.path)
            template = self._cache[cache_key]
        else:
            raise ValueError("Template must have either content or path or structured")

        ctx = {
            **self._get_base_context(),
            "alerts": context.alerts,
            "group_labels": context.group_labels,
            "common_labels": context.common_labels,
            "common_annotations": context.common_annotations,
            "status": context.status,
            "group_name": context.group_name,
            "destination_name": context.destination_name,
        }
        return template.render(**ctx)

    def render_blockkit(
        self, structured: SlackBlockKitStructured, context: GroupedAlertContext
    ) -> str:
        ctx = {
            **self._get_base_context(),
            "alerts": context.alerts,
            "group_labels": context.group_labels,
            "common_labels": context.common_labels,
            "common_annotations": context.common_annotations,
            "status": context.status,
            "group_name": context.group_name,
            "destination_name": context.destination_name,
        }

        blocks = []

        if structured.header:
            header_content = self._render_part(structured.header.content, ctx)
            if len(header_content) > SLACK_HEADER_MAX_LENGTH:
                header_content = (
                    header_content[: SLACK_HEADER_MAX_LENGTH - len(TRUNCATION_SUFFIX)]
                    + TRUNCATION_SUFFIX
                )
            blocks.append(
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": header_content, "emoji": True},
                }
            )

        if structured.body:
            body_content = self._render_part(structured.body.content, ctx)
            body_content = self._truncate_body(body_content, SLACK_BODY_MAX_LENGTH)
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body_content}})

        if structured.footer:
            footer_content = self._render_part(structured.footer.content, ctx)
            blocks.append(
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": footer_content}],
                }
            )

        return json.dumps({"blocks": blocks})

    def render_attachment(
        self, structured: SlackAttachmentStructured, context: GroupedAlertContext
    ) -> str:
        ctx = {
            **self._get_base_context(),
            "alerts": context.alerts,
            "group_labels": context.group_labels,
            "common_labels": context.common_labels,
            "common_annotations": context.common_annotations,
            "status": context.status,
            "group_name": context.group_name,
            "destination_name": context.destination_name,
        }

        color = self._render_part(structured.color, ctx)
        body_content = self._render_part(structured.body.content, ctx)
        body_content = self._truncate_body(body_content, SLACK_BODY_MAX_LENGTH)

        attachment = {"color": color, "text": body_content, "mrkdwn_in": ["text"]}
        return json.dumps({"attachments": [attachment]})

    def render_embed(self, structured: DiscordEmbedStructured, context: GroupedAlertContext) -> str:
        ctx = {
            **self._get_base_context(),
            "alerts": context.alerts,
            "group_labels": context.group_labels,
            "common_labels": context.common_labels,
            "common_annotations": context.common_annotations,
            "status": context.status,
            "group_name": context.group_name,
            "destination_name": context.destination_name,
        }

        embed = {}

        if structured.header:
            header_content = self._render_part(structured.header.content, ctx)
            embed["title"] = header_content

        if structured.body:
            body_content = self._render_part(structured.body.content, ctx)
            body_content = self._truncate_body(body_content, DISCORD_BODY_MAX_LENGTH)
            embed["description"] = body_content

        if structured.footer:
            footer_content = self._render_part(structured.footer.content, ctx)
            embed["footer"] = {"text": footer_content}

        return json.dumps({"embeds": [embed]})
