import logging

from src.models import AlertContext, GroupedAlertContext
from src.senders.base_sender import BaseSender

logger = logging.getLogger(__name__)


class DiscordSender(BaseSender):
    def _render_payload(self, context: GroupedAlertContext) -> str:
        template_config = self.destination.template
        if template_config.structured and template_config.structured.embed:
            return self.template_engine.render_embed(template_config.structured.embed, context)
        return self.template_engine.render_grouped(template_config, context)

    def send(self, context: AlertContext) -> bool:
        try:
            payload = self._render_payload(context)
            return self._do_send(payload)
        except Exception as e:
            logger.error(
                "Failed to render/send Discord message",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False

    async def send_async(self, context: AlertContext) -> bool:
        try:
            payload = self._render_payload(context)
            return await self._do_send_async(payload)
        except Exception as e:
            logger.error(
                "Failed to render/send Discord message (async)",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False

    async def send_grouped_async(self, context: GroupedAlertContext) -> bool:
        try:
            payload = self._render_payload(context)
            return await self._do_send_async(payload)
        except Exception as e:
            logger.error(
                "Failed to render/send grouped Discord message (async)",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False
