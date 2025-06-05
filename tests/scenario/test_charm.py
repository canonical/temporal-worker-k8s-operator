# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import dataclasses
import logging
import textwrap
import unittest.mock

import ops
import ops.testing
import pytest

logger = logging.getLogger(__name__)

CONFIG = {
    "log-level": "debug",
    "host": "test-host",
    "namespace": "test-namespace",
    "queue": "test-queue",
    "sentry-dsn": "",
    "sentry-release": "",
    "sentry-environment": "",
    "encryption-key": "",
    "auth-provider": "candid",
    "tls-root-cas": "",
    "candid-url": "test-url",
    "candid-username": "test-username",
    "candid-public-key": "test-public-key",
    "candid-private-key": "test-private-key",
    "oidc-auth-type": "",
    "oidc-project-id": "",
    "oidc-private-key-id": "",
    "oidc-private-key": "",
    "oidc-client-email": "",
    "oidc-client-id": "",
    "oidc-auth-uri": "",
    "oidc-token-uri": "",
    "oidc-auth-cert-url": "",
    "oidc-client-cert-url": "",
}

VAULT_CONFIG = {
    "vault_address": "127.0.0.1:8081",
    "vault_ca_certificate_bytes": "abcd",
    "vault_mount": "temporal-worker-k8s",
    "vault_role_id": "111",
    "vault_role_secret_id": "222",
    "vault_cert_path": "/vault/cert.pem",
}

DATABASE_CONFIG = {
    "TEMPORAL_DB_HOST": "myhost",
    "TEMPORAL_DB_PORT": "5432",
    "TEMPORAL_DB_USER": "jean-luc",
    "TEMPORAL_DB_PASSWORD": "inner-light",
    "TEMPORAL_DB_TLS": "True",
}

WANT_ENV = {
    "TEMPORAL_AUTH_PROVIDER": "candid",
    "TEMPORAL_CANDID_PRIVATE_KEY": "test-private-key",
    "TEMPORAL_CANDID_PUBLIC_KEY": "test-public-key",
    "TEMPORAL_CANDID_URL": "test-url",
    "TEMPORAL_CANDID_USERNAME": "test-username",
    "TEMPORAL_DB_NAME": "",
    "TEMPORAL_ENCRYPTION_KEY": "",
    "TEMPORAL_HOST": "test-host",
    "TEMPORAL_LOG_LEVEL": "debug",
    "TEMPORAL_NAMESPACE": "test-namespace",
    "TEMPORAL_PROMETHEUS_PORT": 9000,
    "TEMPORAL_OIDC_AUTH_CERT_URL": "",
    "TEMPORAL_OIDC_AUTH_TYPE": "",
    "TEMPORAL_OIDC_AUTH_URI": "",
    "TEMPORAL_OIDC_CLIENT_CERT_URL": "",
    "TEMPORAL_OIDC_CLIENT_EMAIL": "",
    "TEMPORAL_OIDC_CLIENT_ID": "",
    "TEMPORAL_OIDC_PRIVATE_KEY": "",
    "TEMPORAL_OIDC_PRIVATE_KEY_ID": "",
    "TEMPORAL_OIDC_PROJECT_ID": "",
    "TEMPORAL_OIDC_TOKEN_URI": "",
    "TEMPORAL_QUEUE": "test-queue",
    "TEMPORAL_SENTRY_DSN": "",
    "TEMPORAL_SENTRY_ENVIRONMENT": "",
    "TEMPORAL_SENTRY_RELEASE": "",
    "TEMPORAL_SENTRY_SAMPLE_RATE": 1.0,
    "TEMPORAL_SENTRY_REDACT_PARAMS": False,
    "TEMPORAL_TLS_ROOT_CAS": "",
    # The below are kept for backwards-compatibility
    "TWC_AUTH_PROVIDER": "candid",
    "TWC_CANDID_PRIVATE_KEY": "test-private-key",
    "TWC_CANDID_PUBLIC_KEY": "test-public-key",
    "TWC_CANDID_URL": "test-url",
    "TWC_CANDID_USERNAME": "test-username",
    "TWC_DB_NAME": "",
    "TWC_ENCRYPTION_KEY": "",
    "TWC_HOST": "test-host",
    "TWC_LOG_LEVEL": "debug",
    "TWC_NAMESPACE": "test-namespace",
    "TWC_PROMETHEUS_PORT": 9000,
    "TWC_OIDC_AUTH_CERT_URL": "",
    "TWC_OIDC_AUTH_TYPE": "",
    "TWC_OIDC_AUTH_URI": "",
    "TWC_OIDC_CLIENT_CERT_URL": "",
    "TWC_OIDC_CLIENT_EMAIL": "",
    "TWC_OIDC_CLIENT_ID": "",
    "TWC_OIDC_PRIVATE_KEY": "",
    "TWC_OIDC_PRIVATE_KEY_ID": "",
    "TWC_OIDC_PROJECT_ID": "",
    "TWC_OIDC_TOKEN_URI": "",
    "TWC_QUEUE": "test-queue",
    "TWC_SENTRY_DSN": "",
    "TWC_SENTRY_ENVIRONMENT": "",
    "TWC_SENTRY_RELEASE": "",
    "TWC_SENTRY_SAMPLE_RATE": 1.0,
    "TWC_SENTRY_REDACT_PARAMS": False,
    "TWC_TLS_ROOT_CAS": "",
}

WANT_ENV_AUTH = {
    "TEMPORAL_AUTH_PROVIDER": "google",
    "TEMPORAL_ENCRYPTION_KEY": "123",
    "TEMPORAL_OIDC_AUTH_TYPE": "example-auth-type",
    "TEMPORAL_OIDC_PROJECT_ID": "example-project-id",
    "TEMPORAL_OIDC_PRIVATE_KEY_ID": "example-private-key-id",
    "TEMPORAL_OIDC_PRIVATE_KEY": "example-private-key",
    "TEMPORAL_OIDC_CLIENT_EMAIL": "example-client-email",
    "TEMPORAL_OIDC_CLIENT_ID": "example-client-id",
    "TEMPORAL_OIDC_AUTH_URI": "https://example.com/auth",
    "TEMPORAL_OIDC_TOKEN_URI": "https://example.com/token",
    "TEMPORAL_OIDC_AUTH_CERT_URL": "https://example.com/certs",
    "TEMPORAL_OIDC_CLIENT_CERT_URL": "https://example.com/client-certs",
    "TWC_AUTH_PROVIDER": "google",
    "TWC_ENCRYPTION_KEY": "123",
    "TWC_OIDC_AUTH_TYPE": "example-auth-type",
    "TWC_OIDC_PROJECT_ID": "example-project-id",
    "TWC_OIDC_PRIVATE_KEY_ID": "example-private-key-id",
    "TWC_OIDC_PRIVATE_KEY": "example-private-key",
    "TWC_OIDC_CLIENT_EMAIL": "example-client-email",
    "TWC_OIDC_CLIENT_ID": "example-client-id",
    "TWC_OIDC_AUTH_URI": "https://example.com/auth",
    "TWC_OIDC_TOKEN_URI": "https://example.com/token",
    "TWC_OIDC_AUTH_CERT_URL": "https://example.com/certs",
    "TWC_OIDC_CLIENT_CERT_URL": "https://example.com/client-certs",
}


@pytest.fixture
def all_required_relations(peer_relation, vault_relation, database_relation):
    return [
        peer_relation,
        vault_relation,
        database_relation,
    ]


@pytest.fixture
def state(temporal_worker_container, all_required_relations, config, token_secret, vault_nonce_secret, simple_secret):
    return ops.testing.State(
        leader=True,
        config=config,
        containers=[temporal_worker_container],
        relations=all_required_relations,
        secrets=[
            token_secret,
            vault_nonce_secret,
            simple_secret,
        ],
    )


def test_smoke(context, state):
    context.run(context.on.start(), state)


def test_blocked_on_missing_host(context, state):
    state = dataclasses.replace(state, config={})
    state_out = context.run(context.on.config_changed(), state)

    assert state_out.unit_status == ops.BlockedStatus("Invalid config: host value missing")


def test_ready(context, state, temporal_worker_container, namespace, queue):
    state_out = context.run(context.on.pebble_ready(temporal_worker_container), state)
    state_out = context.run(context.on.config_changed(), state_out)

    assert sorted(state_out.get_container("temporal-worker").plan.to_dict()) == sorted(
        {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": WANT_ENV,
                },
            },
        }
    )

    assert (
        state_out.get_container("temporal-worker").service_statuses["temporal-worker"]
        == ops.pebble.ServiceStatus.ACTIVE
    )
    assert state_out.unit_status == ops.MaintenanceStatus("replanning application")

    state_out = context.run(context.on.update_status(), state_out)

    assert state_out.unit_status == ops.ActiveStatus(f"worker listening to namespace {namespace!r} on queue {queue!r}")


def test_invalid_juju_secret(
    context, state, temporal_worker_container, config, missing_oidc_auth_type_secret, vault_nonce_secret
):
    state = dataclasses.replace(
        state,
        secrets=[missing_oidc_auth_type_secret, vault_nonce_secret],
        config={
            **config,
            "auth-secret-id": missing_oidc_auth_type_secret.id,
        },
    )

    state_out = context.run(context.on.pebble_ready(temporal_worker_container), state)
    state_out = context.run(context.on.config_changed(), state_out)

    assert state_out.unit_status == ops.BlockedStatus("Invalid config: oidc-auth-type value missing")


def test_auth_juju_secret(
    context, state, temporal_worker_container, config, oidc_auth_secret, vault_nonce_secret, namespace, queue
):
    state = dataclasses.replace(
        state,
        secrets=[oidc_auth_secret, vault_nonce_secret],
        config={
            **config,
            "auth-secret-id": oidc_auth_secret.id,
        },
    )

    state_out = context.run(context.on.pebble_ready(temporal_worker_container), state)
    state_out = context.run(context.on.config_changed(), state_out)

    expected_env = {**WANT_ENV}
    expected_env.update(**WANT_ENV_AUTH)

    assert sorted(state_out.get_container("temporal-worker").plan.to_dict()) == sorted(
        {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": expected_env,
                },
            },
        }
    )

    assert (
        state_out.get_container("temporal-worker").service_statuses["temporal-worker"]
        == ops.pebble.ServiceStatus.ACTIVE
    )
    assert state_out.unit_status == ops.MaintenanceStatus("replanning application")

    state_out = context.run(context.on.update_status(), state_out)

    assert state_out.unit_status == ops.ActiveStatus(f"worker listening to namespace {namespace!r} on queue {queue!r}")


def test_vault_relation(context, state, temporal_worker_container):
    state_out = context.run(context.on.pebble_ready(temporal_worker_container), state)
    state_out = context.run(context.on.config_changed(), state_out)

    assert sorted(state_out.get_container("temporal-worker").plan.to_dict()) == sorted(
        {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": WANT_ENV,
                },
            },
        }
    )


def test_invalid_environment_config(context, state, temporal_worker_container, config):
    state_out = context.run(context.on.pebble_ready(temporal_worker_container), state)
    state_out = context.run(context.on.config_changed(), state_out)

    invalid_environment_config_env = textwrap.dedent(
        """
        env:
            - hello: world
              wrong: key
    """
    )

    state_out = dataclasses.replace(state_out, config={**config, "environment": invalid_environment_config_env})

    state_out = context.run(context.on.config_changed(), state_out)

    assert state_out.unit_status == ops.BlockedStatus("Invalid environment structure. Check logs")

    invalid_environment_config_juju = textwrap.dedent(
        """
        juju:
            - wrong: key
              key: hello
    """
    )

    state_out = dataclasses.replace(state_out, config={**config, "environment": invalid_environment_config_juju})

    state_out = context.run(context.on.config_changed(), state_out)

    assert state_out.unit_status == ops.BlockedStatus("Invalid environment structure. Check logs")

    invalid_environment_config_vault = textwrap.dedent(
        """
        vault:
            - path: path
              value: wrong
    """
    )

    state_out = dataclasses.replace(state_out, config={**config, "environment": invalid_environment_config_vault})

    state_out = context.run(context.on.config_changed(), state_out)

    assert state_out.unit_status == ops.BlockedStatus("Invalid environment structure. Check logs")


def test_valid_environment_config(context, state, temporal_worker_container, config, simple_secret, token_secret):
    with unittest.mock.patch(
        "ops.jujuversion.JujuVersion.from_environ", return_value=ops.jujuversion.JujuVersion(version="3.6")
    ), unittest.mock.patch(
        "relations.vault.VaultRelation.get_vault_config", return_value=VAULT_CONFIG
    ), unittest.mock.patch(
        "relations.vault.VaultRelation.get_vault_client"
    ) as get_vault_client, unittest.mock.patch(
        "os.makedirs"
    ), unittest.mock.patch(
        "builtins.open", new_callable=unittest.mock.mock_open
    ):
        mock_vault_client = unittest.mock.Mock()
        mock_vault_client.read_secret.return_value = "token_secret"
        get_vault_client.return_value = mock_vault_client

        state_out = context.run(context.on.pebble_ready(temporal_worker_container), state)
        state_out = context.run(context.on.config_changed(), state_out)

        simple_secret_id = simple_secret.id.split(":")[1]
        token_secret_id = token_secret.id.split(":")[1]

        environment_config = textwrap.dedent(
            f"""
            env:
                - name: hello
                  value: world
                - name: test
                  value: variable
                - name: test_nested
                  value:
                    - connection_id: my_connection_id
                      unnesting:
                        tables:
                          table1: [col1, col2]
                          table2: [col3]
                      redaction:
            juju:
                - secret-id: {simple_secret_id}
                  name: sensitive1
                  key: key1
                - secret-id: {simple_secret_id}
                  name: sensitive2
                  key: key2
                - secret-id: {token_secret_id}
            vault:
                - path: secrets
                  name: access_token
                  key: token
        """
        )

        state_out = dataclasses.replace(state_out, config={**config, "environment": environment_config})

        state_out = context.run(context.on.config_changed(), state_out)

        assert sorted(state_out.get_container("temporal-worker").plan.to_dict()) == sorted(
            {
                "services": {
                    "temporal-worker": {
                        "summary": "temporal worker",
                        "command": "./app/scripts/start-worker.sh",
                        "startup": "enabled",
                        "override": "replace",
                        "environment": {
                            **WANT_ENV,
                            # User added secrets through config
                            **{
                                "ACCESS_TOKEN": "token",
                                "CLIENT_SECRET": "secret",
                                "hello": "world",
                                "test": "variable",
                                "sensitive1": "hello",
                                "sensitive2": "world",
                                "access_token": "token_secret",
                                "test_nested": '[{"connection_id": "my_connection_id", "unnesting": {"tables": {"table1": ["col1", "col2"], "table2": ["col3"]}}, "redaction": null}]',
                            },
                        },
                    },
                },
            }
        )


@pytest.mark.database_relation_skipped
def test_blocked_by_missing_db_name(context, state, temporal_worker_container, config):
    config_without_db_name = {**config}
    del config_without_db_name["db-name"]

    state = dataclasses.replace(state, config=config_without_db_name)

    state_out = context.run(context.on.pebble_ready(temporal_worker_container), state)
    state_out = context.run(context.on.config_changed(), state_out)

    assert state_out.unit_status == ops.BlockedStatus("Invalid config: db name value missing")


def test_db_relation(context, state, temporal_worker_container):
    state_out = context.run(context.on.pebble_ready(temporal_worker_container), state)
    state_out = context.run(context.on.config_changed(), state_out)

    assert sorted(state_out.get_container("temporal-worker").plan.to_dict()) == sorted(
        {
            "services": {
                "temporal-worker": {
                    "summary": "temporal worker",
                    "command": "./app/scripts/start-worker.sh",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {
                        **WANT_ENV,
                        **DATABASE_CONFIG,
                        "TEMPORAL_DB_NAME": "temporal-worker-k8s_db",
                        "TWC_DB_NAME": "temporal-worker-k8s_db",
                    },
                },
            },
        }
    )
