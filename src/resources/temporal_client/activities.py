# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Temporal sample activity."""

from dataclasses import dataclass

from temporalio import activity


@dataclass
class ComposeGreetingInput:
    """Greeting class.

    Attrs:
        greeting: abc.
        name: abc.
    """

    greeting: str
    name: str


@activity.defn(name="compose_greeting")
async def compose_greeting(arg: ComposeGreetingInput) -> str:
    """Log and do string concatenation activity.

    Args:
        arg: greeting to log.

    Returns:
        Greeting string.
    """
    activity.logger.info(f"Running activity with parameter {arg}")
    return f"{arg.greeting}, {arg.name}!"
