# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


"""Temporal sample workflow."""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from .activities import ComposeGreetingInput, compose_greeting


@workflow.defn(name="GreetingWorkflow")
class GreetingWorkflow:
    """Basic workflow that logs and invokes an activity."""

    @workflow.run
    async def run(self, name: str) -> str:
        """Workflow runner.

        Args:
            name: value to be logged.

        Returns:
            Workflow execution.
        """
        workflow.logger.info(f"Running workflow with parameter {name}")
        return await workflow.execute_activity(
            compose_greeting,
            ComposeGreetingInput("Hello", name),
            start_to_close_timeout=timedelta(seconds=10),
        )
