terraform {
  required_version = ">= 1.12.2"
  required_providers {
    juju = {
      source  = "juju/juju"
      version = ">= 0.21.1"
    }

    null = {
        source = "null"
        version = ">=3.2.4"
    }
  }
}
