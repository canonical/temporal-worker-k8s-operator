#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm definition and helpers."""

import logging
import os
import secrets

from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.vault_k8s.v0 import vault_kv
from dotenv import dotenv_values
from ops import main, pebble
from ops.charm import CharmBase
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    WaitingStatus,
)

from literals import (
    LOG_FILE,
    PROMETHEUS_PORT,
    REQUIRED_CANDID_CONFIG,
    REQUIRED_CHARM_CONFIG,
    REQUIRED_OIDC_CONFIG,
    SUPPORTED_AUTH_PROVIDERS,
    VALID_LOG_LEVELS,
)
from log import log_event_handler
from relations.vault import VAULT_CERT_PATH, VAULT_NONCE_SECRET_LABEL, VaultRelation
from state import State

logger = logging.getLogger(__name__)


class TemporalWorkerK8SOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        """Construct.

        Args:
            args: Ignore.
        """
        super().__init__(*args)
        self._state = State(self.app, lambda: self.model.get_relation("peer"))
        self.name = "temporal-worker"

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.temporal_worker_pebble_ready, self._on_temporal_worker_pebble_ready)
        self.framework.observe(self.on.restart_action, self._on_restart)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.install, self._on_install)

        # Vault
        self.vault = vault_kv.VaultKvRequires(
            self,
            relation_name="vault",
            mount_suffix=self.app.name,
        )
        self.vault_relation = VaultRelation(self)

        # Prometheus
        self._prometheus_scraping = MetricsEndpointProvider(
            self,
            relation_name="metrics-endpoint",
            jobs=[{"static_configs": [{"targets": [f"*:{PROMETHEUS_PORT}"]}]}],
            refresh_event=self.on.config_changed,
        )

        # Loki
        self._log_proxy = LogProxyConsumer(self, log_files=[LOG_FILE], relation_name="log-proxy")

        # Grafana
        self._grafana_dashboards = GrafanaDashboardProvider(self, relation_name="grafana-dashboard")

    @log_event_handler(logger)
    def _on_install(self, event):
        """Handle on install event.

        Args:
            event: The event triggered on install.
        """
        self.unit.add_secret(
            {"nonce": secrets.token_hex(16)},
            label=VAULT_NONCE_SECRET_LABEL,
            description="Nonce for vault-kv relation",
        )

    @log_event_handler(logger)
    def _on_temporal_worker_pebble_ready(self, event):
        """Define and start temporal using the Pebble API.

        Args:
            event: The event triggered when the relation changed.
        """
        if not self._state.is_ready():
            event.defer()
            return

        self._update(event)

    @log_event_handler(logger)
    def _on_restart(self, event):
        """Restart Temporal worker action handler.

        Args:
            event:The event triggered by the restart action
        """
        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.defer()
            return

        self.unit.status = MaintenanceStatus("restarting worker")
        container.restart(self.name)

        event.set_results({"result": "worker successfully restarted"})

    @log_event_handler(logger)
    def _on_config_changed(self, event):
        """Handle configuration changes.

        Args:
            event: The event triggered when the relation changed.
        """
        self.unit.status = WaitingStatus("configuring temporal worker")
        self._update(event)

    @log_event_handler(logger)
    def _on_update_status(self, event):
        """Handle `update-status` events.

        Args:
            event: The `update-status` event triggered at intervals.
        """
        try:
            self._validate(event)
        except ValueError:
            return

        container = self.unit.get_container(self.name)
        valid_pebble_plan = self._validate_pebble_plan(container)
        if not valid_pebble_plan:
            self._update(event)
            return

        self.unit.status = ActiveStatus(
            f"worker listening to namespace {self.config['namespace']!r} on queue {self.config['queue']!r}"
        )

    def _validate_pebble_plan(self, container):
        """Validate Temporal worker pebble plan.

        Args:
            container: application container

        Returns:
            bool of pebble plan validity
        """
        try:
            plan = container.get_plan().to_dict()
            return bool(plan and plan["services"].get(self.name, {}))
        except pebble.ConnectionError:
            return False

    def _process_env_file(self, event):
        """Process env file attached by user.

        This method extracts the env file provided by the user and stores the data in the
        charm's data bucket.

        Args:
            event: The event triggered when the relation changed.

        Raises:
            ValueError: if env file contains variable starting with reserved prefix.
        """
        if not self._state.is_ready():
            event.defer()
            return

        if self.unit.is_leader():
            self._state.env = None

        try:
            resource_path = self.model.resources.fetch("env-file")
            env = dotenv_values(resource_path)

            for key, _ in env.items():
                if key.startswith("TWC_"):
                    raise ValueError("Invalid state: 'TWC_' env variable prefix is reserved")

            if self.unit.is_leader():
                self._state.env = env
        except ModelError as err:
            logger.error(err)

    def _check_required_config(self, config_list):
        """Check if required config has been set by user.

        Args:
            config_list: list of required config parameters.

        Raises:
            ValueError: if any of the required config is not set.
        """
        for param in config_list:
            if self.config[param].strip() == "":
                raise ValueError(f"Invalid config: {param} value missing")

    def _validate(self, event):  # noqa: C901
        """Validate that configuration and relations are valid and ready.

        Args:
            event: The event triggered when the relation changed.

        Raises:
            ValueError: in case of invalid configuration.
        """
        log_level = self.model.config["log-level"].lower()
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"config: invalid log level {log_level!r}")

        if not self._state.is_ready():
            raise ValueError("peer relation not ready")

        self._process_env_file(event)

        self._check_required_config(REQUIRED_CHARM_CONFIG)

        if self.config["auth-provider"]:
            if not self.config["auth-provider"] in SUPPORTED_AUTH_PROVIDERS:
                raise ValueError("Invalid config: auth-provider not supported")

            if self.config["auth-provider"] == "candid":
                self._check_required_config(REQUIRED_CANDID_CONFIG)
            elif self.config["auth-provider"] == "google":
                self._check_required_config(REQUIRED_OIDC_CONFIG)

        sample_rate = self.config["sentry-sample-rate"]
        if self.config["sentry-dsn"] and (sample_rate < 0 or sample_rate > 1):
            raise ValueError("Invalid config: sentry-sample-rate must be between 0 and 1")

    def _update(self, event):  # noqa: C901
        """Update the Temporal worker configuration and replan its execution.

        Args:
            event: The event triggered when the relation changed.
        """
        try:
            self._validate(event)
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.defer()
            self.unit.status = WaitingStatus("waiting for pebble api")
            return

        logger.info("Configuring Temporal worker")

        context = {}
        if self._state.env:
            context.update(self._state.env)

        proxy_vars = {
            "HTTP_PROXY": "JUJU_CHARM_HTTP_PROXY",
            "HTTPS_PROXY": "JUJU_CHARM_HTTPS_PROXY",
            "NO_PROXY": "JUJU_CHARM_NO_PROXY",
        }

        for key, env_var in proxy_vars.items():
            value = os.environ.get(env_var)
            if value:
                context.update({key: value})

        context.update({convert_env_var(key): value for key, value in self.config.items()})
        context.update({"TWC_PROMETHEUS_PORT": PROMETHEUS_PORT})

        try:
            vault_config = self.vault_relation._get_vault_config()
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        if vault_config:
            context.update(vault_config)
            container.push(VAULT_CERT_PATH, vault_config.get("TWC_VAULT_CACERT_BYTES"), make_dirs=True)

        # update vault relation if exists
        binding = self.model.get_binding("vault")
        if binding is not None:
            try:
                egress_subnet = str(binding.network.interfaces[0].subnet)
                self.vault.request_credentials(event.relation, egress_subnet, self.vault_relation.get_vault_nonce())
            except Exception as e:
                logger.warning(f"failed to update vault relation - {repr(e)}")

        pebble_layer = {
            "summary": "temporal worker layer",
            "services": {
                self.name: {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": context,
                }
            },
        }

        container.add_layer(self.name, pebble_layer, combine=True)
        container.replan()

        self.unit.status = MaintenanceStatus("replanning application")


def convert_env_var(config_var, prefix="TWC_"):
    """Convert config parameter to environment variable with prefix.

    Args:
        config_var: Configuration parameter to convert.
        prefix: A prefix to be added to the converted variable name.

    Returns:
        Converted environment variable.
    """
    converted_env_var = config_var.upper().replace("-", "_")
    return prefix + converted_env_var


if __name__ == "__main__":  # pragma: nocover
    main.main(TemporalWorkerK8SOperatorCharm)
