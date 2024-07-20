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
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.vault_k8s.v0 import vault_kv
from ops import main, pebble
from ops.charm import CharmBase
from ops.jujuversion import JujuVersion
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    SecretNotFoundError,
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
from vault_client import VaultClient

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
        self.framework.observe(self.on.add_vault_secret_action, self._on_add_vault_secret)

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
            event.fail("Failed to connect to the container")
            return

        self.unit.status = MaintenanceStatus("restarting worker")
        container.restart(self.name)

        event.set_results({"result": "worker successfully restarted"})

    @log_event_handler(logger)
    def _on_add_vault_secret(self, event):
        """Add Vault secret action handler.

        Args:
            event:The event triggered by the restart action
        """
        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.fail("Failed to connect to the container")
            return

        vault_config = self.vault_relation.get_vault_config()
        if not vault_config:
            event.fail("No Vault relation found")

        path, key, value = (event.params.get(param) for param in ["path", "key", "value"])
        if not all([path, key, value]):
            event.fail("`path`, `key` and `value` are required parameters")

        try:
            vault_client = VaultClient(
                address=vault_config["address"],
                cert_path=vault_config["cert_path"],
                role_id=vault_config["role_id"],
                role_secret_id=vault_config["role_secret_id"],
                mount_point=vault_config["mount_path"],
            )

            vault_client.write_secret(path=path, data={key: value})
        except Exception as e:
            event.fail(e)
            return

        event.set_results({"result": "secret successfully created"})

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
        except SecretNotFoundError:
            self.unit.status = BlockedStatus("juju secrets not found yet")
            return
        except ModelError:
            self.unit.status = BlockedStatus("access to juju secrets not granted to charm")
            return
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return
        # except ValueError:
        # return

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

    def create_env(self, parsed_secrets_data):
        """Create an environment dictionary with secrets from the parsed secrets data.

        Args:
            parsed_secrets_data (dict): The parsed secrets data, expected to have 'env', 'juju', and 'vault' sections.

        Returns:
            dict: A dictionary containing environment variables.

        Raises:
            ValueError: If the Juju version does not support secrets but 'juju' secrets are present, or
                            if there is no 'vault' relation but 'vault' secrets are present.
                        If there is an error parsing Juju secrets or reading Vault secrets.
        """
        charm_env = {}
        if parsed_secrets_data.get("juju") and not JujuVersion.from_environ().has_secrets:
            raise ValueError("Juju version does not support Juju user secrets")

        if parsed_secrets_data.get("vault") and not self.model.relations["vault"]:
            raise ValueError("No vault relation found to fetch secrets from")

        env_variables = parsed_secrets_data.get("env")
        for key, value in env_variables.items():
            charm_env.update({key: value})

        juju_variables = parsed_secrets_data.get("juju")
        for juju_secret in juju_variables:
            try:
                secret_id = juju_secret.get("secret-id")
                secret_name = juju_secret.get("secret-name")
                key = juju_secret.get("key")

                secret = None
                if secret_id:
                    secret = self.model.get_secret(id=secret_id)
                else:
                    secret = self.model.get_secret(label=secret_name)

                secret_content = secret.get_content(refresh=True)
                charm_env.update({key: secret_content[key]})
            # except SecretNotFoundError:
            #     raise SecretNotFoundError
            # except ModelError:
            #     raise ModelError
            except KeyError as e:
                logger.error(f"Error parsing secrets env: {e}")
                raise ValueError(f"Error parsing secrets env: {e}") from e

        vault_variables = parsed_secrets_data.get("vault")
        if vault_variables and self.model.relations["vault"]:
            vault_config = self.vault_relation.get_vault_config()
            vault_client = VaultClient(
                address=vault_config["vault_address"],
                cert_path=vault_config["vault_cert_path"],
                role_id=vault_config["vault_role_id"],
                role_secret_id=vault_config["vault_role_secret_id"],
                mount_point=vault_config["vault_mount"],
            )
            
            for item in vault_variables:
                key = item.get("key")
                secret = vault_client.read_secret(item.get("path"), key)
                charm_env.update({key: secret})

        return charm_env

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

        secrets_config = self.config.get("secrets")
        if secrets_config:
            try:
                yaml.safe_load(secrets_config)
            except (yaml.parser.ParserError, yaml.scanner.ScannerError) as e:
                raise ValueError(f"Incorrectly formatted `secrets` config: {e}") from e

        # try:
        secrets_config = self.config.get("secrets")
        if secrets_config:
            parsed_secrets_data = parse_secrets(secrets_config)
            self.create_env(parsed_secrets_data)
        # except SecretNotFoundError:
        #     raise SecretNotFoundError
        # except ModelError:
        #     raise ModelError
        # except ValueError as err:
        #     self.unit.status = BlockedStatus(str(err))
        #     return

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
        secrets_config = self.config.get("secrets")

        try:
            self._validate(event)
            if secrets_config:
                parsed_secrets_data = parse_secrets(secrets_config)
                charm_config_env = self.create_env(parsed_secrets_data)
                context.update(charm_config_env)
        except SecretNotFoundError:
            self.unit.status = WaitingStatus("juju secrets not found yet")
            return
        except ModelError:
            self.unit.status = WaitingStatus("access to juju secrets not granted to charm")
            return
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

        context.update({convert_env_var(key): value for key, value in self.config.items() if key not in ["secrets"]})
        context.update({"TWC_PROMETHEUS_PORT": PROMETHEUS_PORT})
        try:
            vault_config = self.vault_relation.get_vault_config()
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        if vault_config:
            context.update({convert_env_var(key): value for key, value in vault_config.items()})
            container.push(VAULT_CERT_PATH, vault_config.get("vault_ca_certificate_bytes"), make_dirs=True)

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


def parse_secrets(yaml_string):
    """Parse a YAML string containing secrets and validates its structure.

    The YAML string should contain a 'secrets' key with nested 'env', 'juju', and 'vault' keys.
    Each nested key should follow a specific structure:
        - 'env': A list of single-key dictionaries.
        - 'juju': A list of dictionaries with 'secret-id' or 'secret-name', and 'key' keys.
        - 'vault': A list of dictionaries with 'path' and 'key' keys.

    Args:
        yaml_string (str): The YAML string to be parsed.

    Returns:
        dict: A dictionary with the parsed and validated secrets.
              The structure of the returned dictionary is:
              {
                  "env": {str: str},
                  "juju": [{"secret-id" or "secret-name": str, "key": str}],
                  "vault": [{"path": str, "key": str}]
              }

    Raises:
        ValueError: If the YAML string does not conform to the expected structure.
    """
    data = yaml.safe_load(yaml_string)
    logger.info(f"DATAAA: {data}")

    # Validate the main structure
    if not isinstance(data, dict) or "secrets" not in data:
        raise ValueError("Invalid secrets structure: 'secrets' key not found")

    secrets_key = data["secrets"]
    if not isinstance(secrets_key, dict):
        raise ValueError("Invalid secrets structure: 'secrets' should be a dictionary")

    # Validate env key
    env = secrets_key.get("env", [])
    if not isinstance(env, list) or not all(isinstance(item, dict) and len(item) == 1 for item in env):
        raise ValueError("Invalid secrets structure: 'env' should be a list of single-key dictionaries")

    # Validate juju key
    juju = secrets_key.get("juju", [])
    if not isinstance(juju, list) or not all(
        isinstance(item, dict) and "key" in item and (("secret-id" in item or "secret-name" in item) and len(item) == 2)
        for item in juju
    ):
        raise ValueError(
            "Invalid secrets structure: 'juju' should be a list of dictionaries with 'key' and either 'secret-id' or 'secret-name'"
        )
    # Ensure only one of 'secret-id' or 'secret-name' is present
    for item in juju:
        if "secret-id" in item and "secret-name" in item:
            raise ValueError(
                "Invalid secrets structure: 'juju' dictionaries should have either 'secret-id' or 'secret-name', but not both"
            )

    # Validate vault key
    vault = secrets_key.get("vault", [])
    if not isinstance(vault, list) or not all(
        isinstance(item, dict) and "path" in item and "key" in item and len(item) == 2 for item in vault
    ):
        raise ValueError("Invalid secrets structure: 'vault' should be a list of dictionaries with 'path' and 'key'")

    env = secrets_key.get("env", [])
    juju = secrets_key.get("juju", [])
    vault = secrets_key.get("vault", [])

    parsed_data = {
        "env": {list(item.keys())[0]: list(item.values())[0] for item in env},
        "juju": [
            {"secret-id": item.get("secret-id"), "secret-name": item.get("secret-name"), "key": item.get("key")}
            for item in juju
        ],
        "vault": [{"path": item.get("path"), "key": item.get("key")} for item in vault],
    }

    return parsed_data


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
