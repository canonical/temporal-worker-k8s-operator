# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

"""Unit test literals."""

CONTAINER_NAME = "temporal-worker"
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

SECRETS_CONFIG = """
secrets:
  env:
    - hello: world
    - test: variable
  juju:
    - secret-id: my-secret
      key: sensitive1
    - secret-id: my-secret
      key: sensitive2
  vault:
    - path: secrets
      key: token
"""

VAULT_CONFIG = {
    "vault_address": "127.0.0.1:8081",
    "vault_ca_certificate_bytes": "abcd",
    "vault_mount": "temporal-worker-k8s",
    "vault_role_id": "111",
    "vault_role_secret_id": "222",
    "vault_cert_path": "/vault/cert.pem",
}

EXPECTED_VAULT_ENV = {
    "TWC_VAULT_ADDRESS": "127.0.0.1:8081",
    "TWC_VAULT_CA_CERTIFICATE_BYTES": "abcd",
    "TWC_VAULT_MOUNT": "temporal-worker-k8s",
    "TWC_VAULT_ROLE_ID": "111",
    "TWC_VAULT_ROLE_SECRET_ID": "222",
    "TWC_VAULT_CERT_PATH": "/vault/cert.pem",
}

WANT_ENV = {
    "TWC_AUTH_PROVIDER": "candid",
    "TWC_CANDID_PRIVATE_KEY": "test-private-key",
    "TWC_CANDID_PUBLIC_KEY": "test-public-key",
    "TWC_CANDID_URL": "test-url",
    "TWC_CANDID_USERNAME": "test-username",
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
