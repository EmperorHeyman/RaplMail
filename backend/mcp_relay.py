"""Dev entry point for the MCP relay (the installed app uses raplmail-backend.exe --mcp).

    python mcp_relay.py      # an MCP stdio server that talks to the running RaplMail
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.mcp.relay import main  # noqa: E402

if __name__ == "__main__":
    main()
