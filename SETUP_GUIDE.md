# General Purpose Agent - Setup & Testing Guide

## Overview
This guide walks you through setting up and testing the General Purpose Agent built on the DIAL Platform. The agent includes:
- 🔍 **Web Search** (DuckDuckGo via MCP)
- 📄 **File Content Extraction** (PDF, TXT, CSV, HTML with pagination)
- 🧠 **RAG Search** (Semantic search with FAISS + LLM generation)
- 🎨 **Image Generation** (DALL-E-3)
- 🐍 **Python Code Interpreter** (Execute code, generate charts)

## Prerequisites

### System Requirements
- Python 3.12 (required for PyTorch compatibility)
- Docker & Docker Compose
- 4GB+ RAM available for containers

### API Access
- EPAM AI Proxy API key (for GPT-4o, DALL-E-3, Claude)
- Access to `https://ai-proxy.lab.epam.com`

## Step 1: Environment Setup

### 1.1 Activate Virtual Environment
```bash
cd /path/to/ai-dial-general-purpose-agent
source dial_general_agent/bin/activate
```

### 1.2 Verify Dependencies
All dependencies should already be installed. Verify:
```bash
pip list | grep -E "aidial|faiss|sentence-transformers|mcp"
```

Expected output should include:
- `aidial-sdk==0.27.0`
- `aidial-client==0.3.0`
- `faiss-cpu>=1.12.0`
- `sentence-transformers==5.1.1`
- `mcp==1.17.0`

### 1.3 Set API Key
**Important:** Set your DIAL API key as an environment variable:
```bash
export DIAL_API_KEY="your-epam-ai-proxy-api-key-here"
```

To persist across sessions, add to `~/.zshrc`:
```bash
echo 'export DIAL_API_KEY="your-api-key"' >> ~/.zshrc
source ~/.zshrc
```

## Step 2: Start Infrastructure

### 2.1 Start Docker Services
```bash
docker-compose up -d
```

This starts:
- **core** (port 8080): DIAL Core API gateway
- **chat** (port 3000): DIAL Chat web UI
- **themes** (port 3001): UI theming service
- **redis** (port 6379): Caching layer
- **ddg-search** (port 8051): DuckDuckGo MCP server
- **python-interpreter** (port 8050): Python execution MCP server
- **adapter-dial**: DIAL protocol adapter

### 2.2 Verify Containers
```bash
docker-compose ps
```

All services should show "Up" status.

### 2.3 Check MCP Servers
```bash
# Test DuckDuckGo search server
curl http://localhost:8051/health

# Test Python interpreter server
curl http://localhost:8050/health
```

## Step 3: Start the Agent

### 3.1 Run Agent Application
```bash
python -m task.app
```

Expected output:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5030
```

### 3.2 Verify Agent Endpoint
Open new terminal:
```bash
curl http://localhost:5030/health
```

## Step 4: Access DIAL Chat

### 4.1 Open Web UI
Navigate to: **http://localhost:3000**

### 4.2 Verify Marketplace
1. Click **Marketplace** icon (grid icon in left sidebar)
2. Verify visible deployments:
   - ✅ **General Purpose Agent**
   - ✅ **GPT 4o**
   - ✅ **DALL-E-3**
   - ✅ **Claude Sonnet 3.7** (if configured)

### 4.3 Select Agent
1. Click on **General Purpose Agent** in marketplace
2. Should appear in chat interface with agent icon

## Step 5: Testing Scenarios

### Test 1: Agent Capabilities
**Query:** "What can you do?"

**Expected Response:**
Agent should describe available tools:
- File content extraction
- RAG search for documents
- Web search via DuckDuckGo
- Python code execution
- Image generation

### Test 2: File Content Extraction
**Steps:**
1. Click attachment icon (📎)
2. Upload `tests/report.csv`
3. **Query:** "What is top sale for category A?"

**Expected Result:**
- Agent calls `file_content_extraction` tool
- Extracts CSV content
- Returns: "1700 on 2025-10-05"

### Test 3: Pagination
**Steps:**
1. Upload `tests/microwave_manual.txt`
2. **Query:** "How should I clean the plate?"

**Expected Result:**
- Agent makes 2-3 tool calls (pagination with "Page #X. Total pages: Y")
- Extracts content progressively
- Provides cleaning instructions from manual

### Test 4: RAG Search
**Steps:**
1. Upload `tests/microwave_manual.txt`
2. **Query:** "How should I clean the plate? Use semantic search."

**Expected Result:**
- Agent calls `rag_search` tool (not file extraction)
- Indexes document with FAISS
- Returns top-3 relevant chunks
- Generates answer based on context

**Stage Indicators:**
- "## Indexing document"
- "## Searching for relevant content"
- "## Generating response"

### Test 5: Image Generation
**Query:** "Generate a picture of a smiling cat"

**Expected Result:**
- Agent calls `image_generation` tool
- Displays request parameters in stage
- Shows revised prompt from DALL-E-3
- Image appears in both stage and chat message
- Image markdown: `![Generated Image](files/...)`

### Test 6: Web Search
**Query:** "What is the weather in Kyiv right now?"

**Expected Result:**
- Agent calls `duckduckgo_web_search` MCP tool
- Fetches current weather data
- Provides weather summary with temperature

### Test 7: Python Code Execution
**Query:** "What is the sin of 5682936329203?"

**Expected Result:**
- Agent calls `execute_code` tool
- Python code in stage: `import math; math.sin(5682936329203)`
- Returns numerical result

### Test 8: Multi-Step Workflow
**Steps:**
1. Upload `tests/report.csv`
2. **Query:** "Create a bar chart from this data"

**Expected Result:**
- Agent extracts CSV content (tool 1)
- Generates Python code to create chart (tool 2)
- Executes code, generates PNG file (tool 2 continued)
- Uploads image to DIAL bucket
- Shows chart in chat as attachment

**Stage Flow:**
```
## file_content_extraction
[CSV content displayed]

## execute_code
Request arguments:
```python
import matplotlib.pyplot as plt
import pandas as pd
# ... chart generation code ...
```
Execution result:
{
  "success": true,
  "files": [{"name": "chart.png", ...}]
}
```

## Step 6: Advanced Testing

### Test Claude Model
1. In DIAL Chat, click model selector
2. Switch from "General Purpose Agent" to **GPT 4o** (test base model)
3. **Query:** "Hi, what can you do?"
4. Switch to **Claude Sonnet 3.7**
5. Same query - verify response

### Test Tool Combinations
**Query:** "Search for information about Python matplotlib, then generate sample code and execute it to create a sine wave plot"

**Expected Flow:**
1. Web search for matplotlib info
2. Generate Python code
3. Execute code
4. Return plot as attachment

### Test Error Handling
**Query:** Upload corrupted file, ask "What's in this file?"

**Expected:** Agent handles error gracefully, returns error message in tool response

## Step 7: Monitoring & Debugging

### Check Agent Logs
Agent terminal shows:
```
Received request: conversation_id=abc123
Tool call: file_content_extraction(file_url=...)
MCP Client connected to http://ddg-search:8050
```

### Check DIAL Core Logs
```bash
docker-compose logs -f core
```

### Check MCP Server Logs
```bash
# DuckDuckGo search
docker-compose logs -f ddg-search

# Python interpreter
docker-compose logs -f python-interpreter
```

### Check Stage Debugging
In DIAL Chat:
1. Stages show tool execution details
2. Expand stage to see full tool input/output
3. Check for errors in red text

## Troubleshooting

### Issue: "Connection refused" to localhost:5030
**Solution:**
- Verify agent is running: `ps aux | grep "python -m task.app"`
- Check port: `lsof -i :5030`
- Restart agent: Kill process and run again

### Issue: "API key not found" errors
**Solution:**
```bash
# Verify environment variable
echo $DIAL_API_KEY

# Check DIAL Core sees it
docker-compose exec core env | grep DIAL_API_KEY

# Restart DIAL Core with env var
docker-compose down
export DIAL_API_KEY="your-key"
docker-compose up -d
```

### Issue: MCP tools not working
**Solution:**
```bash
# Check MCP containers
docker-compose ps | grep -E "ddg-search|python-interpreter"

# Restart MCP servers
docker-compose restart ddg-search python-interpreter

# Test connectivity from agent container
curl http://ddg-search:8050/health
```

### Issue: "Tool not found" errors
**Solution:**
- Check `task/app.py` tool initialization in `_create_tools()`
- Verify all tool imports are correct
- Check logs for initialization errors

### Issue: RAG search indexing fails
**Solution:**
- Verify sentence-transformers model downloaded: `~/.cache/torch/sentence_transformers/`
- Check memory: RAG needs ~500MB for embeddings
- Test manually:
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
```

### Issue: Image generation returns error
**Solution:**
- Verify DALL-E-3 model in `core/config.json`
- Check API key has DALL-E-3 access
- Test endpoint directly:
```bash
curl -X POST http://localhost:8080/openai/deployments/dall-e-3/chat/completions \
  -H "Api-Key: dial_api_key" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "A cat"}]}'
```

## Performance Tips

### Speed up RAG indexing
- Use smaller documents (<100 pages)
- Increase chunk size in `rag_tool.py`: change 500→1000 chars

### Reduce token costs
- Use shorter system prompts
- Enable output truncation (already configured to 1000 chars)
- Use Claude instead of GPT-4o for cheaper inference

### Scale for production
- Move Redis to persistent storage
- Configure DIAL Core rate limits in `core/config.json`
- Use load balancer for multiple agent instances
- Set up logging aggregation (ELK stack)

## Architecture Overview

```
┌─────────────────┐
│   DIAL Chat     │  User Interface (port 3000)
│  (Web Browser)  │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│   DIAL Core     │  API Gateway (port 8080)
│  (Docker)       │  - Routes requests
└────────┬────────┘  - Auth & rate limiting
         │
         ├─── GPT-4o ────────────► EPAM AI Proxy
         ├─── DALL-E-3 ──────────► EPAM AI Proxy
         ├─── Claude ────────────► EPAM AI Proxy
         │
         ▼
┌─────────────────┐
│ General Purpose │  Agent Application (port 5030)
│     Agent       │  - Orchestrates LLM + tools
│  (Python App)   │  - Streaming responses
└────────┬────────┘
         │
         ├─── file_content_extraction → DIAL Storage
         ├─── rag_search → FAISS (in-memory)
         ├─── image_generation → DALL-E-3 via DIAL
         │
         ├─── MCP Tools:
         │    ├─── DuckDuckGo Search (port 8051)
         │    └─── Python Interpreter (port 8050)
         │
         └─── Redis (cache, port 6379)
```

## Next Steps

### Production Deployment
1. **Secure API Keys:** Use secrets manager (AWS Secrets Manager, HashiCorp Vault)
2. **Persistent Storage:** Configure volumes for Redis and file storage
3. **Monitoring:** Add Prometheus metrics and Grafana dashboards
4. **Scaling:** Use Kubernetes for auto-scaling agent instances
5. **Backup:** Regular backups of conversation history and indexed documents

### Extend Functionality
1. **Add More MCP Tools:**
   - GitHub integration (code search, PR management)
   - Slack/Teams messaging
   - Database query tool (SQL execution)

2. **Enhance RAG:**
   - Support more file types (DOCX, XLSX, PPTX)
   - Use better embeddings (text-embedding-3-large)
   - Implement re-ranking for better results

3. **Multi-Agent Workflows:**
   - Specialized agents (data analyst, code reviewer)
   - Agent-to-agent communication
   - Hierarchical task decomposition

### Resources
- **DIAL Documentation:** https://dialx.ai
- **MCP Specification:** https://modelcontextprotocol.io
- **Project GitHub:** Check `.github/copilot-instructions.md` for architecture details

---

**Need Help?** Check logs, verify environment variables, and ensure all containers are running. Most issues are related to API keys or network connectivity between Docker services.
