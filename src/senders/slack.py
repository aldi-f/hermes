import logging

from src.models import AlertContext, GroupedAlertContext
from src.senders.base_sender import BaseSender

logger = logging.getLogger(__name__)


class SlackSender(BaseSender):
    def _render_payload(self, context: GroupedAlertContext) -> str:
        template_config = self.destination.template
        if template_config.structured:
            st = template_config.structured
            if st.blockkit:
                return self.template_engine.render_blockkit(st.blockkit, context)
            elif st.attachment:
                return self.template_engine.render_attachment(st.attachment, context)
        return self.template_engine.render_grouped(template_config, context)

    def send(self, context: AlertContext) -> bool:
        try:
            payload = self._render_payload(context)
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
            payload = self._render_payload(context)
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
            payload = self._render_payload(context)
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
