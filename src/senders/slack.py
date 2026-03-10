import logging

from src.models import AlertContext, GroupedAlertContext
from src.senders.base_sender import BaseSender

logger = logging.getLogger(__name__)


class SlackSender(BaseSender):
    def send(self, context: AlertContext) -> bool:
        try:
            if self.destination.attachments_template:
                payload = self.template_engine.render(
                    self.destination.attachments_template, context
                )
            else:
                payload = self.template_engine.render(self.destination.template, context)
            return self._do_send(payload)
        except Exception as e:
            logger.error(
                "Failed to render/send Slack message",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False

    async def send_async(self, context: AlertContext) -> bool:
        try:
            if self.destination.attachments_template:
                payload = self.template_engine.render(
                    self.destination.attachments_template, context
                )
            else:
                payload = self.template_engine.render(self.destination.template, context)
            return await self._do_send_async(payload)
        except Exception as e:
            logger.error(
                "Failed to render/send Slack message (async)",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False

    async def send_grouped_async(self, context: GroupedAlertContext) -> bool:
        try:
            if self.destination.attachments_template:
                payload = self.template_engine.render_grouped(
                    self.destination.attachments_template, context
                )
            else:
                payload = self.template_engine.render_grouped(self.destination.template, context)
            return await self._do_send_async(payload)
        except Exception as e:
            logger.error(
                "Failed to render/send grouped Slack message (async)",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False
