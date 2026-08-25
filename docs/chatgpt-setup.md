# ChatGPT setup

## Local verification

Start the bridge and test `http://127.0.0.1:8000/mcp` with MCP Inspector before
involving ChatGPT. Verify that all tools appear, discovery and historical reads
return structured data, an invalid token produces `authentication_failed`, and no
response contains tokens, private URLs, camera streams, coordinates, raw
configuration, or raw historical attributes.

```bash
npx @modelcontextprotocol/inspector@latest
```

## Connecting ChatGPT

ChatGPT needs either a reachable HTTPS Streamable HTTP endpoint (normally ending
in `/mcp`) or OpenAI's Secure MCP Tunnel for a private/on-premises server. The
official connection flow is Developer mode, ChatGPT Plugins, the plus button, and
the server URL or tunnel connection. See OpenAI's current
[Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
guide and [MCP server guidance](https://developers.openai.com/api/docs/mcp).

**Do not expose this server directly to the public internet.** It has Home
Assistant credentials but intentionally does not yet implement bridge OAuth or
user authentication. A safe next phase should evaluate Secure MCP Tunnel for the
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
- "Turn off the kitchen lights." (Expected: no matching control tool.)
