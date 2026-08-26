"""Docker liveness probe that treats upstream HA outages as degraded, not dead."""

from __future__ import annotations

import json
import os
import sys
from urllib.request import urlopen

from ambient_ha.launcher import RuntimeConfigurationError, drop_container_privileges


def main() -> None:
    """Exit successfully when the application health endpoint is responsive."""
    try:
        drop_container_privileges()
    except RuntimeConfigurationError:
        sys.exit(1)
    port = os.environ.get("MCP_PORT", "8000")
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        sys.exit(1)
    if response.status == 200 and payload.get("application_running") is True:
        return
    sys.exit(1)


if __name__ == "__main__":
    main()
