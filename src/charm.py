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
from charms.temporal_k8s.v0.temporal_host_info import TemporalHostInfoRequirer
from charms.temporal_worker_k8s.v0.temporal_worker_info import (
    TemporalWorkerInfoProvider,
)
from charms.vault_k8s.v0 import vault_kv
from ops import (
    ConfigChangedEvent,
    InstallEvent,
    PebbleCheckFailedEvent,
    PebbleReadyEvent,
    RelationChangedEvent,
    RelationEvent,
    RelationJoinedEvent,
    main,
    pebble,
)
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
from vault.actions import VaultActions

logger = logging.getLogger(__name__)


class ExitWithStatusError(Exception):
    """Exception raised to exit the reconciliation with a specific unit status.

    Attrs:
        msg: The status message.
        status_type: The ops status class to report.
        status: The Juju unit status represented by this exception.
    """

    def __init__(self, msg: str, status_type):
        """Construct.

        Args:
            msg: The status message.
            status_type: The ops status class to report.
        """
        super().__init__(str(msg))
        self.msg = str(msg)
        self.status_type = status_type

    @property
    def status(self):
        """Return the Juju unit status represented by this exception."""
        return self.status_type(self.msg)


class ExitWithoutStatusChange(Exception):  # noqa: N818
    """Exception raised to exit the reconciliation leaving the unit status as it is."""


class TemporalWorkerK8SOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        """Construct.

        Args:
            args: Ignore.
        """
        super().__init__(*args)
        self._service_name = "temporal-worker"

        self.database = DatabaseRequires(
            self, relation_name="database", database_name=self.model.config.get("db-name", None)
        )
        self.postgresql = Postgresql(self)

        self.framework.observe(self.on.restart_action, self._on_restart)

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
            # pebble-ready fires when the pod restarts with a new IP; config-changed does not.
            refresh_event=[self.on.config_changed, self.on.temporal_worker_pebble_ready],
        )

        # Loki
        self._log_forwarder = LogForwarder(self, relation_name="logging")

        # Grafana
        self._grafana_dashboards = GrafanaDashboardProvider(self, relation_name="grafana-dashboard")

        self.worker_info = TemporalWorkerInfoProvider(self)
        self.host_info = TemporalHostInfoRequirer(self)

        # Every event the charm reacts to converges on the single reconciler. The vault and host-info library events
        # are only emitted once the relation data is usable, which is why they are observed instead of the relation
        # events.
        for event in [
            self.on.install,
            self.on.upgrade_charm,
            self.on.config_changed,
            self.on.update_status,
            self.on.temporal_worker_pebble_ready,
            self.on.temporal_worker_pebble_check_failed,
            self.on.temporal_worker_pebble_check_recovered,
            self.on.secret_changed,
            self.on.peer_relation_changed,
            self.database.on.database_created,
            self.database.on.endpoints_changed,
            self.on.database_relation_broken,
            self.on.vault_relation_joined,
            self.vault.on.ready,
            self.vault.on.gone_away,
            self.host_info.on.temporal_host_info_changed,
            self.host_info.on.temporal_host_info_unavailable,
        ]:
            self.framework.observe(event, self._reconcile)

    @property
    def _deprecated_host(self) -> str | None:
        """Return configured fallback Temporal address (host[:port]), if set."""
        raw = self.config.get("host")
        if raw is None:
            return None
        stripped = str(raw).strip()
        return stripped or None

    @log_event_handler(logger)
    def _reconcile(self, event):
        """Reconcile the charm towards the desired state; idempotent for every event.

        Args:
            event: The event that triggered the reconciliation.
        """
        try:
            self._handle_unit_event(event)
            self._ignore_event(event)

            if isinstance(event, ConfigChangedEvent) or self._is_vault_joined(event):
                self.vault_relation.update_vault_relation()
            self.postgresql.sync_legacy_peer_state(event)
            if self._is_vault_joined(event):
                raise ExitWithoutStatusChange()

            container = self.unit.get_container(self._service_name)
            self._check_container_can_connect(container)
            self._check_entrypoint(container)
            charm_config_env, auth_config = self._check_configuration()
            db_conn = self._check_database_connection()
            context = self._build_context(charm_config_env, auth_config, db_conn)
            self._apply_layer(container, context)
            self._check_failing_pebble_checks(container)
        except ExitWithoutStatusChange:
            return
        except ExitWithStatusError as e:
            self.unit.status = e.status
            return

        self._set_active_status()

    @staticmethod
    def _is_vault_joined(event) -> bool:
        """Report whether the event is a unit joining the vault relation."""
        return isinstance(event, RelationJoinedEvent) and event.relation.name == "vault"

    def _handle_unit_event(self, event):
        """Handle the events that only report on, or prepare, the unit and never reconfigure the workload.

        Args:
            event: The event being reconciled.

        Raises:
            ExitWithoutStatusChange: If the event is fully handled.
        """
        if isinstance(event, PebbleCheckFailedEvent):
            self._raise_pebble_check_failure(event.info.name)

        if isinstance(event, InstallEvent):
            self.unit.add_secret(
                {"nonce": secrets.token_hex(16)},
                label=VAULT_NONCE_SECRET_LABEL,
                description="Nonce for vault-kv relation",
            )
            raise ExitWithoutStatusChange()

    def _ignore_event(self, event):
        """Ignore the events there is nothing to reconcile for on this unit.

        Args:
            event: The event being reconciled.

        Raises:
            ExitWithoutStatusChange: If the event is ignored.
        """
        relation_name = event.relation.name if isinstance(event, RelationEvent) else None
        if isinstance(event, RelationChangedEvent) and relation_name == "peer" and self.unit.is_leader():
            # The leader is the one writing to the peer relation.
            raise ExitWithoutStatusChange()
        if not self._peer_relation_ready() and (isinstance(event, PebbleReadyEvent) or relation_name == "database"):
            raise ExitWithoutStatusChange()

    def _peer_relation_ready(self) -> bool:
        """Report whether the peer relation is available."""
        return bool(self.model.get_relation("peer"))

    def _check_container_can_connect(self, container):
        """Check that the workload container can be reached.

        Args:
            container: application container

        Raises:
            ExitWithStatusError: If the workload container cannot be reached.
        """
        if not container.can_connect():
            raise ExitWithStatusError("waiting for pebble api", WaitingStatus)

    def _check_entrypoint(self, container):
        """Check that the workload image has the expected entrypoint script.

        Args:
            container: application container

        Raises:
            ExitWithStatusError: If the entrypoint script does not exist.
        """
        if not container.exists("/app/scripts/start-worker.sh"):
            logger.error(
                "The workload container does not have the expected entrypoint script. Please refresh the charm with another valid image"
            )
            raise ExitWithStatusError("Please refresh the charm with a valid worker image", BlockedStatus)

    def _check_configuration(self) -> tuple[dict, dict]:
        """Validate the configuration and read the environment and the auth configuration.

        Returns:
            The environment configuration variables and the auth configuration variables.

        Raises:
            ExitWithStatusError: If the configuration is not valid.
        """
        charm_config_env = {}
        auth_config = {}
        try:
            self._validate()
            if self.config.get("environment"):
                charm_config_env = self.create_env()
            if self.config.get("auth-secret-id"):
                auth_config = self.get_auth_config_from_juju_secret()
        except ValueError as err:
            raise ExitWithStatusError(str(err), BlockedStatus) from err
        return charm_config_env, auth_config

    def _check_database_connection(self) -> dict | None:
        """Read the database connection info, if the charm is related to a database.

        Returns:
            The database connection info, or None if there is no database relation.

        Raises:
            ExitWithStatusError: If the database relation does not provide the connection info yet.
        """
        if not self.model.get_relation("database"):
            return None

        db_conn = self.postgresql.connection()
        if not db_conn:
            raise ExitWithStatusError("waiting for database credentials", WaitingStatus)
        return db_conn

    @log_event_handler(logger)
    def _on_restart(self, event):
        """Restart Temporal worker action handler.

        Args:
            event:The event triggered by the restart action
        """
        container = self.unit.get_container(self._service_name)
        if not container.can_connect():
            event.fail("Failed to connect to the container")
            return

        self.unit.status = MaintenanceStatus("restarting worker")
        container.restart(self._service_name)
        self._reconcile(event)

        if not isinstance(self.unit.status, ActiveStatus):
            event.fail(self.unit.status.message)
            return

        event.set_results({"result": "worker successfully restarted"})

    def _active_message(self) -> str:
        """Return the message of the Active status: the configured namespace and queue."""
        return f"worker listening to namespace {self.config['namespace']!r} on queue {self.config['queue']!r}"

    def _set_active_status(self):
        """Set Active status with the configured namespace and queue."""
        self.unit.status = ActiveStatus(self._active_message())

    def _has_failing_pebble_checks(self, container):
        """Check whether any pebble check of the container is currently failing.

        Args:
            container: application container

        Returns:
            bool, True if at least one pebble check is down
        """
        return any(info.status == pebble.CheckStatus.DOWN for info in container.get_checks().values())

    def _check_failing_pebble_checks(self, container):
        """Keep the unit blocked while any Pebble check is down.

        Args:
            container: Application container.
        """
        if not self._has_failing_pebble_checks(container):
            return

        checks = container.get_checks()
        if any(
            info.name == "eviction-loop-check" and info.status == pebble.CheckStatus.DOWN for info in checks.values()
        ):
            self._raise_pebble_check_failure("eviction-loop-check")

        self._raise_pebble_check_failure("start-worker-check")

    @staticmethod
    def _raise_pebble_check_failure(check_name):
        """Raise the blocked status for a failed Pebble check.

        Args:
            check_name: Name of the failed check.

        Raises:
            ExitWithStatusError: With the failed check's Blocked status.
        """
        if check_name == "eviction-loop-check":
            logger.error(
                "Temporal SDK workflow eviction loop detected: the worker has stuck slots "
                "and may not complete workflow tasks. "
                "Fix the workflow code before restarting the worker."
            )
            raise ExitWithStatusError("eviction loop detected - fix workflow code before restarting", BlockedStatus)
        raise ExitWithStatusError("temporal-worker service is not running; check logs for crash details", BlockedStatus)

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

    def _validate(self):  # noqa: C901
        """Validate that configuration and relations are valid and ready.

        Raises:
            ValueError: in case of invalid configuration.
        """
        log_level = self.model.config["log-level"].lower()
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"config: invalid log level {log_level!r}")

        if not self._peer_relation_ready():
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

    def _build_context(self, charm_config_env: dict, auth_config: dict, db_conn: dict | None) -> dict:  # noqa: C901
        """Build the environment of the Temporal worker.

        Args:
            charm_config_env: Variables coming from the `environment` config.
            auth_config: Variables coming from the auth Juju secret.
            db_conn: Connection info of the related database, if any.

        Returns:
            The environment of the Temporal worker service.

        Raises:
            ExitWithStatusError: If the worker cannot be configured to reach Temporal.
        """
        logger.info("Configuring Temporal worker")

        context: dict = {}
        proxy_vars = {
            "HTTP_PROXY": "JUJU_CHARM_HTTP_PROXY",
            "HTTPS_PROXY": "JUJU_CHARM_HTTPS_PROXY",
            "NO_PROXY": "JUJU_CHARM_NO_PROXY",
        }

        for key, env_var in proxy_vars.items():
            value = os.environ.get(env_var)
            if value:
                context.update({key: value})

        host = None
        host_from_relation = bool(self.host_info.host and self.host_info.port)
        if host_from_relation:
            host = f"{self.host_info.host}:{self.host_info.port}"
            if self._deprecated_host:
                logger.warning(
                    "The `host` config option is deprecated and will be removed in a future release; "
                    "prefer the `temporal-host-info` relation. Ignoring `host` while relation data is present."
                )
        elif self._deprecated_host:
            logger.warning(
                "The `host` config option is deprecated and will be removed in a future release; "
                "prefer the `temporal-host-info` relation."
            )
            host = self._deprecated_host
        else:
            raise ExitWithStatusError(
                "temporal-host-info relation not established; set deprecated `host` config as fallback",
                BlockedStatus,
            )

        context.update(
            {
                "TWC_HOST": host,
                "TEMPORAL_HOST": host,
            }
        )

        context.update(
            {
                convert_env_var(key, prefix="TWC_"): value
                for key, value in self.config.items()
                if key not in ["environment", "auth-secret-id", "host"]
            }
        )

        context.update(
            {
                convert_env_var(key, prefix="TEMPORAL_"): value
                for key, value in self.config.items()
                if key not in ["environment", "auth-secret-id", "host"]
            }
        )

        # Environment config (env/juju/vault) should override base charm config values.
        if charm_config_env:
            context.update(charm_config_env)

        # Auth configs coming from a juju secret take precedence over those coming from config.
        # Auth config options will be deprecated in favor of using juju user secrets.
        if auth_config:
            context.update(**auth_config)

        # temporal-host-info reports whether the frontend serves gRPC over TLS,
        # but the workload only dials TLS when it has a CA bundle, so without
        # one it would dial plaintext and fail with no hint at the cause. The
        # CA stays operator-supplied (`tls-root-cas` or `environment`) until
        # the workload gets a TLS switch of its own; see
        # canonical/temporal-worker-k8s-operator#121.
        if host_from_relation:
            tls_root_cas = context.get("TEMPORAL_TLS_ROOT_CAS") or context.get("TWC_TLS_ROOT_CAS")
            if self.host_info.tls and not tls_root_cas:
                raise ExitWithStatusError("Temporal frontend uses TLS: set tls-root-cas to its CA", BlockedStatus)
            if not self.host_info.tls and tls_root_cas:
                logger.warning(
                    "tls-root-cas is set but the Temporal frontend does not serve TLS: the worker dials "
                    "it over TLS and will fail to connect. Unset tls-root-cas, or enable frontend TLS."
                )

        context.update({"TWC_PROMETHEUS_PORT": PROMETHEUS_PORT, "TEMPORAL_PROMETHEUS_PORT": PROMETHEUS_PORT})

        if db_conn:
            context.update(
                {
                    "TEMPORAL_DB_HOST": db_conn.get("host"),
                    "TEMPORAL_DB_PORT": db_conn.get("port"),
                    "TEMPORAL_DB_PASSWORD": db_conn.get("password"),
                    "TEMPORAL_DB_USER": db_conn.get("user"),
                    "TEMPORAL_DB_TLS": db_conn.get("tls"),
                }
            )

        return context

    def _apply_layer(self, container, context):
        """Add the Pebble layer and replan when the plan changed or the worker is not running.

        Args:
            container: application container
            context: The environment of the Temporal worker service.

        Raises:
            ExitWithStatusError: If the worker cannot be started.
        """
        pebble_layer = {
            "summary": "temporal worker layer",
            "services": {
                self._service_name: {
                    "summary": "temporal worker",
                    "command": "/app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": context,
                }
            },
            "checks": {
                "start-worker-check": {
                    "override": "replace",
                    "threshold": 3,
                    "exec": {"command": "pgrep -f start-worker.sh"},
                },
                # NOTE: this eviction log only works for the Go and Python SDKs specifically
                "eviction-loop-check": {
                    "override": "replace",
                    "period": "5m",
                    "threshold": 1,
                    "exec": {
                        "command": f"bash -c '! pebble logs -n 50 {self._service_name} 2>/dev/null | grep -q \"continually retrying eviction\"'"
                    },
                },
            },
        }

        plan_before = container.get_plan().to_dict()
        container.add_layer(self._service_name, pebble_layer, combine=True)
        plan_changed = container.get_plan().to_dict() != plan_before

        # A previous replan may have failed to start the worker: retry it.
        if not plan_changed and self._worker_running(container):
            return

        try:
            container.replan()
        except pebble.ChangeError as e:
            logger.exception(f"Failed to replan pebble services: {e}")
            raise ExitWithStatusError(
                "Failed to start pebble services - please consult logs for further details", BlockedStatus
            ) from e

    def _worker_running(self, container) -> bool:
        """Check whether the worker service is running.

        Args:
            container: application container

        Returns:
            True if the worker service is running.
        """
        service = container.get_services(self._service_name).get(self._service_name)
        return service is not None and service.is_running()


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
