---
title: Glossary
description: Domain terms, abbreviations, and technical concepts used throughout the project
version: 1.0.0
last_updated: 2025-12-30
related: [README.md, architecture.md]
tags: [glossary, terminology, definitions]
---

# Glossary

Comprehensive terminology reference for the DIAL General Purpose Agent project.

## Table of Contents

- [Agent & AI Concepts](#agent--ai-concepts)
- [DIAL Platform](#dial-platform)
- [Tools & Integration](#tools--integration)
- [Technical Concepts](#technical-concepts)
- [Acronyms & Abbreviations](#acronyms--abbreviations)

---

## Agent & AI Concepts

### Agent
An AI system that autonomously decides which actions (tool calls) to take to accomplish user goals. In this project, the agent uses an LLM (GPT-4o/Claude) as its decision-making engine.

### Agent-as-Orchestrator
Architectural pattern where an LLM coordinates tool execution based on user requests. The LLM receives tool schemas, decides which tools to call, and synthesizes results into final responses.

### Agentic AI
AI systems that exhibit goal-directed behavior, make autonomous decisions, and can use tools to accomplish complex, multi-step tasks.

### Function Calling
OpenAI API feature allowing LLMs to output structured tool calls in JSON format. The LLM analyzes user requests and tool schemas to determine appropriate function calls with arguments.

### LLM (Large Language Model)
Neural network trained on massive text datasets (GPT-4o, Claude, etc.). Used in this project as the orchestration engine for decision-making.

### Orchestrator
Component responsible for coordinating multiple tools to accomplish user tasks. In this project, the LLM acts as the orchestrator.

### System Prompt
Initial instructions provided to the LLM that define its behavior, capabilities, and guidelines. Injected per-request and hidden from users for security.

### Tool
External capability (file extraction, web search, code execution, etc.) that the agent can invoke to accomplish tasks beyond the LLM's native abilities.

---

## DIAL Platform

### DIAL (AI Unified API Gateway)
EPAM's platform for unified access to multiple AI models and services. Provides consistent API, routing, authentication, and conversation management.

### DIAL Core
Central API gateway component of DIAL Platform. Routes requests to appropriate deployments (models/agents), manages authentication, and handles file storage.

**Port**: 8080  
**Role**: API Gateway

### DIAL Chat
Web-based user interface for interacting with DIAL deployments. Provides chat interface, file uploads, marketplace, and conversation history.

**Port**: 3000  
**Role**: Web UI

### DIAL SDK
Python library (`aidial-sdk`) for building DIAL-compatible applications. Provides `ChatCompletion` abstract class, message handling, and streaming utilities.

### Deployment
In DIAL terminology, any AI service (model or application) accessible via the platform. Examples: `gpt-4o` (model), `general-purpose-agent` (application).

### Marketplace
UI section in DIAL Chat showing available deployments. Users select deployments to start conversations.

### Upstream
External API that DIAL Core routes requests to. Example: EPAM AI Proxy endpoints for GPT-4o, DALL-E-3, Claude.

### Adapter
Component that translates between DIAL protocol and upstream provider protocols (OpenAI, Anthropic, etc.).

**Service**: `adapter-dial`

---

## Tools & Integration

### BaseTool
Abstract base class for all tools in this project. Uses template method pattern: public `execute()` wraps protected `_execute()` with error handling.

### MCP (Model Context Protocol)
Protocol for exposing external tools to AI systems. Enables stateless, HTTP-based tool servers that can be dynamically discovered and invoked.

**Specification**: https://github.com/modelcontextprotocol/specification

### MCP Server
External service implementing MCP protocol. Exposes tools via HTTP endpoints (`/tools` for discovery, `/call_tool` for execution).

**Examples**:
- DuckDuckGo Search (port 8051)
- Python Interpreter (port 8050)

### MCP Client
Component that connects to MCP servers, discovers tools, and executes tool calls. In this project: `MCPClient` class.

### MCPTool
Adapter class that wraps MCP server tools as `BaseTool` instances, enabling uniform interface for agent orchestration.

### Tool Schema
JSON Schema definition of a tool's name, description, and parameters. Sent to LLM for function calling decisions.

**Format**: OpenAI function calling schema

### Stage
UI visualization component in DIAL Chat. Tools can create stages to show execution progress, request/response details, and intermediate results.

### Streaming
Real-time transmission of response chunks as they're generated (not waiting for complete response). Improves perceived performance.

---

## Technical Concepts

### RAG (Retrieval Augmented Generation)
Pattern combining semantic search with text generation:
1. Index documents → vector embeddings
2. Query → retrieve relevant chunks
3. Augment LLM prompt with retrieved context
4. Generate answer based on context

**Used for**: Semantic document search in large files

### FAISS (Facebook AI Similarity Search)
Library for efficient similarity search in high-dimensional vector spaces. Used for RAG to find relevant document chunks.

**Type**: CPU-based (no GPU required)  
**Index**: L2 distance (Euclidean)

### Embeddings
Vector representations of text that capture semantic meaning. Similar texts have similar embeddings (measured by distance metrics).

**Model**: `all-MiniLM-L6-v2` (384 dimensions)  
**Library**: SentenceTransformers

### Vector Index
Data structure optimized for similarity search in embedding space. Maps vectors to documents for fast retrieval.

**Implementation**: FAISS IndexFlatL2

### Chunking
Splitting documents into smaller segments (chunks) for better retrieval granularity in RAG systems.

**Settings**: 500 chars, 50 char overlap

### Pagination
Breaking large content into pages for incremental delivery. File extraction uses 10KB pages to avoid overwhelming context.

**Footer Format**: `**Page #X. Total pages: Y**`

### Async/Await
Python concurrency pattern for I/O-bound operations. All tool execution, MCP calls, and LLM requests use async.

### Context Manager
Python pattern (`with` statement) for resource management. MCP clients use async context managers for connection lifecycle.

### Template Method Pattern
Design pattern where base class defines algorithm structure, subclasses implement specific steps. Used in `BaseTool`.

### Recursive Streaming
Pattern where agent makes LLM call → processes tool calls → appends results → makes another LLM call (repeats until no tool calls).

---

## RAG-Specific Terms

### Document Cache
Conversation-scoped storage for indexed documents (FAISS indexes + chunks). Prevents re-indexing within same conversation.

**TTL**: 24 hours  
**Key Format**: `{conversation_id}_{file_url}`

### Top-K Retrieval
Retrieving K most similar chunks from vector index. This project uses K=3.

### Semantic Search
Search based on meaning rather than exact keyword matching. Uses embeddings to find conceptually similar content.

### Text Splitter
Component that divides documents into chunks. Uses recursive strategy with configurable separators.

**Library**: LangChain `RecursiveCharacterTextSplitter`

---

## File Processing

### File URL
DIAL-specific URL format for files in storage. Format: `files/{file_id}.{extension}`

### Attachment
File associated with a message. Sent as part of `custom_content.attachments` array with `type` and `url`.

### Content Extraction
Process of extracting text from various file formats (PDF, CSV, HTML, TXT).

**Library Used**:
- PDF: pdfplumber
- HTML: BeautifulSoup
- CSV: pandas

---

## Acronyms & Abbreviations

| Acronym | Full Form | Description |
|---------|-----------|-------------|
| **ADR** | Architecture Decision Record | Documentation of architectural decisions with rationale |
| **API** | Application Programming Interface | Interface for software communication |
| **ASGI** | Asynchronous Server Gateway Interface | Python async server standard (used by uvicorn) |
| **CLI** | Command Line Interface | Text-based interface for programs |
| **CPU** | Central Processing Unit | Main processor (vs GPU for compute) |
| **CSV** | Comma-Separated Values | Tabular data format |
| **DIAL** | AI Unified API Gateway | EPAM's AI platform |
| **FAISS** | Facebook AI Similarity Search | Vector similarity library |
| **GPU** | Graphics Processing Unit | Parallel processor (optional for AI) |
| **HTML** | HyperText Markup Language | Web page format |
| **HTTP** | HyperText Transfer Protocol | Web communication protocol |
| **JSON** | JavaScript Object Notation | Data interchange format |
| **JWT** | JSON Web Token | Authentication token standard |
| **K8s** | Kubernetes | Container orchestration (not used in this project) |
| **LLM** | Large Language Model | AI text generation model |
| **MCP** | Model Context Protocol | Tool integration protocol |
| **OCR** | Optical Character Recognition | Image-to-text (not used in this project) |
| **PDF** | Portable Document Format | Document file format |
| **QA** | Quality Assurance | Testing and validation |
| **RAG** | Retrieval Augmented Generation | Search + generation pattern |
| **REST** | Representational State Transfer | API architectural style |
| **SDK** | Software Development Kit | Library for development |
| **SSE** | Server-Sent Events | HTTP streaming protocol |
| **TXT** | Plain Text | Unformatted text file |
| **UI** | User Interface | Visual interaction layer |
| **URL** | Uniform Resource Locator | Web address |
| **UUID** | Universally Unique Identifier | Unique ID generation |

---

## Platform-Specific Terms

### EPAM AI Proxy
EPAM's internal API gateway for accessing multiple LLM providers (OpenAI, Anthropic, etc.) with unified authentication.

**URL**: `https://ai-proxy.lab.epam.com`

### Per-Request API Key
Security pattern where each user's API key is forwarded per-request (not shared pool). Enabled via `forwardAuthToken: true` in config.

### Conversation ID
Unique identifier for a conversation session. Used for:
- Caching scoped to conversation
- Stateful tool execution (Python interpreter)
- Conversation history management

### Custom Content
DIAL-specific message field for attachments, state, and metadata not in standard OpenAI message format.

**Fields**:
- `attachments[]`: File references
- `state{}`: Hidden conversation state

### Tool Call History
Hidden conversation state containing full assistant messages with tool calls and tool result messages. Stored in `custom_content.state[TOOL_CALL_HISTORY_KEY]`.

---

## Development Terms

### Virtual Environment
Isolated Python environment with specific package versions. Located at `dial_general_agent/`.

### Lazy Initialization
Pattern where resources are created on first use (not at startup). Tools are lazy-initialized in this project.

### Graceful Degradation
System continues operating with reduced functionality when components fail. Example: Agent works without MCP tools if servers unavailable.

### Health Check
Endpoint that returns system status. Used for monitoring and load balancer probing.

**Endpoints**:
- Core: `http://localhost:8080/health`
- Agent: `http://localhost:5030/health`
- MCP Servers: `http://localhost:8050/health`, `http://localhost:8051/health`

### Docker Compose
Tool for defining and running multi-container Docker applications. Uses `docker-compose.yml` configuration.

### Container
Lightweight, standalone executable package including code, runtime, libraries. Docker containers used for DIAL infrastructure.

---

## Error Handling Terms

### Fail-Safe
Design principle where failures don't cascade. Tool errors return as messages (not exceptions), allowing agent to continue.

### Error Message
Message with `role=TOOL` containing error description instead of successful result. LLM can reason about errors and retry.

### Stage Error
Exception during stage lifecycle (open/close). Handled gracefully with `close_stage_safely()`.

### Connection Timeout
Failure to connect to external service within time limit. Handled by async timeout decorators.

---

## Performance Terms

### Cache Hit
Successful retrieval from cache (document already indexed). Much faster than cache miss.

### Cache Miss
Item not found in cache, requires computation (document indexing). Slower than cache hit.

### TTL (Time To Live)
Duration cached items remain valid before expiration. Document cache uses 24h TTL.

### Concurrent Execution
Multiple operations running simultaneously. Tools executed in parallel with `asyncio.gather()`.

### Memory Leak
Gradual memory consumption increase due to unreleased resources. Prevented by proper cleanup in context managers.

---

## Security Terms

### API Key
Authentication credential for accessing LLM APIs. Per-user keys forwarded from DIAL Core to agent.

### Authorization Header
HTTP header containing API key: `Authorization: Bearer <key>`

### Token Forwarding
Passing authentication token from client → gateway → service. Critical for per-user quota tracking.

### Prompt Injection
Attack where malicious input manipulates LLM behavior. Mitigated by hiding system prompt from users.

### Secret Management
Secure storage of API keys and credentials. Should use environment variables, not hardcoded in config files.

---

**Related Documentation:**
- [Architecture](./architecture.md) - See these terms in context
- [API Reference](./api.md) - Technical class/method details
- [Setup Guide](./setup.md) - Configuration and deployment
