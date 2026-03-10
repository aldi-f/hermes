from src.models import Destination
from src.senders.discord import DiscordSender
from src.senders.slack import SlackSender
from src.senders.stdout import StdoutSender
from src.templates import TemplateEngine

from .base_sender import BaseSender


def create_sender(destination: Destination, template_engine: TemplateEngine) -> BaseSender:
    sender_type = destination.type.lower()
    if sender_type == "slack":
        return SlackSender(destination, template_engine)
    elif sender_type == "discord":
        return DiscordSender(destination, template_engine)
    elif sender_type == "stdout":
        return StdoutSender(destination, template_engine)
    else:
        raise ValueError(f"Unknown destination type: {destination.type}")
