import logging
from pathlib import Path
from typing import Optional

from jinja2 import BaseLoader, Environment, Template, TemplateNotFound

from src.models import AlertContext, GroupedAlertContext, TemplateConfig

logger = logging.getLogger(__name__)


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

    def render(self, template_config: TemplateConfig, context: AlertContext) -> str:
        if template_config.content:
            template = Template(template_config.content)
        elif template_config.path:
            cache_key = template_config.path
            if cache_key not in self._cache:
                self._cache[cache_key] = self.env.get_template(template_config.path)
            template = self._cache[cache_key]
        else:
            raise ValueError("Template must have either path or content")

        return template.render(
            status=context.status,
            labels=context.labels,
            annotations=context.annotations,
            startsAt=context.startsAt,
            endsAt=context.endsAt,
            generatorURL=context.generatorURL,
            fingerprint=context.fingerprint,
            group_name=context.group_name,
            destination_name=context.destination_name,
        )

    def render_grouped(self, template_config: TemplateConfig, context: GroupedAlertContext) -> str:
        if template_config.content:
            template = Template(template_config.content)
        elif template_config.path:
            cache_key = template_config.path
            if cache_key not in self._cache:
                self._cache[cache_key] = self.env.get_template(template_config.path)
            template = self._cache[cache_key]
        else:
            raise ValueError("Template must have either path or content")

        return template.render(
            alerts=context.alerts,
            group_labels=context.group_labels,
            common_labels=context.common_labels,
            common_annotations=context.common_annotations,
            status=context.status,
            group_name=context.group_name,
            destination_name=context.destination_name,
        )
