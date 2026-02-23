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
            logger.error(f"Failed to render/send grouped message: {e}")
            return False

    def _do_send(self, payload: str) -> bool:
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(
                        self.destination.webhook_url,
                        content=payload.encode(),
                        headers={"Content-Type": "application/json"}
                    )
                    if response.status_code < 400:
                        return True
                    logger.warning(f"Webhook returned {response.status_code}: {response.text}")
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

            if attempt < self.max_retries - 1:
                import time
                time.sleep(2 ** attempt)

        return False

    async def _do_send_async(self, payload: str) -> bool:
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        self.destination.webhook_url,
                        content=payload.encode(),
                        headers={"Content-Type": "application/json"}
                    )
                    if response.status_code < 400:
                        return True
                    logger.warning(f"Webhook returned {response.status_code}: {response.text}")
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return False


class SlackSender(BaseSender):
    def send(self, context: AlertContext) -> bool:
        try:
            payload = self.template_engine.render(self.destination.template, context)
            return self._do_send(payload)
        except Exception as e:
            logger.error(f"Failed to render/send Slack message: {e}")
            return False

    async def send_async(self, context: AlertContext) -> bool:
        try:
            payload = self.template_engine.render(self.destination.template, context)
            return await self._do_send_async(payload)
        except Exception as e:
            logger.error(f"Failed to render/send Slack message: {e}")
            return False

    async def send_grouped_async(self, context: GroupedAlertContext) -> bool:
        try:
            payload = self.template_engine.render_grouped(self.destination.template, context)
            return await self._do_send_async(payload)
        except Exception as e:
            logger.error(f"Failed to render/send grouped Slack message: {e}")
            return False


class DiscordSender(BaseSender):
    def send(self, context: AlertContext) -> bool:
        try:
            payload = self.template_engine.render(self.destination.template, context)
            return self._do_send(payload)
        except Exception as e:
            logger.error(f"Failed to render/send Discord message: {e}")
            return False

    async def send_async(self, context: AlertContext) -> bool:
        try:
            payload = self.template_engine.render(self.destination.template, context)
            return await self._do_send_async(payload)
        except Exception as e:
            logger.error(f"Failed to render/send Discord message: {e}")
            return False

    async def send_grouped_async(self, context: GroupedAlertContext) -> bool:
        try:
            payload = self.template_engine.render_grouped(self.destination.template, context)
            return await self._do_send_async(payload)
        except Exception as e:
            logger.error(f"Failed to render/send grouped Discord message: {e}")
            return False


def create_sender(destination: Destination, template_engine: TemplateEngine) -> BaseSender:
    sender_type = destination.type.lower()
    if sender_type == "slack":
        return SlackSender(destination, template_engine)
    elif sender_type == "discord":
        return DiscordSender(destination, template_engine)
    else:
        raise ValueError(f"Unknown destination type: {destination.type}")
