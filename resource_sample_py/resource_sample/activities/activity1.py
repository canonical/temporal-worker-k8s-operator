# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from common.messages import ComposeGreetingInput
from temporalio import activity
import os


# Basic activity that logs and does string concatenation
@activity.defn(name="compose_greeting")
async def compose_greeting(arg: ComposeGreetingInput) -> str:
    activity.logger.info("Running activity with parameter %s" % arg)
    sensitive1 = os.getenv("sensitive1")
    sensitive2 = os.getenv("sensitive2")
    
    return f"{sensitive1} {sensitive2}"
    
    # return f"{arg.greeting}, {arg.name}!"
