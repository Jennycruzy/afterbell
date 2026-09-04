"""Report the supported Binance Agent OS connection state.

Binance recognizes OAuth clients registered by supported agent hosts such as
Codex. AFTERBELL therefore does not manufacture its own OAuth client, run a
callback listener, or copy a bearer token into this repository. The supported
connection belongs to Codex and is deliberately outside the recorder, guard,
dashboard, and executor processes.

Connect once from the Codex host:

    codex mcp add binance-agent-os --url https://agent.binance.com/mcp/agentic

Codex starts the provider's OAuth flow. Use ``codex mcp login
binance-agent-os`` to reconnect if necessary. This script is read-only and
exists so an operator can check the integration without reading Codex's
credential store.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

SERVER = "binance-agent-os"


def main() -> None:
    if shutil.which("codex") is None:
        sys.exit("Codex CLI is not installed; configure Binance MCP in a "
                 "supported Codex or ChatGPT client")
    result = subprocess.run(
        ["codex", "mcp", "get", SERVER], text=True, capture_output=True)
    if result.returncode:
        print(f"{SERVER} is not configured.")
        print("Connect it with:")
        print("  codex mcp add binance-agent-os --url "
              "https://agent.binance.com/mcp/agentic")
        sys.exit(result.returncode)
    print(result.stdout.strip())
    print("\nConnection configuration is present. Use Codex's MCP tools for "
          "read-only account checks; AFTERBELL never reads or stores Codex "
          "OAuth credentials.")


if __name__ == "__main__":
    main()
