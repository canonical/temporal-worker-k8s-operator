# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Secret config processors."""

import json
import logging

import yaml
from ops.jujuversion import JujuVersion
from ops.model import ModelError, SecretNotFoundError

logger = logging.getLogger(__name__)


def process_env_variables(parsed_environment_data):
    """Process environment variables from the parsed secrets data.

    Args:
        parsed_environment_data: Parsed secrets data.

    Returns:
        dict: A dictionary containing environment variables.
    """
    charm_env = {}
    env_variables = parsed_environment_data.get("env", {})
    for env_variable in env_variables:
        key_name = env_variable.get("name")
        key_value = env_variable.get("value")
        if isinstance(key_value, (dict, list)):
            charm_env.update({key_name: json.dumps(key_value)})
        else:
            charm_env.update({key_name: key_value})

    return charm_env


def process_juju_variables(charm, parsed_environment_data):
    """Process Juju secrets from the parsed secrets data.

    Args:
        charm: The charm to perform operations on.
        parsed_environment_data: Parsed secrets data.

    Returns:
        dict: A dictionary containing Juju secrets.

    Raises:
        ValueError: If the Juju version does not support Juju user secrets,
                    if a specified Juju secret is not found,
                    or if the charm does not have permission to access the specified Juju secret.
    """
    charm_env = {}
    if parsed_environment_data.get("juju") and not JujuVersion.from_environ().has_secrets:
        raise ValueError("Juju version does not support Juju user secrets")

    juju_variables = parsed_environment_data.get("juju", [])
    for juju_secret in juju_variables:
        try:
            secret_id = juju_secret.get("secret-id")
            key_name = juju_secret.get("name")
            from_key = juju_secret.get("key")

            secret = charm.model.get_secret(id=secret_id)
            secret_content = secret.get_content(refresh=True)
            charm_env.update({key_name: secret_content[from_key]})
        except SecretNotFoundError as e:
            raise ValueError(f"Juju secret `{secret_id}` not found") from e
        except ModelError as e:
            raise ValueError(f"Access permission not granted to charm for secret `{secret_id}`") from e
        except KeyError as e:
            logger.error(f"Error parsing secrets env: {e}")
            raise ValueError(f"Error parsing secrets env: {e}") from e

    return charm_env


def process_vault_variables(charm, parsed_environment_data):
    """Process Vault secrets from the parsed secrets data.

    Args:
        charm: The charm to perform operations on.
        parsed_environment_data: Parsed secrets data.

    Returns:
        dict: A dictionary containing Vault secrets.

    Raises:
        ValueError: If there is no vault relation, if there is an error initializing the vault client,
                    or if there is an error reading a vault secret.
    """
    # TODO (kelkawi-a): Convert to using structured config
    charm_env = {}
    vault_variables = parsed_environment_data.get("vault", [])

    if vault_variables and not charm.model.relations["vault"]:
        raise ValueError("No vault relation found to fetch secrets from")

    if vault_variables and charm.model.relations["vault"]:
        try:
            vault_client = charm.vault_relation.get_vault_client()
        except Exception as e:
            logger.error("Unable to initialize vault client: %s", e)
            raise ValueError("Unable to initialize vault client. Remove relation and retry.") from e

        for item in vault_variables:
            key_name = item.get("name")
            from_key = item.get("key")
            path = item.get("path")
            try:
                secret = vault_client.read_secret(path=path, key=from_key)
            except Exception as e:
                raise ValueError(f"Unable to read vault secret `{from_key}` at path `{path}`: {e}") from e
            charm_env.update({key_name: secret})

    for key in charm_env:
        if key.startswith("TEMPORAL_") or key.startswith("TWC_"):
            raise ValueError("Environment variables cannot use reserved prefix 'TEMPORAL_' or 'TWC_'")

    return charm_env


def parse_environment(yaml_string):
    """Parse a YAML string containing environment variables and validates its structure.

    The YAML string may contain 'env', 'juju', and 'vault' keys as required.
    Each nested key should follow a specific structure:
        - 'env': A list of dictionaries with 'name' and 'value' keys.
        - 'juju': A list of dictionaries with 'secret-id', 'name', and 'key' keys.
        - 'vault': A list of dictionaries with 'path', 'name', and 'key' keys.

    Args:
        yaml_string: The YAML string to be parsed.

    Returns:
        dict: A dictionary with the parsed and validated secrets.
              The structure of the returned dictionary is:
              {
                  "env": [{"name": str, "value": str}],
                  "juju": [{"secret-id": str, "name": str, "key": str}],
                  "vault": [{"path": str, "name": str, "key": str}]
              }

    Raises:
        ValueError: If the YAML string does not conform to the expected structure.
    """
    data = yaml.safe_load(yaml_string)

    # Validate env key
    env = data.get("env", [])
    if not isinstance(env, list) or not all(
        isinstance(item, dict) and "name" in item and "value" in item and len(item) == 2 for item in env
    ):
        raise ValueError(
            "Invalid environment structure: 'env' should be a list of dictionaries with 'name' and 'value'"
        )

    # Validate juju key
    juju = data.get("juju", [])
    if not isinstance(juju, list) or not all(
        isinstance(item, dict) and "secret-id" in item and "name" in item and "key" in item and len(item) == 3
        for item in juju
    ):
        raise ValueError(
            "Invalid environment structure: 'juju' should be a list of dictionaries with 'secret-id', 'name', and 'key'"
        )

    # Validate vault key
    vault = data.get("vault", [])
    if not isinstance(vault, list) or not all(
        isinstance(item, dict) and "path" in item and "name" in item and "key" in item and len(item) == 3
        for item in vault
    ):
        raise ValueError(
            "Invalid environment structure: 'vault' should be a list of dictionaries with 'path', 'name', and 'key'"
        )

    parsed_data = {
        "env": [{"name": item.get("name"), "value": item.get("value")} for item in env],
        "juju": [
            {"secret-id": item.get("secret-id"), "name": item.get("name"), "key": item.get("key")} for item in juju
        ],
        "vault": [{"path": item.get("path"), "name": item.get("name"), "key": item.get("key")} for item in vault],
    }

    return parsed_data
