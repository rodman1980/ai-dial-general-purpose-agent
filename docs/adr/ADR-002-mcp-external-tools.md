---
title: ADR-002 - MCP for External Tools
status: Accepted
date: 2025-12-30
decision-makers: Architecture Team
consulted: Development Team, Integration Team
informed: All Stakeholders
---

# ADR-002: Model Context Protocol (MCP) for External Tools

## Status
**Accepted** - Implemented for Python Interpreter and DuckDuckGo Search

## Context

The agent needs to integrate external capabilities (web search, code execution) that are better implemented as separate services rather than in-process tools. Requirements:

- **Isolation**: Tool execution shouldn't crash the agent
- **Language-Agnostic**: Tools can be written in any language
- **Discoverability**: Agent should dynamically discover tool capabilities
- **Versioning**: Tool updates shouldn't break agent compatibility
- **Scalability**: Tools can scale independently

### Options Considered

1. **Model Context Protocol (MCP)** - Chosen
   - Standard protocol from Anthropic
   - HTTP-based (stateless)
   - Tool discovery via schema endpoint
   - Execution via call_tool endpoint

2. **Custom REST API**
   - Design our own protocol
   - OpenAPI specs for each tool
   - Direct HTTP calls

3. **gRPC Services**
   - Binary protocol (faster)
   - Strong typing with protobuf
   - Service mesh integration

4. **In-Process Tools**
   - Import as Python modules
   - Direct function calls
   - No network overhead

## Decision

**We will use MCP (Model Context Protocol)** as the standard interface for external tool servers.

### Implementation

```python
# MCP Client (agent side)
class MCPClient:
    async def get_tools(self) -> list[MCPToolModel]:
        """Discover available tools"""
        response = await self.session.get(f"{self.url}/tools")
        return [MCPToolModel(**tool) for tool in response.json()["tools"]]
    
    async def call_tool(self, name: str, arguments: dict) -> str:
        """Execute tool"""
        response = await self.session.post(
            f"{self.url}/call_tool",
            json={"name": name, "arguments": arguments}
        )
        return response.json()["content"][0]["text"]

# MCP Server (tool side)
@app.get("/tools")
def list_tools():
    return {
        "tools": [
            {
                "name": "duckduckgo_web_search",
                "description": "Search the web using DuckDuckGo",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            }
        ]
    }

@app.post("/call_tool")
def call_tool(request: ToolCallRequest):
    if request.name == "duckduckgo_web_search":
        results = ddg.search(request.arguments["query"])
        return {"content": [{"type": "text", "text": results}]}
```

## Rationale

### Advantages

**1. Standardization**
- MCP is an emerging standard (Anthropic-backed)
- Growing ecosystem of MCP servers
- Documentation and tooling available

**2. Simplicity**
- HTTP-based (no special transport)
- JSON payloads (easy to debug)
- Stateless (no connection management complexity)

**3. Discoverability**
- `/tools` endpoint returns schema
- Agent automatically learns tool capabilities
- No manual configuration needed

**Example**:
```python
# Agent discovers all tools automatically
client = await MCPClient.create("http://search-server:8000/mcp")
tools = await client.get_tools()  # Returns list of available tools
```

**4. Isolation**
- Tool crashes don't affect agent
- Tools can restart independently
- Resource limits per tool

**5. Polyglot**
- Tools can be written in any language
- Python, Node.js, Go, Rust all supported
- Choose best tool for the job

**Example Ecosystem**:
- Python Interpreter: Python (Jupyter kernel)
- DuckDuckGo Search: Node.js (duckduckgo-lite)
- Future SQL Tool: Go (connection pooling)

**6. Versioning**
- Each tool server has its own version
- Breaking changes isolated to one tool
- Rolling updates without agent downtime

### Disadvantages & Mitigations

**1. Network Latency**
- Risk: HTTP calls slower than in-process
- Mitigation: Local deployment, connection pooling, caching

**Measurement**: ~10-50ms latency overhead (acceptable for agent use case)

**2. Additional Infrastructure**
- Risk: More containers to manage
- Mitigation: Docker Compose for local dev, K8s for production

**3. Debugging Complexity**
- Risk: Distributed system harder to debug
- Mitigation: Request IDs, structured logging, distributed tracing

**4. Protocol Immaturity**
- Risk: MCP spec still evolving
- Mitigation: Abstract MCPClient, can swap transport later

**5. Network Failures**
- Risk: Tool server unreachable
- Mitigation: Health checks, retries, graceful degradation

**Example**:
```python
try:
    result = await mcp_client.call_tool("search", args)
except ConnectionError:
    return "Search service temporarily unavailable"
```

### Rejected Alternatives

**Custom REST API**

Rejected because:
- Reinventing the wheel (MCP exists)
- No discoverability standard (custom per tool)
- Fragmentation across tools (inconsistent patterns)
- More maintenance burden

**gRPC Services**

Rejected because:
- Over-engineered for this use case
- Requires protobuf compilation
- HTTP/2 not supported by all infrastructure
- Harder to debug (binary protocol)

**Would reconsider for**:
- Ultra-high performance requirements (>10k RPS)
- Strong typing critical (complex data structures)
- Service mesh already in use

**In-Process Tools**

Rejected because:
- No isolation (tool crash = agent crash)
- Python-only (can't use best tools)
- Memory sharing issues (large data processing)
- Harder to scale independently

**Kept for**: Simple, lightweight tools (file extraction, RAG)

## Implementation Details

### MCP Server Structure

**Docker Deployment**:
```yaml
# docker-compose.yml
services:
  python-interpreter:
    image: ghcr.io/epam/python-mcp-server:0.3.0
    ports:
      - "8050:8050"
    environment:
      LOG_LEVEL: "INFO"
    mem_limit: 2G  # Isolated resource limits
    cpus: 2.0
```

**Health Checks**:
```bash
curl http://localhost:8050/health
# Response: {"status": "ok", "uptime": 3600}
```

### Agent Integration

**Discovery**:
```python
# In _create_tools()
mcp_tools = await self._get_mcp_tools("http://localhost:8050/mcp")
tools.extend(mcp_tools)  # Automatically available to agent
```

**Execution**:
```python
# MCPTool wraps MCP call as BaseTool
class MCPTool(BaseTool):
    async def _execute(self, params):
        return await self.client.call_tool(self.name, arguments)
```

## Consequences

### Positive

✅ **Easy Tool Addition**: Deploy MCP server → automatically available to agent

✅ **Community Tools**: Can use open-source MCP servers (growing ecosystem)

✅ **Technology Choice**: Use Python for agent, Node.js for search, Go for SQL

✅ **Independent Scaling**: Scale Python interpreter to 10 instances, agent to 5

### Negative

⚠️ **Operational Complexity**: 2 additional containers to monitor (Python, Search)

⚠️ **Network Dependency**: Requires reliable networking between services

⚠️ **Protocol Maturity**: MCP spec still evolving (v1.0 not yet released)

### Neutral

🔄 **Hybrid Approach**: Some tools in-process (file, RAG), some via MCP (search, code)

## Migration Path

If MCP proves insufficient:

**Phase 1**: Abstract MCPClient interface
```python
class ToolClient(ABC):
    @abstractmethod
    async def call_tool(self, name, args): pass

class MCPClient(ToolClient):
    # Current MCP implementation

class GRPCClient(ToolClient):  # Future alternative
    # gRPC implementation
```

**Phase 2**: Implement alternative client (gRPC, GraphQL, etc.)

**Phase 3**: Gradually migrate tools to new protocol

**Cost**: ~1 week per protocol implementation (interface already abstracted)

## Related Decisions

- [ADR-001: Agent-as-Orchestrator](./ADR-001-agent-orchestrator-pattern.md) - Why we need external tools
- [ADR-004: Async-First Architecture](./ADR-004-async-first-architecture.md) - How MCP calls are async
- [ADR-005: Template Method for Tools](./ADR-005-template-method-tools.md) - Uniform tool interface

## MCP Ecosystem

**Current MCP Servers Used**:
- [Python Interpreter](https://github.com/khshanovskyi/mcp-python-code-interpreter) - Jupyter kernel
- [DuckDuckGo Search](https://github.com/khshanovskyi/duckduckgo-mcp-server) - Web search

**Potential Future MCP Servers**:
- SQL Query Tool (PostgreSQL/MySQL)
- Browser Automation (Playwright)
- API Testing Tool (Postman-like)
- Cloud Resource Management (AWS/GCP)

## References

- [MCP Specification](https://github.com/modelcontextprotocol/specification)
- [Anthropic MCP Announcement](https://www.anthropic.com/news/model-context-protocol)
- [MCP Python SDK](https://pypi.org/project/mcp/)

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-30 | Architecture Team | Initial decision |
