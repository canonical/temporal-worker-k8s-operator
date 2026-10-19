#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal worker charm observability integration tests."""

import json
import logging
import time
import urllib.parse
import urllib.request
from base64 import b64encode
from typing import Any, Callable

import jubilant
import pytest
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    fast_forward,
    get_unit_url,
    run_sample_workflow,
)

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


def _get_json(url: str, params: dict | None = None, auth: tuple[str, str] | None = None) -> Any:
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
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
        return json.loads(response.read())


def _poll_until(check: Callable, message: str, timeout: int = 600, interval: int = 15):
    """Poll `check` until it returns a truthy value.

    Errors raised by `check` (e.g. a service not being reachable yet) are logged and retried.

    Args:
        check: Callable returning a truthy value once the condition is met.
        message: Failure message used if the condition is never met.
        timeout: Maximum time to wait, in seconds.
        interval: Time between attempts, in seconds.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            if check():
                return
        except Exception as e:  # pylint: disable=broad-except
            logger.info("Check not satisfied yet: %s", e)
        if time.monotonic() > deadline:
            pytest.fail(message)
        time.sleep(interval)


def _prometheus_query(juju: jubilant.Juju, query: str) -> list:
    """Run an instant PromQL query and return its result vector.

    Args:
        juju: Jubilant Juju client bound to the test model.
        query: PromQL query.

    Returns:
        The list of samples in the result vector.
    """
    url = get_unit_url(juju, PROMETHEUS_NAME, 0, PROMETHEUS_PORT)
    response = _get_json(f"{url}/api/v1/query", {"query": query})
    return response["data"]["result"]


def _alert_rule_states(juju: jubilant.Juju) -> dict:
    """Return the state of every alert rule Prometheus has loaded, keyed by name.

    Args:
        juju: Jubilant Juju client bound to the test model.

    Returns:
        Mapping of alert rule names to their state (inactive, pending or firing).
    """
    url = get_unit_url(juju, PROMETHEUS_NAME, 0, PROMETHEUS_PORT)
    response = _get_json(f"{url}/api/v1/rules", {"type": "alert"})
    return {rule["name"]: rule["state"] for group in response["data"]["groups"] for rule in group["rules"]}


@pytest.fixture(scope="module", name="observed_stack")
def observed_stack_fixture(juju: jubilant.Juju, deploy):  # noqa: F811 pylint: disable=W0621
    """Deploy Prometheus, Grafana and Loki and relate them to the worker.

    Args:
        juju: Jubilant Juju client bound to the test model.
        deploy: Fixture deploying the worker and the Temporal ecosystem.
    """
    if not set(COS_APPS) <= set(juju.status().apps):
        for app in COS_APPS:
            juju.deploy(app, channel=COS_CHANNEL, trust=True)
        juju.integrate(f"{APP_NAME}:metrics-endpoint", f"{PROMETHEUS_NAME}:metrics-endpoint")
        juju.integrate(f"{APP_NAME}:grafana-dashboard", f"{GRAFANA_NAME}:grafana-dashboard")
        juju.integrate(f"{APP_NAME}:logging", f"{LOKI_NAME}:logging")

    # COS charms patch their own pod resources on startup, which restarts the pod and can
    # fail a hook transiently; Juju retries it, so only require that they end up active.
    with fast_forward(juju):
        juju.wait(
            lambda status: jubilant.all_active(status, APP_NAME, *COS_APPS),
            timeout=1200,
            successes=30,
        )


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("observed_stack")
class TestObservability:
    """Integration tests for the worker's metrics, alerts, dashboard and logs."""

    def test_metrics_are_scraped(self, juju: jubilant.Juju):
        """Prometheus scrapes the worker, which reports itself up with active pollers."""

        def _worker_up_with_pollers():
            """Check the worker is up and has active pollers.

            Returns:
                Whether every worker unit is up and the worker has at least one poller.
            """
            up = _prometheus_query(juju, f'up{{juju_application="{APP_NAME}"}}')
            pollers = _prometheus_query(juju, f'sum(temporal_num_pollers{{juju_application="{APP_NAME}"}})')
            logger.info("up=%s pollers=%s", up, pollers)
            return (
                up and all(sample["value"][1] == "1" for sample in up) and pollers and float(pollers[0]["value"][1]) > 0
            )

        _poll_until(_worker_up_with_pollers, "Prometheus never saw the worker up with active pollers")

    def test_alert_rules_are_loaded(self, juju: jubilant.Juju):
        """The alert rules the charm ships are loaded into Prometheus and are not firing."""

        def _rules_loaded():
            """Check the charm's alert rules are loaded.

            Returns:
                Whether every expected alert rule is loaded.
            """
            states = _alert_rule_states(juju)
            logger.info("Alert rule states: %s", states)
            return set(ALERT_RULES) <= set(states)

        _poll_until(_rules_loaded, f"Prometheus never loaded the alert rules {ALERT_RULES}")

        states = _alert_rule_states(juju)
        firing = [name for name in ALERT_RULES if states[name] == "firing"]
        assert not firing, f"alert rules firing on a healthy worker: {firing}"

    def test_grafana_dashboard_is_published(self, juju: jubilant.Juju):
        """The dashboard the charm ships, including the worker health panels, shows up in Grafana."""
        url = get_unit_url(juju, GRAFANA_NAME, 0, GRAFANA_PORT)
        task = juju.run(f"{GRAFANA_NAME}/0", "get-admin-password")
        password = task.results["admin-password"]
        auth = ("admin", password)

        def _dashboard_published():
            """Check the dashboard and its worker health panels are published.

            Returns:
                Whether the dashboard is published.
            """
            dashboards = _get_json(f"{url}/api/search", {"type": "dash-db"}, auth)
            matches = [entry for entry in dashboards if entry.get("title") == DASHBOARD_TITLE]
            if not matches:
                return False
            dashboard = _get_json(f"{url}/api/dashboards/uid/{matches[0]['uid']}", auth=auth)
            titles = {panel.get("title") for panel in dashboard["dashboard"]["panels"]}
            missing = set(DASHBOARD_PANELS) - titles
            assert not missing, f"dashboard is missing panels: {missing}"
            return True

        _poll_until(_dashboard_published, f"Grafana never loaded the '{DASHBOARD_TITLE}' dashboard")

    def test_logs_are_forwarded(self, juju: jubilant.Juju):
        """Loki receives log lines from the temporal-worker service."""
        # The sample worker logs nothing while idle, and Pebble only forwards lines written
        # after the logging relation is set up, so run a workflow to make it log.
        run_sample_workflow(juju)

        url = get_unit_url(juju, LOKI_NAME, 0, LOKI_PORT)
        query = f'{{juju_application="{APP_NAME}", pebble_service="temporal-worker"}} |= "Running workflow"'

        def _logs_received():
            """Check Loki has worker log lines.

            Returns:
                Whether Loki returned any matching log streams.
            """
            now = time.time_ns()
            response = _get_json(
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

        _poll_until(_logs_received, f"Loki never received logs matching {query}")

    def test_unable_to_poll_alert_fires(self, juju: jubilant.Juju):
        """Taking the Temporal server away fires TemporalWorkerUnableToPoll while the worker stays up.

        This must run last in the module as it temporarily removes the Temporal server.
        """
        juju.cli("scale-application", APP_NAME_SERVER, "0")
        try:

            def _unable_to_poll_firing():
                """Check whether TemporalWorkerUnableToPoll is firing.

                Returns:
                    Whether the alert is firing.
                """
                states = _alert_rule_states(juju)
                logger.info("Alert rule states: %s", states)
                return states.get("TemporalWorkerUnableToPoll") == "firing"

            # The rule needs 3m without a successful poll plus 2m pending.
            _poll_until(_unable_to_poll_firing, "TemporalWorkerUnableToPoll never fired", timeout=900)

            states = _alert_rule_states(juju)
            assert states["TemporalWorkerDown"] != "firing", "worker process should still be up"
        finally:
            juju.cli("scale-application", APP_NAME_SERVER, "1")
            juju.wait(
                lambda status: jubilant.all_active(status, APP_NAME_SERVER, APP_NAME),
                timeout=900,
            )
