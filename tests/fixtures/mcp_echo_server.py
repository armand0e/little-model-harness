from mcp.server.fastmcp import FastMCP

app = FastMCP("Little Harness MCP smoke server")


@app.tool()
def echo(message: str) -> str:
    """Return a message through MCP."""
    return "MCP says: " + message


if __name__ == "__main__":
    app.run(transport="stdio")
