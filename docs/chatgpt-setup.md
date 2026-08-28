# ChatGPT setup

## Local verification

Start the bridge and test `http://127.0.0.1:8000/mcp` with MCP Inspector before
involving ChatGPT. The v0.6.9 baseline has 24 read tools; Phase 7 source has 31 total
tools. Verify discovery and historical reads return structured data, control tools
report `read_only` under defaults, an invalid token produces `authentication_failed`, and no
response contains tokens, private URLs, camera streams, coordinates, raw
configuration, or raw historical attributes.

```bash
npx @modelcontextprotocol/inspector@latest
```

For a Home Assistant App installation, port `8000/tcp` is disabled by default.
Temporarily assign a local host port and add the exact Home Assistant hostname to
`mcp_allowed_hosts` before using Inspector, then remove the mapping. App installation
does not by itself make the MCP endpoint safe or reachable for ChatGPT.

## Connecting ChatGPT

ChatGPT needs either a reachable HTTPS Streamable HTTP endpoint (normally ending
in `/mcp`) or OpenAI's Secure MCP Tunnel for a private/on-premises server. The
official connection flow is Developer mode, ChatGPT Plugins, the plus button, and
the server URL or tunnel connection. See OpenAI's current
[Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
guide and [MCP server guidance](https://developers.openai.com/api/docs/mcp).

**Do not expose this server directly to the public internet.** It has Home
Assistant credentials but intentionally does not yet implement bridge OAuth or
user authentication. Phase 7 server-side policy is defense in depth, not public
endpoint authentication. A later phase should evaluate Secure MCP Tunnel for the
private Home Assistant network, then add supported authentication and deployment
hardening before any public endpoint.

When that phase is complete, the expected MCP URL is:

```text
https://your-approved-host.example/mcp
```

The local `MCP_ALLOWED_HOSTS` defaults will reject that hostname until it is
explicitly approved. That is intentional DNS-rebinding protection, not a setup
error to bypass globally.

## Metadata updates

After changing tool names, descriptions, schemas, or authentication, restart the
server and refresh the connection metadata in ChatGPT before retesting. Published
plugins use reviewed metadata snapshots and have a separate update process.

## Test prompts

- "Can the Ambient bridge connect to Home Assistant?"
- "Which Home Assistant version is running?"
- "Show only the safe server information available from Home Assistant."
- "Find the garage lights."
- "Which entities are unavailable upstairs?"
- "Summarize the current states in the cover domain."
- "Show the recorded changes for the kitchen lights during the last hour."
- "What does the logbook say about light.kitchen_ceiling since 09:00Z?"
- "Give me a quick whole-home status without listing every entity."
- "Are any batteries low, doors open, or devices unavailable?"
- "Report deterministic home findings and show the sensor evidence."
- "Turn off the kitchen lights." (Expected under defaults: exact target discovery,
  then a structured `read_only` result without execution.)
