# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Temporal client sample workflow."""

# pylint: disable=R0801

from datetime import timedelta

from temporalio import workflow

# Import our activity, passing it through the sandbox
with workflow.unsafe.imports_passed_through():
    from .activities import ComposeGreetingInput, compose_greeting


# Basic workflow that logs and invokes an activity
@workflow.defn(name="GreetingWorkflow")
class GreetingWorkflow:
    """Temporal workflow class."""

    @workflow.run
    async def run(self, name: str) -> str:
        """Workflow execution method.

        Args:
            name: input for workflow execution.

        Returns:
            Workflow execution result.
        """
        workflow.logger.info(f"Running workflow with parameter {name}")
        return await workflow.execute_activity(
            compose_greeting,
            ComposeGreetingInput("Hello", name),
            start_to_close_timeout=timedelta(seconds=10),
        )
