#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm observability integration tests."""

import asyncio
import json
import logging
import time
import urllib.parse
import urllib.request
from base64 import b64encode
from typing import Any, Callable

import pytest
import pytest_asyncio
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import APP_NAME, APP_NAME_SERVER, get_unit_url, run_sample_workflow
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

PROMETHEUS_NAME = "prometheus-k8s"
GRAFANA_NAME = "grafana-k8s"
LOKI_NAME = "loki-k8s"
COS_APPS = (PROMETHEUS_NAME, GRAFANA_NAME, LOKI_NAME)
COS_CHANNEL = "1/stable"

PROMETHEUS_PORT = 9090
GRAFANA_PORT = 3000
LOKI_PORT = 3100

ALERT_RULES = (
    "TemporalWorkerDown",
    "TemporalWorkerMetricsMissing",
    "TemporalWorkerNoPollers",
    "TemporalWorkerPollFailuresHigh",
    "TemporalWorkerUnableToPoll",
)

DASHBOARD_TITLE = "Temporal Worker SDK Metrics"
DASHBOARD_PANELS = ("Worker Up", "Active Pollers", "Poll Success Rate", "Worker Logs")

LOG_LOOKBACK_SECONDS = 60 * 60


async def _get_json(url: str, params: dict | None = None, auth: tuple[str, str] | None = None) -> Any:
    """Send a GET request and return the decoded JSON body.

    Args:
        url: URL to request.
        params: Optional query parameters.
        auth: Optional (username, password) for HTTP basic auth.

    Returns:
        The decoded JSON response.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url)
    if auth:
        request.add_header("Authorization", "Basic " + b64encode(":".join(auth).encode()).decode())

    def _fetch():
        """Perform the blocking request.

        Returns:
            The decoded JSON response.
        """
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            return json.loads(response.read())

    return await asyncio.to_thread(_fetch)


async def _poll_until(check: Callable, message: str, timeout: int = 600, interval: int = 15):
    """Await `check` until it returns a truthy value.

    Errors raised by `check` (e.g. a service not being reachable yet) are logged and retried.

    Args:
        check: Async callable returning a truthy value once the condition is met.
        message: Failure message used if the condition is never met.
        timeout: Maximum time to wait, in seconds.
        interval: Time between attempts, in seconds.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            if await check():
                return
        except Exception as e:  # pylint: disable=broad-except
            logger.info("Check not satisfied yet: %s", e)
        if time.monotonic() > deadline:
            pytest.fail(message)
        await asyncio.sleep(interval)


async def _prometheus_query(ops_test: OpsTest, query: str) -> list:
    """Run an instant PromQL query and return its result vector.

    Args:
        ops_test: PyTest object.
        query: PromQL query.

    Returns:
        The list of samples in the result vector.
    """
    url = await get_unit_url(ops_test, PROMETHEUS_NAME, 0, PROMETHEUS_PORT)
    response = await _get_json(f"{url}/api/v1/query", {"query": query})
    return response["data"]["result"]


async def _alert_rule_states(ops_test: OpsTest) -> dict:
    """Return the state of every alert rule Prometheus has loaded, keyed by name.

    Args:
        ops_test: PyTest object.

    Returns:
        Mapping of alert rule names to their state (inactive, pending or firing).
    """
    url = await get_unit_url(ops_test, PROMETHEUS_NAME, 0, PROMETHEUS_PORT)
    response = await _get_json(f"{url}/api/v1/rules", {"type": "alert"})
    return {rule["name"]: rule["state"] for group in response["data"]["groups"] for rule in group["rules"]}


@pytest_asyncio.fixture(scope="module", name="observed_stack")
async def observed_stack_fixture(ops_test: OpsTest, deploy):  # noqa: F811 pylint: disable=W0621
    """Deploy Prometheus, Grafana and Loki and relate them to the worker.

    Args:
        ops_test: PyTest object.
        deploy: Fixture deploying the worker and the Temporal ecosystem.
    """
    # Allow re-running against an existing model (--model) that already has COS deployed.
    if not set(COS_APPS) <= set(ops_test.model.applications):
        await asyncio.gather(
            *(ops_test.model.deploy(app, channel=COS_CHANNEL, trust=True) for app in COS_APPS),
        )
        await ops_test.model.integrate(f"{APP_NAME}:metrics-endpoint", f"{PROMETHEUS_NAME}:metrics-endpoint")
        await ops_test.model.integrate(f"{APP_NAME}:grafana-dashboard", f"{GRAFANA_NAME}:grafana-dashboard")
        await ops_test.model.integrate(f"{APP_NAME}:logging", f"{LOKI_NAME}:logging")

    # COS charms patch their own pod resources on startup, which restarts the pod and can
    # fail a hook transiently; Juju retries it, so only require that they end up active.
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME, *COS_APPS],
            status="active",
            raise_on_blocked=False,
            raise_on_error=False,
            idle_period=30,
            timeout=1200,
        )


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("observed_stack")
class TestObservability:
    """Integration tests for the worker's metrics, alerts, dashboard and logs."""

    async def test_metrics_are_scraped(self, ops_test: OpsTest):
        """Prometheus scrapes the worker, which reports itself up with active pollers."""

        async def _worker_up_with_pollers():
            """Check the worker is up and has active pollers.

            Returns:
                Whether every worker unit is up and the worker has at least one poller.
            """
            up = await _prometheus_query(ops_test, f'up{{juju_application="{APP_NAME}"}}')
            pollers = await _prometheus_query(ops_test, f'sum(temporal_num_pollers{{juju_application="{APP_NAME}"}})')
            logger.info("up=%s pollers=%s", up, pollers)
            return (
                up and all(sample["value"][1] == "1" for sample in up) and pollers and float(pollers[0]["value"][1]) > 0
            )

        await _poll_until(_worker_up_with_pollers, "Prometheus never saw the worker up with active pollers")

    async def test_alert_rules_are_loaded(self, ops_test: OpsTest):
        """The alert rules the charm ships are loaded into Prometheus and are not firing."""

        async def _rules_loaded():
            """Check the charm's alert rules are loaded.

            Returns:
                Whether every expected alert rule is loaded.
            """
            states = await _alert_rule_states(ops_test)
            logger.info("Alert rule states: %s", states)
            return set(ALERT_RULES) <= set(states)

        await _poll_until(_rules_loaded, f"Prometheus never loaded the alert rules {ALERT_RULES}")

        states = await _alert_rule_states(ops_test)
        firing = [name for name in ALERT_RULES if states[name] == "firing"]
        assert not firing, f"alert rules firing on a healthy worker: {firing}"

    async def test_grafana_dashboard_is_published(self, ops_test: OpsTest):
        """The dashboard the charm ships, including the worker health panels, shows up in Grafana."""
        url = await get_unit_url(ops_test, GRAFANA_NAME, 0, GRAFANA_PORT)
        action = await ops_test.model.applications[GRAFANA_NAME].units[0].run_action("get-admin-password")
        password = (await action.wait()).results["admin-password"]
        auth = ("admin", password)

        async def _dashboard_published():
            """Check the dashboard and its worker health panels are published.

            Returns:
                Whether the dashboard is published.
            """
            dashboards = await _get_json(f"{url}/api/search", {"type": "dash-db"}, auth)
            matches = [entry for entry in dashboards if entry.get("title") == DASHBOARD_TITLE]
            if not matches:
                return False
            dashboard = await _get_json(f"{url}/api/dashboards/uid/{matches[0]['uid']}", auth=auth)
            titles = {panel.get("title") for panel in dashboard["dashboard"]["panels"]}
            missing = set(DASHBOARD_PANELS) - titles
            assert not missing, f"dashboard is missing panels: {missing}"
            return True

        await _poll_until(_dashboard_published, f"Grafana never loaded the '{DASHBOARD_TITLE}' dashboard")

    async def test_logs_are_forwarded(self, ops_test: OpsTest):
        """Loki receives log lines from the temporal-worker service."""
        # The sample worker logs nothing while idle, and Pebble only forwards lines written
        # after the logging relation is set up, so run a workflow to make it log.
        await run_sample_workflow(ops_test)

        url = await get_unit_url(ops_test, LOKI_NAME, 0, LOKI_PORT)
        query = f'{{juju_application="{APP_NAME}", pebble_service="temporal-worker"}} |= "Running workflow"'

        async def _logs_received():
            """Check Loki has worker log lines.

            Returns:
                Whether Loki returned any matching log streams.
            """
            now = time.time_ns()
            response = await _get_json(
                f"{url}/loki/api/v1/query_range",
                {
                    "query": query,
                    "start": str(now - LOG_LOOKBACK_SECONDS * 1_000_000_000),
                    "end": str(now),
                    "limit": "5",
                    "direction": "backward",
                },
            )
            return bool(response["data"]["result"])

        await _poll_until(_logs_received, f"Loki never received logs matching {query}")

    async def test_unable_to_poll_alert_fires(self, ops_test: OpsTest):
        """Taking the Temporal server away fires TemporalWorkerUnableToPoll while the worker stays up.

        This must run last in the module as it temporarily removes the Temporal server.
        """
        await ops_test.model.applications[APP_NAME_SERVER].scale(0)
        try:

            async def _unable_to_poll_firing():
                """Check whether TemporalWorkerUnableToPoll is firing.

                Returns:
                    Whether the alert is firing.
                """
                states = await _alert_rule_states(ops_test)
                logger.info("Alert rule states: %s", states)
                return states.get("TemporalWorkerUnableToPoll") == "firing"

            # The rule needs 3m without a successful poll plus 2m pending.
            await _poll_until(_unable_to_poll_firing, "TemporalWorkerUnableToPoll never fired", timeout=900)

            states = await _alert_rule_states(ops_test)
            assert states["TemporalWorkerDown"] != "firing", "worker process should still be up"
        finally:
            await ops_test.model.applications[APP_NAME_SERVER].scale(1)
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME_SERVER, APP_NAME], status="active", raise_on_blocked=False, timeout=900
            )
