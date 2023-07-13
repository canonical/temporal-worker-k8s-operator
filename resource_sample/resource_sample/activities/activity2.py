# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from temporalio import activity
from dataclasses import dataclass
from resource_sample.common.messages import ComposeGreetingInput

# Basic activity that logs and does string concatenation
@activity.defn(name="compose_greeting2")
async def compose_greeting2(arg: ComposeGreetingInput) -> str:
    activity.logger.info("Running activity with parameter %s" % arg)
    return f"{arg.greeting}, {arg.name}!"
