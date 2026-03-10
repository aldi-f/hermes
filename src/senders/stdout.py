import logging

from src.models import AlertContext, GroupedAlertContext
from src.senders.base_sender import BaseSender

logger = logging.getLogger(__name__)


class StdoutSender(BaseSender):
    def send(self, context: AlertContext) -> bool:
        try:
            payload = self.template_engine.render(self.destination.template, context)
            print(payload)
            logger.info(
                "Successfully sent message to stdout",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                },
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to render/send message to stdout",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False

    async def send_async(self, context: AlertContext) -> bool:
        try:
            payload = self.template_engine.render(self.destination.template, context)
            print(payload)
            logger.info(
                "Successfully sent message to stdout (async)",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                },
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to render/send message to stdout (async)",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False

    async def send_grouped_async(self, context: GroupedAlertContext) -> bool:
        try:
            payload = self.template_engine.render_grouped(self.destination.template, context)
            print(payload)
            logger.info(
                "Successfully sent grouped message to stdout (async)",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                },
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to render/send grouped message to stdout (async)",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False
