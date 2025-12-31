---
title: System Architecture
description: Comprehensive architecture documentation with data flows, design patterns, and technical decisions
version: 1.0.0
last_updated: 2025-12-30
related: [README.md, api.md, adr/ADR-001-agent-orchestrator-pattern.md]
tags: [architecture, design-patterns, data-flow, mcp, async]
---

# System Architecture

## Table of Contents

- [Overview](#overview)
- [Architecture Pattern](#architecture-pattern)
- [System Components](#system-components)
- [Data Flow](#data-flow)
- [Tool Architecture](#tool-architecture)
- [State Management](#state-management)
- [Error Handling](#error-handling)
- [Security Model](#security-model)
- [Performance Considerations](#performance-considerations)
- [Design Decisions](#design-decisions)

## Overview

The DIAL General Purpose Agent implements an **Agent-as-Orchestrator** pattern where an LLM (GPT-4o or Claude Sonnet 3.7) acts as the decision-making engine, selecting and coordinating tool executions to accomplish user tasks.

### High-Level Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        A[Web Browser<br/>DIAL Chat UI<br/>Port 3000]
    end
    
    subgraph "DIAL Platform"
        B[DIAL Core<br/>API Gateway<br/>Port 8080]
        C[DIAL Adapter<br/>Protocol Adapter]
        D[Redis Cache<br/>Port 6379]
    end
    
    subgraph "Agent Application"
        E[General Purpose Agent<br/>task/app.py<br/>Port 5030]
        F[Agent Orchestrator<br/>task/agent.py]
        G[Tool Registry<br/>task/tools/]
    end
    
    subgraph "External Tools"
        H[DuckDuckGo MCP<br/>Port 8051]
        I[Python Interpreter MCP<br/>Port 8050]
    end
    
    subgraph "LLM Upstreams"
        J[OpenAI GPT-4o<br/>EPAM AI Proxy]
        K[Anthropic Claude<br/>EPAM AI Proxy]
        L[DALL-E-3<br/>EPAM AI Proxy]
    end
    
    A -->|HTTP/REST| B
    B -->|Forward Auth Token| E
    E --> F
    F -->|Tool Calls| G
    G -->|MCP Protocol| H
    G -->|MCP Protocol| I
    F -->|Chat Completion| C
    C -->|API Calls| J
    C -->|API Calls| K
    C -->|API Calls| L
    B --> D
    
    style E fill:#f9f,stroke:#333,stroke-width:4px
    style F fill:#bbf,stroke:#333,stroke-width:2px
```

### Key Architectural Principles

1. **Separation of Concerns**: Agent (orchestration) ↔ Tools (execution) ↔ Infrastructure (DIAL/MCP)
2. **Async-First Design**: All I/O operations are async (tool execution, LLM calls, MCP communication)
3. **Fail-Safe Tool Execution**: Tool errors don't crash agent - returned as messages for LLM to handle
4. **Hidden State Management**: Full conversation history hidden from UI but preserved for agent context
5. **Per-Request Authentication**: User's API keys forwarded per-request, never stored

## Architecture Pattern

### Agent-as-Orchestrator Flow

```mermaid
sequenceDiagram
    participant User
    participant DIAL Core
    participant Agent
    participant LLM
    participant Tools
    participant MCP Servers

    User->>DIAL Core: Chat Request + API Key
    DIAL Core->>Agent: Forward Request (with auth token)
    
    loop Recursive Orchestration
        Agent->>Agent: Prepare Messages (inject system prompt)
        Agent->>LLM: Stream Chat Completion + Tool Schemas
        
        alt Tool Calls Present
            LLM-->>Agent: Stream: content + tool_calls[]
            Agent->>Agent: Accumulate tool calls by index
            
            par Parallel Tool Execution
                Agent->>Tools: Execute Tool 1 (async)
                Agent->>Tools: Execute Tool 2 (async)
                Tools->>MCP Servers: MCP Protocol Request
                MCP Servers-->>Tools: MCP Response
                Tools-->>Agent: Tool Result Messages
            end
            
            Agent->>Agent: Append to State (hidden from user)
            Note over Agent: Recursive call with updated history
        else No Tool Calls
            LLM-->>Agent: Final Response
            Agent->>DIAL Core: Stream Response
            DIAL Core->>User: Display Response
        end
    end
```

### Recursive Streaming Pattern

The agent uses a recursive approach to handle multi-turn tool interactions:

```python
async def handle_request():
    while True:
        # 1. Stream LLM response with tool schemas
        response = await llm.stream(messages, tools)
        
        # 2. Accumulate content + tool_calls
        tool_calls = accumulate_streaming_tool_calls(response)
        
        # 3. Decision point
        if not tool_calls:
            return final_response  # Base case
        
        # 4. Execute tools in parallel
        tool_results = await asyncio.gather(*[
            tool.execute(params) for tool in tool_calls
        ])
        
        # 5. Append to hidden state
        state.append(assistant_message)
        state.append(tool_results)
        
        # 6. Recurse with updated history
        messages = prepare_messages(state)
        # Continue loop...
```

**Why Recursive?**
- LLM may need multiple tool calls to complete task (e.g., extract file → analyze → generate chart)
- Each tool result provides new context for next decision
- Gracefully handles errors (tool failure → LLM sees error → tries alternative)

## System Components

### 1. Application Layer (`task/app.py`)

**Responsibility**: Entry point, tool initialization, request routing

```mermaid
classDiagram
    class GeneralPurposeAgentApplication {
        +tools: list~BaseTool~
        +chat_completion(request, response)
        -_create_tools() list~BaseTool~
        -_get_mcp_tools(url) list~BaseTool~
    }
    
    class DIALApp {
        <<framework>>
        +add_chat_completion()
    }
    
    DIALApp --> GeneralPurposeAgentApplication: registers
    GeneralPurposeAgentApplication --> "1..*" BaseTool: manages
```

**Key Behaviors:**
- **Lazy Tool Initialization**: Tools created on first request, cached for subsequent requests
- **MCP Discovery**: Dynamically discovers tools from MCP servers via HTTP
- **DIAL Integration**: Implements `ChatCompletion` interface from `aidial-sdk`

**Initialization Sequence:**

```mermaid
sequenceDiagram
    participant App as app.py
    participant Tools as Tool Registry
    participant MCP as MCP Servers

    App->>App: First Request Received
    App->>Tools: Create Deployment Tools (ImageGen)
    App->>Tools: Create File Tools (Extraction)
    App->>Tools: Create RAG Tool (FAISS)
    App->>MCP: Connect to Python Interpreter MCP
    MCP-->>App: Return Tool Schemas
    App->>Tools: Wrap as PythonCodeInterpreterTool
    App->>MCP: Connect to DuckDuckGo MCP
    MCP-->>App: Return Tool Schemas
    App->>Tools: Wrap as MCPTool instances
    App->>App: Cache tools for reuse
```

### 2. Orchestration Layer (`task/agent.py`)

**Responsibility**: LLM coordination, tool execution, state management

**Core Method: `handle_request()`**

```python
async def handle_request(deployment, choice, request, response):
    """
    Recursive orchestration loop:
    1. Prepare messages (inject system prompt + unpack state)
    2. Stream LLM response
    3. Accumulate tool_calls by index
    4. If tool_calls: execute → update state → recurse
    5. Else: return final response
    """
```

**Tool Call Accumulation Pattern** (OpenAI Streaming Spec):

```mermaid
stateDiagram-v2
    [*] --> WaitingForToolCall
    WaitingForToolCall --> AccumulatingArgs: delta.tool_calls[i].id present
    AccumulatingArgs --> AccumulatingArgs: delta.tool_calls[i].function.arguments
    AccumulatingArgs --> ExecuteTools: stream complete
    ExecuteTools --> [*]: all tools executed
    
    note right of AccumulatingArgs
        Tool calls arrive incrementally:
        1. First chunk: id + function name
        2. Subsequent chunks: argument fragments
        3. Must accumulate by index
    end note
```

**Message Preparation Flow:**

```mermaid
flowchart TD
    A[Incoming Request Messages] --> B[Unpack Messages]
    B --> C[Retrieve State: TOOL_CALL_HISTORY_KEY]
    C --> D{State Has Hidden History?}
    D -->|Yes| E[Merge User Messages + Tool History]
    D -->|No| F[Use Messages As-Is]
    E --> G[Inject System Prompt at Position 0]
    F --> G
    G --> H[Send to LLM]
    
    style C fill:#ffffcc
    style G fill:#ccffcc
```

**Why Unpack Messages?**
- DIAL attachments sent as URLs, need conversion to text
- Hidden tool call history stored in `custom_content.state`
- System prompt injected per-request (security: never visible to user)

### 3. Tool Layer (`task/tools/`)

**Responsibility**: Encapsulate external capabilities, uniform interface

```mermaid
classDiagram
    class BaseTool {
        <<abstract>>
        +name: str
        +description: str
        +parameters: dict
        +schema: ToolParam
        +show_in_stage: bool
        +execute(ToolCallParams) Message
        -_execute(ToolCallParams)* str|Message
    }
    
    class FileContentExtractionTool {
        +name: "file_content_extraction"
        -_execute() Message
        -_paginate(content, page) str
    }
    
    class RagTool {
        +name: "rag_search"
        +document_cache: DocumentCache
        -_execute() Message
        -_index_document() FAISS
        -_search(query, k=3) list
    }
    
    class ImageGenerationTool {
        +name: "image_generation"
        -_execute() Message
        -_call_dall_e() Attachment
    }
    
    class MCPTool {
        +name: dynamic
        +client: MCPClient
        +mcp_tool_model: MCPToolModel
        -_execute() str
    }
    
    class PythonCodeInterpreterTool {
        +name: "execute_code"
        +client: MCPClient
        -_execute() Message
        -_format_output() str
    }
    
    BaseTool <|-- FileContentExtractionTool
    BaseTool <|-- RagTool
    BaseTool <|-- ImageGenerationTool
    BaseTool <|-- MCPTool
    BaseTool <|-- PythonCodeInterpreterTool
```

**Template Method Pattern** (`BaseTool.execute()`):

```python
async def execute(tool_call_params: ToolCallParams) -> Message:
    """Public API: wraps _execute() with error handling"""
    message = Message(role=TOOL, name=self.name, tool_call_id=...)
    try:
        result = await self._execute(tool_call_params)  # Subclass implements
        message.content = result if isinstance(result, str) else result
    except Exception as e:
        message.content = f"Error: {e}"  # Fail-safe: return error as content
    return message
```

**Why Template Method?**
- Uniform error handling across all tools
- Consistent message structure (role=TOOL, tool_call_id)
- Subclasses focus on logic, not infrastructure

### 4. MCP Integration Layer (`task/tools/mcp/`)

**Model Context Protocol** enables external tool servers.

```mermaid
graph LR
    A[Agent] -->|1. Discover Tools| B[MCPClient]
    B -->|2. HTTP GET /tools| C[MCP Server]
    C -->|3. Tool Schemas| B
    B -->|4. Wrap as MCPTool| D[Tool Registry]
    
    A -->|5. Execute Tool| E[MCPTool]
    E -->|6. MCP Protocol| B
    B -->|7. HTTP POST| C
    C -->|8. Result| B
    B -->|9. Message| E
    E -->|10. Tool Message| A
    
    style C fill:#ffcccc
```

**MCPClient** (`task/tools/mcp/mcp_client.py`):
- Async context manager for connection lifecycle
- Stateless HTTP transport (no WebSocket dependency)
- Tool discovery via `/tools` endpoint
- Tool execution via `/call_tool` endpoint

**Supported MCP Servers:**
1. **DuckDuckGo Search** (`port 8051`): Web search + content fetching
2. **Python Interpreter** (`port 8050`): Jupyter kernel execution

### 5. Utility Layer (`task/utils/`)

**Modules:**

```mermaid
graph TD
    A[task/utils/] --> B[history.py<br/>Message Unpacking]
    A --> C[stage.py<br/>UI Visualization]
    A --> D[dial_file_conent_extractor.py<br/>File Access]
    A --> E[constants.py<br/>Configuration]
    
    B -->|unpack_messages| F[Convert attachments to text]
    B -->|merge state| G[Combine user + tool history]
    C -->|open_stage| H[Create UI stage]
    C -->|close_stage_safely| I[Handle errors gracefully]
    D -->|extract_text| J[Fetch from DIAL storage]
```

## Data Flow

### Complete Request-Response Cycle

```mermaid
sequenceDiagram
    autonumber
    participant User
    participant Chat UI
    participant DIAL Core
    participant Agent
    participant Orchestrator
    participant Tool
    participant MCP
    participant LLM Upstream

    User->>Chat UI: Attach file + Ask question
    Chat UI->>DIAL Core: POST /chat/completions<br/>{messages, attachments, api_key}
    DIAL Core->>DIAL Core: Route to general-purpose-agent
    DIAL Core->>Agent: Forward request (port 5030)
    
    Agent->>Orchestrator: chat_completion(request, response)
    Orchestrator->>Orchestrator: Prepare messages:<br/>- Inject system prompt<br/>- Unpack attachments
    
    Orchestrator->>LLM Upstream: Stream chat completion<br/>+ tool schemas
    LLM Upstream-->>Orchestrator: Stream delta: tool_calls
    Orchestrator->>Orchestrator: Accumulate by index
    
    par Tool Execution (Parallel)
        Orchestrator->>Tool: execute(file_extraction)
        Tool->>DIAL Core: Fetch file content
        DIAL Core-->>Tool: File bytes
        Tool-->>Orchestrator: Message(role=TOOL)
        
        Orchestrator->>Tool: execute(rag_search)
        Tool->>Tool: Index with FAISS
        Tool->>Tool: Search top-3 chunks
        Tool-->>Orchestrator: Message(role=TOOL)
    end
    
    Orchestrator->>Orchestrator: Update state (hidden)
    Orchestrator->>LLM Upstream: Recursive call with results
    LLM Upstream-->>Orchestrator: Final response (no tool_calls)
    
    Orchestrator->>Chat UI: Stream response via DIAL Core
    Chat UI->>User: Display answer
```

### Tool Execution Data Flow

```mermaid
flowchart TD
    A[LLM Returns Tool Call] --> B{Tool Type}
    
    B -->|File Extraction| C[FileContentExtractionTool]
    C --> C1[Parse Arguments: file_url, page]
    C1 --> C2[Fetch from DIAL Storage]
    C2 --> C3[Extract Text]
    C3 --> C4[Paginate: 10KB chunks]
    C4 --> C5[Return Message + Footer]
    
    B -->|RAG Search| D[RagTool]
    D --> D1[Check DocumentCache]
    D1 --> D2{Already Indexed?}
    D2 -->|No| D3[Fetch + Split Text]
    D3 --> D4[Embed: SentenceTransformer]
    D4 --> D5[Index: FAISS]
    D5 --> D6[Cache 24h]
    D2 -->|Yes| D7[Load from Cache]
    D6 --> D8[Search: query embedding]
    D7 --> D8
    D8 --> D9[Top-3 Chunks]
    D9 --> D10[Call LLM with Context]
    D10 --> D11[Return Generated Answer]
    
    B -->|Image Generation| E[ImageGenerationTool]
    E --> E1[Parse Arguments: prompt]
    E1 --> E2[Call DALL-E-3 Deployment]
    E2 --> E3[Receive Image URL]
    E3 --> E4[Create Attachment]
    E4 --> E5[Return Message + Attachment]
    
    B -->|Python Code| F[PythonCodeInterpreterTool]
    F --> F1[Parse Arguments: code]
    F1 --> F2[Call MCP Server: execute_code]
    F2 --> F3[Jupyter Kernel Runs Code]
    F3 --> F4{Has Outputs?}
    F4 -->|Yes| F5[Extract: stdout, images, errors]
    F4 -->|No| F6[Return Success]
    F5 --> F7[Format as Markdown]
    F7 --> F8[Return Message + Attachments]
    
    B -->|Web Search| G[MCPTool: DuckDuckGo]
    G --> G1[Parse Arguments: query]
    G1 --> G2[Call MCP Server: web_search]
    G2 --> G3[DuckDuckGo API Call]
    G3 --> G4[Parse Results]
    G4 --> G5[Return Formatted Text]
```

## Tool Architecture

### Tool Categories

| Category | Tools | Purpose | Technology |
|----------|-------|---------|------------|
| **Deployment** | ImageGenerationTool | Call DIAL models as tools | DALL-E-3 API |
| **File** | FileContentExtractionTool | Extract content from attachments | pdfplumber, BeautifulSoup, pandas |
| **RAG** | RagTool | Semantic search over documents | FAISS, SentenceTransformers |
| **MCP** | MCPTool (DuckDuckGo) | Web search via external server | MCP Protocol, HTTP |
| **Python** | PythonCodeInterpreterTool | Code execution, chart generation | Jupyter kernel, MCP |

### Tool Schema Format (OpenAI Function Calling)

```json
{
  "type": "function",
  "function": {
    "name": "file_content_extraction",
    "description": "Extracts text content from PDF, TXT, CSV, HTML files. Supports pagination for large files.",
    "parameters": {
      "type": "object",
      "properties": {
        "file_url": {
          "type": "string",
          "description": "URL of the file to extract content from"
        },
        "page": {
          "type": "integer",
          "description": "Page number for pagination (1-based). Omit to get first page."
        }
      },
      "required": ["file_url"]
    }
  }
}
```

### Tool Execution Parameters

All tools receive `ToolCallParams`:

```python
@dataclass
class ToolCallParams:
    tool_call: ToolCall           # Contains function name + arguments (JSON)
    stage: Stage                  # UI visualization object
    choice: Choice                # Response streaming object
    api_key: str                  # Per-request user API key
    conversation_id: str          # For caching scoped to conversation
```

**Why `ToolCallParams`?**
- Uniform interface across all tools
- Encapsulates context needed for execution
- Enables UI visualization (stages)
- Supports conversation-scoped caching

### Stage Visualization Pattern

Tools can visualize execution in DIAL Chat UI:

```python
async def _execute(self, params: ToolCallParams) -> Message:
    stage = StageProcessor.open_stage(params.choice, "File Extraction")
    stage.append_content("## Extracting content\n")
    stage.append_content(f"File: {file_url}\n")
    
    try:
        content = await extract_file(file_url)
        stage.append_content(f"✓ Extracted {len(content)} characters\n")
        return Message(content=content)
    finally:
        StageProcessor.close_stage_safely(stage)
```

**Stage Features:**
- Collapsible sections in UI
- Markdown formatting support
- Code blocks for request/response display
- Attachment previews

## State Management

### Hidden Conversation State

**Problem**: Users shouldn't see raw tool call history, but agent needs full context.

**Solution**: Store complete history in `custom_content.state[TOOL_CALL_HISTORY_KEY]`

```mermaid
flowchart LR
    A[User Sees] -->|UI Display| B[Final Responses Only]
    C[Agent Sees] -->|Internal State| D[Full Conversation]
    
    D --> E[User Messages]
    D --> F[Assistant Messages<br/>with tool_calls]
    D --> G[Tool Result Messages]
    D --> H[Assistant Responses]
    
    B -.Hidden From UI.-> F
    B -.Hidden From UI.-> G
```

**State Structure:**

```python
state = {
    "tool_call_history": [
        # User message
        {"role": "user", "content": "Extract this file", "attachments": [...]},
        
        # Assistant with tool call (hidden from UI)
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_123", "function": {"name": "file_extraction", "arguments": "..."}}
        ]},
        
        # Tool result (hidden from UI)
        {"role": "tool", "content": "Extracted content...", "tool_call_id": "call_123"},
        
        # Final assistant response (visible in UI)
        {"role": "assistant", "content": "Based on the file..."}
    ]
}
```

**Security Implications:**
- System prompt never visible to user (injected per-request)
- Tool call internals hidden (prevents prompt injection via tool results)
- Per-request key forwarding (user's credentials, not shared pool)

### Document Cache (RAG)

**DocumentCache** (`task/tools/rag/document_cache.py`):
- TTL: 24 hours
- Key format: `{conversation_id}_{file_url}`
- Stores FAISS index + metadata
- Thread-safe (asyncio locks)

```mermaid
stateDiagram-v2
    [*] --> CheckCache: User attaches file
    CheckCache --> IndexDocument: Cache miss
    CheckCache --> LoadIndex: Cache hit
    IndexDocument --> StoreCache: Embedding complete
    StoreCache --> Search: Ready
    LoadIndex --> Search: Ready
    Search --> [*]: Return results
    
    note right of StoreCache
        Key: conversation_id + file_url
        Value: FAISS index + metadata
        TTL: 24 hours
    end note
```

**Why Conversation-Scoped?**
- Different users may upload same file with different context
- Privacy: user A's indexed documents not accessible to user B
- Memory efficiency: automatic cleanup after 24h

## Error Handling

### Multi-Layer Error Strategy

```mermaid
flowchart TD
    A[Error Occurs] --> B{Where?}
    
    B -->|Tool Execution| C[BaseTool.execute]
    C --> C1[Catch Exception]
    C1 --> C2[Return Message with Error]
    C2 --> C3[LLM Sees Error]
    C3 --> C4[LLM Tries Alternative]
    
    B -->|MCP Server| D[MCPClient]
    D --> D1[Connection Timeout]
    D1 --> D2[Return Error Response]
    D2 --> C2
    
    B -->|LLM API Call| E[AsyncDial Client]
    E --> E1[Retry Logic Built-in]
    E1 --> E2[Exponential Backoff]
    E2 --> E3{Max Retries?}
    E3 -->|Yes| E4[Raise Exception]
    E3 -->|No| E5[Retry]
    E4 --> F[Agent Returns Error to User]
    
    B -->|File Extraction| G[Extract Text Failure]
    G --> G1[Return Empty Content]
    G1 --> C2
    
    style C2 fill:#ffcccc
    style C4 fill:#ccffcc
```

### Error Recovery Patterns

**1. Tool Error → LLM Decision**
```
User: "What's in this corrupted PDF?"
Agent → Tool: file_extraction(corrupted.pdf)
Tool → Agent: "Error: Unable to parse PDF"
Agent → LLM: (sees error in tool result)
LLM → Agent: "I encountered an error reading the PDF. It may be corrupted..."
```

**2. MCP Server Unavailable → Graceful Degradation**
```python
try:
    mcp_tools = await self._get_mcp_tools("http://localhost:8051")
except Exception as e:
    print(f"⚠️ MCP server unavailable: {e}")
    mcp_tools = []  # Continue without web search
```

**3. Pagination Error → Stop Gracefully**
```python
if page > total_pages:
    return Message(content="Error: Page number exceeds total pages")
```

### Stage Error Handling

```python
stage = StageProcessor.open_stage(choice, tool_name)
try:
    # Tool execution
    result = await complex_operation()
    stage.append_content(f"✓ Success: {result}\n")
except Exception as e:
    stage.append_content(f"✗ Error: {e}\n")
finally:
    StageProcessor.close_stage_safely(stage)  # Always close
```

## Security Model

### Per-Request API Key Forwarding

```mermaid
sequenceDiagram
    participant User
    participant DIAL Core
    participant Agent
    participant LLM Upstream

    User->>DIAL Core: Request + User's API Key
    Note over DIAL Core: config.json:<br/>forwardAuthToken: true
    DIAL Core->>Agent: Forward header:<br/>authorization: user_key
    Agent->>Agent: Extract from headers
    Agent->>LLM Upstream: Request with user_key
    
    Note over User,LLM Upstream: User's own quota consumed<br/>Not shared pool
```

**Configuration** (`core/config.json`):
```json
{
  "applications": {
    "general-purpose-agent": {
      "forwardAuthToken": true  // Critical for security
    }
  }
}
```

**Benefits:**
- No shared API key pool (quota abuse prevention)
- User accountability (track usage per user)
- Rate limiting per user (not per agent)

### System Prompt Injection

**Problem**: If system prompt is in conversation history, users could see/manipulate it.

**Solution**: Inject on every request at position 0

```python
def _prepare_messages(self, messages):
    unpacked = unpack_messages(messages, self.state[TOOL_CALL_HISTORY_KEY])
    return [{"role": "system", "content": self.system_prompt}] + unpacked
```

**Security Properties:**
- System prompt never in client-side state
- Cannot be overridden by user messages
- Consistent across all requests

### Input Validation

**File URLs** - validated in DIAL Core (only authorized file storage URLs)
**Tool Arguments** - JSON schema validation by LLM (pydantic models)
**MCP Responses** - validated against protocol specification

## Performance Considerations

### Async Execution Patterns

**Parallel Tool Execution:**
```python
# Execute multiple tools simultaneously
tool_messages = await asyncio.gather(*[
    self._process_tool_call(tool_call, ...) for tool_call in tool_calls
])
```

**Performance Gains:**
- File extraction + web search in parallel
- Multiple web searches concurrently
- Independent tool calls don't block each other

### Caching Strategy

| Layer | Cache | TTL | Purpose |
|-------|-------|-----|---------|
| **Tools** | In-memory list | Application lifetime | Avoid re-initialization |
| **Documents** | DocumentCache | 24 hours | Reuse FAISS indexes |
| **DIAL Core** | Redis | Configurable | Rate limiting, session |

### Streaming Optimization

**Incremental Response:**
```python
async for chunk in llm_stream:
    if chunk.delta.content:
        choice.append_content(chunk.delta.content)  # Real-time to UI
```

**Benefits:**
- User sees response immediately (not waiting for complete response)
- Better perceived performance
- Can stop generation early if needed

### Memory Management

**Large File Handling:**
- Pagination: 10KB chunks (not loading entire file)
- RAG chunking: 500 chars with 50 char overlap
- FAISS CPU-optimized (no GPU required)

**MCP Connection Pooling:**
```python
async with MCPClient.create(url) as client:
    # Connection reused for multiple tool calls
    result1 = await client.call_tool("tool1", args1)
    result2 = await client.call_tool("tool2", args2)
# Auto-cleanup on exit
```

## Design Decisions

See [Architecture Decision Records](./adr/) for detailed rationale:

- [ADR-001: Agent-as-Orchestrator Pattern](./adr/ADR-001-agent-orchestrator-pattern.md)
- [ADR-002: MCP for External Tools](./adr/ADR-002-mcp-external-tools.md)
- [ADR-003: Hidden State Management](./adr/ADR-003-hidden-state-management.md)
- [ADR-004: Async-First Architecture](./adr/ADR-004-async-first-architecture.md)
- [ADR-005: Template Method for Tools](./adr/ADR-005-template-method-tools.md)

### Key Trade-offs

**Recursive vs. Loop-Based Orchestration**
- ✅ Chosen: Recursive (cleaner state management, natural async flow)
- ❌ Alternative: While loop (more imperative, harder to reason about)

**Streaming vs. Batch Tool Execution**
- ✅ Chosen: Streaming (better UX, real-time feedback)
- ❌ Alternative: Batch (simpler implementation, worse UX)

**MCP HTTP vs. WebSocket**
- ✅ Chosen: HTTP (stateless, simpler deployment, better for serverless)
- ❌ Alternative: WebSocket (lower latency, but more complex)

**FAISS vs. Vector Database**
- ✅ Chosen: FAISS in-memory (no external dependency, fast for small datasets)
- ❌ Alternative: Pinecone/Weaviate (better for large-scale, but adds complexity)

---

**Next Steps:**
- [API Reference](./api.md) - Detailed class/method documentation
- [Setup Guide](./setup.md) - Infrastructure and deployment
- [Testing Guide](./testing.md) - Validation scenarios
