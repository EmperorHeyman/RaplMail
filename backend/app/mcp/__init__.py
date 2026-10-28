"""MCP (Model Context Protocol) server: lets AI apps - Claude Desktop, Claude
Code, other MCP clients - work with your mail in RaplMail.

How it fits together:

* ``tools``    - what an AI app may do, in three access levels (read / act / send)
* ``protocol`` - the JSON-RPC side of MCP (initialize, tools/list, tools/call)
* ``endpoint`` - where the running app can be reached (a small file in the data dir)
* ``relay``    - the stdio bridge an AI app launches (``raplmail-backend.exe --mcp``);
                 it forwards each message to the running RaplMail

Everything here must stay cheap to import: the relay loads these modules on
every AI-app start, so heavy imports (the app, the DB) live inside functions.
"""
