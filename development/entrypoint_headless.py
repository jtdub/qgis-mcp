#!/usr/bin/env python3
"""Start the QGIS MCP plugin socket server inside a headless QGIS.

The plugin normally starts its server when a user clicks Start in the dock. A
container has no dock, so this builds the server directly and runs the Qt event
loop that drives its poll timer.

The token comes from QGIS_MCP_TOKEN. A container cannot show you a generated
one, so it must be given.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for import_root in (REPO_ROOT, REPO_ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from qgis.testing import start_app  # noqa: E402
from qgis.testing.mocked import get_iface  # noqa: E402

from qgis_mcp_plugin.qgis_mcp_plugin import PLUGIN_VERSION, QgisMCPServer  # noqa: E402


def main():
    """Run the plugin server until the process is stopped.

    Returns:
        The process exit code.
    """
    token = os.environ.get("QGIS_MCP_TOKEN")
    if not token:
        print("QGIS_MCP_TOKEN is not set. Copy development/creds.example.env.", file=sys.stderr)
        return 1

    host = os.environ.get("QGIS_MCP_HOST", "0.0.0.0")  # noqa: S104
    port = int(os.environ.get("QGIS_MCP_PORT", "9876"))

    app = start_app()
    server = QgisMCPServer(host=host, port=port, iface=get_iface(), token=token)

    if not server.start():
        print(f"Could not bind {host}:{port}.", file=sys.stderr)
        return 1

    print(f"QGIS MCP plugin {PLUGIN_VERSION} listening on {host}:{port}", flush=True)
    try:
        return app.exec_()
    finally:
        server.stop()


if __name__ == "__main__":
    sys.exit(main())
