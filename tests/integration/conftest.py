# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for jubilant tests."""

import logging
import pathlib

import jubilant
import pytest
from helpers import (
    APP_NAME,
    APP_NAME_SERVER,
    add_juju_secret,
    fast_forward,
    get_worker_config,
    setup_temporal_ecosystem,
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module", autouse=True)
def configure_juju(juju: jubilant.Juju):
    """Set wait timeout to match python-libjuju's 10-minute default.

    Args:
        juju: pytest-jubilant Juju client bound to the test model.
    """
    juju.wait_timeout = 10 * 60


@pytest.fixture(scope="module", name="temporal_worker_image")
def temporal_worker_image_fixture(request: pytest.FixtureRequest) -> str:
    """Fetch the OCI image for Temporal Worker charm."""
    temporal_worker_image = request.config.getoption("--temporal-worker-image")
    assert (
        temporal_worker_image
    ), "--temporal-worker-image argument is required which should contain the name of the OCI image."
    return temporal_worker_image


@pytest.fixture(scope="module", name="charm")
def charm_fixture(request: pytest.FixtureRequest) -> pathlib.Path:
    """Fetch the path to charm.

    Uses ``--charm-file`` when provided. Otherwise requires exactly one ``*.charm``
    file in the project root.
    """
    if charms := request.config.getoption("--charm-file"):
        assert len(charms) == 1, f"Expected one charm file, found {charms}"
        return pathlib.Path(charms[0]).resolve()

    packed = sorted(pathlib.Path(".").glob("*.charm"))
    assert packed, "*.charm not found in project root; pack the charm first (charmcraft pack)"
    assert len(packed) == 1, f"more than one *.charm in project root, unsure which to use: {packed}"
    return packed[0].resolve()


@pytest.fixture(name="deploy", scope="module")
def deploy(juju: jubilant.Juju, charm: pathlib.Path, temporal_worker_image: str):
    """Verify the app is up and running."""
    juju.model_config({"update-status-hook-interval": "1m"})

    resources = {
        "temporal-worker-image": temporal_worker_image,
    }

    secret_id = add_juju_secret(juju)
    worker_config = get_worker_config(secret_id)

    juju.deploy(charm, app=APP_NAME, resources=resources, config=worker_config)
    juju.grant_secret("worker-secrets", APP_NAME)

    setup_temporal_ecosystem(juju)
    juju.config(APP_NAME, {"host": f"{APP_NAME_SERVER}:7233"})

    with fast_forward(juju):
        juju.wait(lambda status: jubilant.all_active(status, APP_NAME), timeout=600)

    assert juju.status().apps[APP_NAME].units[f"{APP_NAME}/0"].workload_status.current == "active"
