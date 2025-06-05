# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json

import ops.testing
import pytest

from charm import TemporalWorkerK8SOperatorCharm


def pytest_configure(config):  # noqa: DCO020
    """Flags that can be configured to modify fixture behavior.

    Used to determine how _state in the peer relation app databag is populated.

    Args:
        config: the pytest config object
    """
    config.addinivalue_line("markers", "database_relation_skipped")


@pytest.fixture
def temporal_worker_k8s_charm(monkeypatch):
    yield TemporalWorkerK8SOperatorCharm


@pytest.fixture(scope="function")
def context(temporal_worker_k8s_charm):
    return ops.testing.Context(charm_type=temporal_worker_k8s_charm)


@pytest.fixture(scope="function")
def temporal_worker_container():
    return ops.testing.Container(
        "temporal-worker",
        can_connect=True,
    )


@pytest.fixture(scope="function")
def role_secret():
    return ops.testing.Secret(
        owner="app",
        tracked_content={
            "role-id": "111",
            "role-secret-id": "222",
        },
    )


@pytest.fixture(scope="function")
def vault_nonce_value():
    return "test_nonce"


@pytest.fixture(scope="function")
def vault_nonce_secret(vault_nonce_value):
    return ops.testing.Secret(
        owner="app",
        label="nonce",
        tracked_content={
            "nonce": vault_nonce_value,
        },
    )


@pytest.fixture(scope="function")
def role_credentials(role_secret, vault_nonce_value):
    return {
        vault_nonce_value: role_secret.id,
    }


@pytest.fixture(scope="function")
def peer_relation(request):
    state_data = {}

    if not request.node.get_closest_marker("database_relation_skipped"):
        state_data["database_connection"] = json.dumps(
            {
                "host": "myhost",
                "port": "5432",
                "password": "inner-light",
                "user": "jean-luc",
                "tls": "True",
            }
        )

    return ops.testing.PeerRelation(endpoint="peer", local_app_data=state_data)


@pytest.fixture(scope="function")
def vault_relation(role_credentials):
    return ops.testing.Relation(
        "vault",
        remote_app_data={
            "vault_url": "127.0.0.1:8081",
            "ca_certificate": "abcd",
            "mount": "temporal-worker-k8s",
            "credentials": json.dumps(role_credentials, sort_keys=True),
        },
    )


@pytest.fixture(scope="function")
def namespace():
    return "test-namespace"


@pytest.fixture(scope="function")
def queue():
    return "test-queue"


@pytest.fixture(scope="function")
def config(namespace, queue):
    return {
        "db-name": "temporal-worker-k8s_db",
        "log-level": "debug",
        "host": "test-host",
        "namespace": namespace,
        "queue": queue,
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


@pytest.fixture(scope="function")
def token_secret():
    return ops.testing.Secret(
        owner="app",
        tracked_content={
            "access-token": "token",
            "client-secret": "secret",
        },
    )


@pytest.fixture(scope="function")
def simple_secret():
    return ops.testing.Secret(
        owner="app",
        tracked_content={
            "key1": "hello",
            "key2": "world",
        },
    )


@pytest.fixture(scope="function")
def oidc_auth_secret_content():
    return {
        "auth-provider": "google",
        "encryption-key": "123",
        "oidc-auth-type": "example-auth-type",
        "oidc-project-id": "example-project-id",
        "oidc-private-key-id": "example-private-key-id",
        "oidc-private-key": "example-private-key",
        "oidc-client-email": "example-client-email",
        "oidc-client-id": "example-client-id",
        "oidc-auth-uri": "https://example.com/auth",
        "oidc-token-uri": "https://example.com/token",
        "oidc-auth-cert-url": "https://example.com/certs",
        "oidc-client-cert-url": "https://example.com/client-certs",
    }


@pytest.fixture(scope="function")
def oidc_auth_secret(oidc_auth_secret_content):
    return ops.testing.Secret(
        owner="app",
        tracked_content=oidc_auth_secret_content,
    )


@pytest.fixture(scope="function")
def missing_oidc_auth_type_secret(oidc_auth_secret_content):
    del oidc_auth_secret_content["encryption-key"]
    del oidc_auth_secret_content["oidc-auth-type"]

    return ops.testing.Secret(
        owner="app",
        tracked_content=oidc_auth_secret_content,
    )


@pytest.fixture(scope="function")
def database_relation():
    return ops.testing.Relation(
        "database",
        remote_app_data={
            "database": "temporal-worker-k8s_db",
            "endpoints": "myhost:5432,anotherhost:2345",
            "password": "inner-light",
            "username": "jean-luc",
            "tls": "True",
        },
    )
