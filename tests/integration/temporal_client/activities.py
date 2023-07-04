# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Temporal client activity."""

# pylint: disable=R0801

from dataclasses import dataclass

from temporalio import activity


@dataclass
class ComposeGreetingInput:
    """GreetingInput class.

    Attrs:
        greeting: blah.
        name: blah.
    """

    greeting: str
    name: str


# Basic activity that logs and does string concatenation
@activity.defn(name="compose_greeting")
async def compose_greeting(arg: ComposeGreetingInput) -> str:
    """Temporal activity.

    Args:
        arg: ComposeGreetingInput used to run the dynamic activity.

    Returns:
        String in the form "Hello, {name}!
    """
    activity.logger.info(f"Running activity with parameter {arg}")
    return f"{arg.greeting}, {arg.name}!"
