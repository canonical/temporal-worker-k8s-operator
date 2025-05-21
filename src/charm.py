#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm definition and helpers."""

import logging
import os
import secrets

import yaml
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.vault_k8s.v0 import vault_kv
from ops import main, pebble
from ops.charm import CharmBase
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

import environment_processors
from literals import (
    AUTH_SECRET_PARAMETERS,
    PROMETHEUS_PORT,
    REQUIRED_CANDID_CONFIG,
    REQUIRED_CHARM_CONFIG,
    REQUIRED_OIDC_CONFIG,
    SUPPORTED_AUTH_PROVIDERS,
    VALID_LOG_LEVELS,
)
from log import log_event_handler
from relations.postgresql import Postgresql
from relations.vault import VAULT_NONCE_SECRET_LABEL, VaultRelation
from state import State
from vault.actions import VaultActions

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

        self.database = DatabaseRequires(
            self, relation_name="database", database_name=self.model.config.get("db-name", None)
        )
        self.postgresql = Postgresql(self)

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.temporal_worker_pebble_ready, self._on_temporal_worker_pebble_ready)
        self.framework.observe(self.on.restart_action, self._on_restart)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.secret_changed, self._on_secret_changed)

        # Vault
        self.vault = vault_kv.VaultKvRequires(
            self,
            relation_name="vault",
            mount_suffix=self.app.name,
        )
        self.vault_relation = VaultRelation(self)
        self.vault_actions = VaultActions(self)

        # Prometheus
        self._prometheus_scraping = MetricsEndpointProvider(
            self,
            relation_name="metrics-endpoint",
            jobs=[{"static_configs": [{"targets": [f"*:{PROMETHEUS_PORT}"]}]}],
            refresh_event=self.on.config_changed,
        )

        if self.config.get("workload-prometheus-port"):
            workload_prometheus_port = self.config.get("workload-prometheus-port")
            self._app_prometheus_scraping = MetricsEndpointProvider(
                self,
                relation_name="workload-metrics-endpoint",
                jobs=[{"static_configs": [{"targets": [f"*:{workload_prometheus_port}"]}]}],
                refresh_event=self.on.config_changed,
            )

        # Loki
        self._log_forwarder = LogForwarder(self, relation_name="logging")

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
            event.fail("Failed to connect to the container")
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
    def _on_secret_changed(self, event):
        """Handle secret changed hook.

        Args:
            event: The event triggered when the secret changed.
        """
        self._update(event)

    @log_event_handler(logger)
    def _on_update_status(self, event):
        """Handle `update-status` events.

        Args:
            event: The `update-status` event triggered at intervals.
        """
        should_update = self.postgresql.update_db_relation_data_in_state(event)
        if should_update:
            logger.info("updating charm to reflect new database connection info")
            self._update(event)
            return

        try:
            self._validate(event)
            environment_config = self.config.get("environment")
            if environment_config:
                self.create_env()
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
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

    def get_auth_config_from_juju_secret(self) -> dict:
        """Get auth config from Juju secret.

        Returns:
            dict: A dictionary containing the auth configuration.

        Raises:
            ValueError: if any of the required config is not set.
        """
        auth_config = {}
        secret = self.model.get_secret(id=self.config.get("auth-secret-id"))
        secret_content = secret.get_content(refresh=True)

        if not secret_content["auth-provider"]:
            raise ValueError("Invalid config: auth-provider value missing from auth-secret")

        if secret_content["auth-provider"] == "candid":
            self._check_required_config(secret_content, REQUIRED_CANDID_CONFIG)
        elif secret_content["auth-provider"] == "google":
            self._check_required_config(secret_content, REQUIRED_OIDC_CONFIG)

        auth_config.update(
            {
                convert_env_var(key, prefix="TWC_"): value
                for key, value in secret_content.items()
                if key in AUTH_SECRET_PARAMETERS
            }
        )

        auth_config.update(
            {
                convert_env_var(key, prefix="TEMPORAL_"): value
                for key, value in secret_content.items()
                if key in AUTH_SECRET_PARAMETERS
            }
        )

        return auth_config

    def create_env(self) -> dict:
        """Create an environment dictionary with secrets from the parsed secrets data.

        Returns:
            dict: A dictionary containing environment variables.
        """
        self.vault_relation.update_vault_relation()

        environment_config = self.config.get("environment")
        parsed_environment_data = environment_processors.parse_environment(environment_config)

        env_variables = environment_processors.process_env_variables(parsed_environment_data)
        juju_variables = environment_processors.process_juju_variables(self, parsed_environment_data)
        vault_variables = environment_processors.process_vault_variables(self, parsed_environment_data)

        charm_env = {**env_variables, **juju_variables, **vault_variables}
        return charm_env

    def _check_required_config(self, config_object, config_list):
        """Check if required config has been set by user.

        Args:
            config_object: configuration object to check.
            config_list: list of required config parameters.

        Raises:
            ValueError: if any of the required config is not set.
        """
        for param in config_list:
            if not config_object.get(param):
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

        self._check_required_config(self.config, REQUIRED_CHARM_CONFIG)

        if self.config["auth-provider"] and not self.config.get("auth-secret-id"):
            if not self.config["auth-provider"] in SUPPORTED_AUTH_PROVIDERS:
                raise ValueError("Invalid config: auth-provider not supported")

            if self.config["auth-provider"] == "candid":
                self._check_required_config(self.config, REQUIRED_CANDID_CONFIG)
            elif self.config["auth-provider"] == "google":
                self._check_required_config(self.config, REQUIRED_OIDC_CONFIG)

        sample_rate = self.config["sentry-sample-rate"]
        if self.config["sentry-dsn"] and (sample_rate < 0 or sample_rate > 1):
            raise ValueError("Invalid config: sentry-sample-rate must be between 0 and 1")

        environment_config = self.config.get("environment")
        if environment_config:
            try:
                yaml.safe_load(environment_config)
            except (yaml.parser.ParserError, yaml.scanner.ScannerError) as e:
                raise ValueError(f"Incorrectly formatted `environment` config: {e}") from e

        if self.model.get_relation("database") and not self.config.get("db-name"):
            raise ValueError("Invalid config: db name value missing")

    def _update(self, event):  # noqa: C901
        """Update the Temporal worker configuration and replan its execution.

        Args:
            event: The event triggered when the relation changed.
        """
        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.defer()
            self.unit.status = WaitingStatus("waiting for pebble api")
            return

        context = {}
        auth_config = {}
        try:
            self._validate(event)
            if self.config.get("environment"):
                charm_config_env = self.create_env()
                context.update(charm_config_env)
            if self.config.get("auth-secret-id"):
                auth_config = self.get_auth_config_from_juju_secret()
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        logger.info("Configuring Temporal worker")

        proxy_vars = {
            "HTTP_PROXY": "JUJU_CHARM_HTTP_PROXY",
            "HTTPS_PROXY": "JUJU_CHARM_HTTPS_PROXY",
            "NO_PROXY": "JUJU_CHARM_NO_PROXY",
        }

        for key, env_var in proxy_vars.items():
            value = os.environ.get(env_var)
            if value:
                context.update({key: value})

        context.update(
            {
                convert_env_var(key, prefix="TWC_"): value
                for key, value in self.config.items()
                if key not in ["environment", "auth-secret-id"]
            }
        )

        context.update(
            {
                convert_env_var(key, prefix="TEMPORAL_"): value
                for key, value in self.config.items()
                if key not in ["environment", "auth-secret-id"]
            }
        )

        # Auth configs coming from a juju secret take precedence over those coming from config.
        # Auth config options will be deprecated in favor of using juju user secrets.
        if auth_config:
            context.update(**auth_config)

        context.update({"TWC_PROMETHEUS_PORT": PROMETHEUS_PORT, "TEMPORAL_PROMETHEUS_PORT": PROMETHEUS_PORT})

        if self.model.get_relation("database"):
            context.update(
                {
                    "TEMPORAL_DB_HOST": self._state.database_connection.get("host"),
                    "TEMPORAL_DB_PORT": self._state.database_connection.get("port"),
                    "TEMPORAL_DB_PASSWORD": self._state.database_connection.get("password"),
                    "TEMPORAL_DB_USER": self._state.database_connection.get("user"),
                    "TEMPORAL_DB_TLS": self._state.database_connection.get("tls"),
                }
            )

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
