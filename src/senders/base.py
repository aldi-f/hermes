import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

from src.models import AlertContext, Destination, GroupedAlertContext
from src.templates import TemplateEngine

logger = logging.getLogger(__name__)


class BaseSender(ABC):
    def __init__(self, destination: Destination, template_engine: TemplateEngine):
        self.destination = destination
        self.template_engine = template_engine
        self.max_retries = 3

    @abstractmethod
    def send(self, context: AlertContext) -> bool:
        pass

    async def send_async(self, context: AlertContext) -> bool:
        return await asyncio.to_thread(self.send, context)

    async def send_grouped_async(self, context: GroupedAlertContext) -> bool:
        return await asyncio.to_thread(self.send_grouped, context)

    def send_grouped(self, context: GroupedAlertContext) -> bool:
        try:
            payload = self.template_engine.render_grouped(self.destination.template, context)
            return self._do_send(payload)
        except Exception as e:
            logger.error(
                "Failed to render/send grouped message",
                extra={
                    "destination": self.destination.name,
                    "destination_type": self.destination.type,
                    "error": str(e),
                },
            )
            return False

    def _do_send(self, payload: str) -> bool:
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(
                        self.destination.webhook_url,
                        content=payload.encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    if response.status_code < 400:
                        logger.info(
                            "Successfully sent webhook",
                            extra={
                                "destination": self.destination.name,
                                "destination_type": self.destination.type,
                                "status_code": response.status_code,
                                "attempt": attempt + 1,
                            },
                        )
                        return True
                    logger.warning(
                        "Webhook returned non-success status",
                        extra={
                            "destination": self.destination.name,
                            "destination_type": self.destination.type,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                        },
                    )
            except Exception as e:
                logger.warning(
                    "Send attempt failed",
                    extra={
                        "destination": self.destination.name,
                        "destination_type": self.destination.type,
                        "attempt": attempt + 1,
                        "error": str(e),
                    },
                )

            if attempt < self.max_retries - 1:
                import time

                time.sleep(2**attempt)

        return False

    async def _do_send_async(self, payload: str) -> bool:
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        self.destination.webhook_url,
                        content=payload.encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    if response.status_code < 400:
                        logger.info(
                            "Successfully sent webhook (async)",
                            extra={
                                "destination": self.destination.name,
                                "destination_type": self.destination.type,
                                "status_code": response.status_code,
                                "attempt": attempt + 1,
                            },
                        )
                        return True
                    logger.warning(
                        "Webhook returned non-success status (async)",
                        extra={
                            "destination": self.destination.name,
                            "destination_type": self.destination.type,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                            "text": response.text,
                        },
                    )
            except Exception as e:
                logger.warning(
                    "Send attempt failed (async)",
                    extra={
                        "destination": self.destination.name,
                        "destination_type": self.destination.type,
                        "attempt": attempt + 1,
                        "error": str(e),
                    },
                )

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2**attempt)

        return False


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


class DiscordSender(BaseSender):
    def send(self, context: AlertContext) -> bool:
        try:
            payload = self.template_engine.render(self.destination.template, context)
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
            payload = self.template_engine.render(self.destination.template, context)
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
            payload = self.template_engine.render_grouped(self.destination.template, context)
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


def create_sender(destination: Destination, template_engine: TemplateEngine) -> BaseSender:
    sender_type = destination.type.lower()
    if sender_type == "slack":
        return SlackSender(destination, template_engine)
    elif sender_type == "discord":
        return DiscordSender(destination, template_engine)
    else:
        raise ValueError(f"Unknown destination type: {destination.type}")
