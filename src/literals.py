# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Literals used by the Temporal Worker K8s charm."""

VALID_LOG_LEVELS = ["info", "debug", "warning", "error", "critical"]
REQUIRED_CHARM_CONFIG = ["host", "namespace", "queue"]
REQUIRED_CANDID_CONFIG = ["candid-url", "candid-username", "candid-public-key", "candid-private-key"]
REQUIRED_OIDC_CONFIG = [
    "oidc-auth-type",
    "oidc-project-id",
    "oidc-private-key-id",
    "oidc-private-key",
    "oidc-client-email",
    "oidc-client-id",
    "oidc-auth-uri",
    "oidc-token-uri",
    "oidc-auth-cert-url",
    "oidc-client-cert-url",
]
SUPPORTED_AUTH_PROVIDERS = ["candid", "google"]
