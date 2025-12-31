---
title: Setup Guide
description: Comprehensive environment setup, configuration, and deployment instructions
version: 1.0.0
last_updated: 2025-12-30
related: [README.md, architecture.md, testing.md]
tags: [setup, installation, configuration, docker, deployment]
---

# Setup Guide

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start (5 Minutes)](#quick-start-5-minutes)
- [Detailed Setup](#detailed-setup)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)

## Prerequisites

### System Requirements

| Component | Requirement | Notes |
|-----------|-------------|-------|
| **OS** | macOS, Linux, Windows (WSL2) | Tested on macOS Ventura+ |
| **Python** | 3.12 | Required for PyTorch/FAISS compatibility |
| **Docker** | 20.10+ | For infrastructure containers |
| **Docker Compose** | 2.0+ | Multi-container orchestration |
| **RAM** | 4GB available | 2GB for containers + 2GB for agent |
| **Disk** | 2GB free | Dependencies + Docker images |

### API Access

**Required:**
- EPAM AI Proxy API key
- Access to `https://ai-proxy.lab.epam.com`

**Models Used:**
- GPT-4o (orchestrator LLM)
- DALL-E-3 (image generation)
- Claude Sonnet 3.7 (optional orchestrator)

### Verification

```bash
# Check Python version
python3 --version  # Should be 3.12.x

# Check Docker
docker --version   # Should be 20.10+
docker-compose --version  # Should be 2.0+

# Check system resources
docker system info | grep "Total Memory"  # Should be >4GB
```

---

## Quick Start (5 Minutes)

For experienced users who want to get running immediately:

```bash
# 1. Navigate to project
cd /path/to/ai-dial-general-purpose-agent

# 2. Activate virtual environment
source dial_general_agent/bin/activate

# 3. Set API key
export DIAL_API_KEY="your-epam-ai-proxy-key"

# 4. Start infrastructure
docker-compose up -d

# 5. Run agent
python -m task.app

# 6. Open browser → http://localhost:3000
# Select "General Purpose Agent" and start chatting
```

**First Test:** Ask "What can you do?"

---

## Detailed Setup

### Step 1: Environment Setup

#### 1.1 Clone/Navigate to Repository

```bash
cd /Users/Dzianis_Haurylovich/Documents/git/git.epam.com/ai-dial-general-purpose-agent
```

#### 1.2 Verify Virtual Environment

The virtual environment is pre-created at `dial_general_agent/`:

```bash
# Activate virtual environment
source dial_general_agent/bin/activate

# Verify activation (prompt should show (dial_general_agent))
which python  # Should point to dial_general_agent/bin/python
```

#### 1.3 Verify Dependencies

```bash
# Check installed packages
pip list | grep -E "aidial|faiss|sentence-transformers|mcp"
```

**Expected Output:**
```
aidial-client              0.3.0
aidial-sdk                 0.27.0
faiss-cpu                  1.12.0
mcp                        1.17.0
sentence-transformers      5.1.1
```

**If Dependencies Missing:**
```bash
pip install -r requirements.txt
```

#### 1.4 Set API Key

**Option A: Environment Variable (Session)**
```bash
export DIAL_API_KEY="your-epam-ai-proxy-key"
```

**Option B: Shell Configuration (Persistent)**
```bash
# For zsh (macOS default)
echo 'export DIAL_API_KEY="your-api-key"' >> ~/.zshrc
source ~/.zshrc

# For bash
echo 'export DIAL_API_KEY="your-api-key"' >> ~/.bashrc
source ~/.bashrc
```

**Verification:**
```bash
echo $DIAL_API_KEY  # Should print your key
```

---

### Step 2: Configure DIAL Core

#### 2.1 Understanding [core/config.json](../core/config.json)

This file defines:
- **Applications**: Agent deployments (endpoints, capabilities)
- **Models**: LLM upstreams (GPT-4o, DALL-E-3, Claude)
- **Keys**: API key management (not recommended for production)
- **Roles**: Access control (optional)

#### 2.2 Critical Configuration: General Purpose Agent

**File**: `core/config.json`

```json
{
  "applications": {
    "general-purpose-agent": {
      "displayName": "General Purpose Agent",
      "description": "General Purpose Agent. Equipped with: WEB search (DuckDuckGo via MCP), RAG search (supports PDF, TXT, CSV files), Python Code Interpreter (via MCP), Image Generation (model).",
      "endpoint": "http://host.docker.internal:5030/openai/deployments/general-purpose-agent/chat/completions",
      "iconUrl": "http://localhost:3001/gpt4.svg",
      "inputAttachmentTypes": [
        "image/png",
        "image/jpeg",
        "application/pdf",
        "text/html",
        "text/plain",
        "text/csv"
      ],
      "forwardAuthToken": true  // CRITICAL: Per-request API key
    }
  }
}
```

**Key Settings:**

| Setting | Value | Purpose |
|---------|-------|---------|
| `endpoint` | `http://host.docker.internal:5030/...` | Agent application URL |
| `inputAttachmentTypes` | File types array | Allowed upload formats |
| `forwardAuthToken` | `true` | **Security**: Forward user's API key |

#### 2.3 Model Configuration: GPT-4o

```json
{
  "models": {
    "gpt-4o": {
      "displayName": "GPT 4o",
      "endpoint": "http://adapter-dial:5000/openai/deployments/gpt-4o/chat/completions",
      "iconUrl": "http://localhost:3001/gpt4.svg",
      "type": "chat",
      "upstreams": [
        {
          "endpoint": "https://ai-proxy.lab.epam.com/openai/deployments/gpt-4o/chat/completions",
          "key": "YOUR_DIAL_API_KEY"  // ⚠️ REMOVE BEFORE COMMIT
        }
      ]
    }
  }
}
```

**⚠️ SECURITY WARNING:**
- **Never commit API keys to version control**
- Use environment variables in production
- Remove keys from `config.json` after testing

#### 2.4 Model Configuration: DALL-E-3

```json
{
  "models": {
    "dall-e-3": {
      "displayName": "DALL-E-3",
      "endpoint": "http://adapter-dial:5000/openai/deployments/dall-e-3/chat/completions",
      "iconUrl": "http://localhost:3001/gpt3.svg",
      "type": "chat",
      "upstreams": [
        {
          "endpoint": "https://ai-proxy.lab.epam.com/openai/deployments/dall-e-3/chat/completions",
          "key": "YOUR_DIAL_API_KEY"
        }
      ]
    }
  }
}
```

#### 2.5 Optional: Claude Sonnet 3.7

```json
{
  "models": {
    "claude-sonnet-3-7": {
      "displayName": "Claude Sonnet 3.7",
      "endpoint": "http://adapter-dial:5000/openai/deployments/claude-sonnet-3-7/chat/completions",
      "iconUrl": "https://chat.lab.epam.com/themes/anthropic.svg",
      "type": "chat",
      "upstreams": [
        {
          "endpoint": "https://ai-proxy.lab.epam.com/openai/deployments/claude-3-7-sonnet@20250219/chat/completions",
          "key": "YOUR_DIAL_API_KEY"
        }
      ]
    }
  }
}
```

**Switching Orchestrator LLM:**

Edit `task/app.py`:
```python
# Line ~20
# DEPLOYMENT_NAME = os.getenv('DEPLOYMENT_NAME', 'gpt-4o')  # GPT-4o
DEPLOYMENT_NAME = os.getenv('DEPLOYMENT_NAME', 'claude-sonnet-3-7')  # Claude
```

---

### Step 3: Start Infrastructure

#### 3.1 Docker Compose Services

**Services Defined:**

| Service | Port | Purpose | Image |
|---------|------|---------|-------|
| `core` | 8080 | DIAL Core API gateway | `epam/ai-dial-core:development` |
| `chat` | 3000 | DIAL Chat web UI | `epam/ai-dial-chat:development` |
| `themes` | 3001 | UI theming service | `epam/ai-dial-chat-themes:development` |
| `redis` | 6379 | Caching layer | `redis:7.2.4-alpine3.19` |
| `adapter-dial` | N/A | Protocol adapter | `epam/ai-dial-adapter-dial:development` |
| `ddg-search` | 8051 | DuckDuckGo MCP | `ghcr.io/epam/duckduckgo-mcp-server:0.3.0` |
| `python-interpreter` | 8050 | Python MCP | `ghcr.io/epam/python-mcp-server:0.3.0` |

#### 3.2 Start Services

```bash
# Start all services in detached mode
docker-compose up -d
```

**Expected Output:**
```
Creating network "ai-dial-general-purpose-agent_default" with the default driver
Creating ai-dial-general-purpose-agent_redis_1 ... done
Creating ai-dial-general-purpose-agent_themes_1 ... done
Creating ai-dial-general-purpose-agent_ddg-search_1 ... done
Creating ai-dial-general-purpose-agent_python-interpreter_1 ... done
Creating ai-dial-general-purpose-agent_adapter-dial_1 ... done
Creating ai-dial-general-purpose-agent_core_1 ... done
Creating ai-dial-general-purpose-agent_chat_1 ... done
```

#### 3.3 Verify Services

```bash
# Check all services are running
docker-compose ps
```

**Expected Output:**
```
NAME                    STATUS      PORTS
core                    Up          0.0.0.0:8080->8080/tcp
chat                    Up          0.0.0.0:3000->3000/tcp
themes                  Up          0.0.0.0:3001->8080/tcp
redis                   Up          0.0.0.0:6379->6379/tcp
ddg-search              Up          0.0.0.0:8051->8050/tcp
python-interpreter      Up          0.0.0.0:8050->8050/tcp
adapter-dial            Up
```

**All services should show "Up" status.**

#### 3.4 Verify Endpoints

```bash
# Test DIAL Core
curl -s http://localhost:8080/health | head -5

# Test DuckDuckGo MCP
curl -s http://localhost:8051/health

# Test Python Interpreter MCP
curl -s http://localhost:8050/health
```

---

### Step 4: Run Agent Application

#### 4.1 Start Agent

```bash
# Ensure virtual environment is active
source dial_general_agent/bin/activate

# Run agent
python -m task.app
```

**Expected Output:**
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5030 (Press CTRL+C to quit)
```

#### 4.2 Verify Agent Endpoint

**Open new terminal:**
```bash
curl -s http://localhost:5030/health
```

**Expected Response:**
```json
{"status": "ok"}
```

#### 4.3 Agent Logs

Monitor agent logs in the terminal where `python -m task.app` is running.

**Key Log Patterns:**
```
INFO:     127.0.0.1:xxxxx - "POST /openai/deployments/general-purpose-agent/chat/completions HTTP/1.1" 200 OK
```

---

### Step 5: Access DIAL Chat UI

#### 5.1 Open Browser

Navigate to: **http://localhost:3000**

#### 5.2 Verify Marketplace

1. Click **Marketplace** icon (grid icon in left sidebar)
2. Verify visible deployments:
   - ✅ General Purpose Agent
   - ✅ GPT 4o
   - ✅ DALL-E-3
   - ✅ Claude Sonnet 3.7 (if configured)

#### 5.3 Select Agent

1. Click **"General Purpose Agent"** card
2. Should appear in chat interface
3. Ready to receive messages

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DIAL_ENDPOINT` | `http://localhost:8080` | DIAL Core endpoint |
| `DEPLOYMENT_NAME` | `gpt-4o` | Orchestrator LLM model |
| `DIAL_API_KEY` | (none) | EPAM AI Proxy API key |

**Setting in Shell:**
```bash
export DIAL_ENDPOINT="http://localhost:8080"
export DEPLOYMENT_NAME="claude-sonnet-3-7"
export DIAL_API_KEY="your-api-key"
```

**Setting for Docker Compose:**

Edit `docker-compose.yml`:
```yaml
services:
  core:
    environment:
      DIAL_API_KEY: ${DIAL_API_KEY}  # From shell
```

### Customizing System Prompt

**File**: `task/prompts.py`

Edit `SYSTEM_PROMPT` constant:
```python
SYSTEM_PROMPT = """
You are a General Purpose Agent with access to specialized tools.

[Your custom instructions here]

## Available Tools
1. **File Content Extraction** - ...
...
"""
```

**Restart agent** for changes to take effect.

### Adding Custom Tools

**Step 1: Create Tool Class**

Create `task/tools/my_tool.py`:
```python
from task.tools.base import BaseTool

class MyCustomTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_custom_tool"
    
    # ... implement required methods
```

**Step 2: Register in Application**

Edit `task/app.py`:
```python
from task.tools.my_tool import MyCustomTool

async def _create_tools(self):
    tools = [
        MyCustomTool(),  # Add here
        ImageGenerationTool(...),
        # ... other tools
    ]
    return tools
```

**Step 3: Restart Agent**

---

## Deployment

### Production Considerations

**Security:**
- [ ] Remove API keys from `core/config.json`
- [ ] Use environment variables for secrets
- [ ] Enable HTTPS for all endpoints
- [ ] Implement rate limiting
- [ ] Add authentication middleware

**Scalability:**
- [ ] Use external Redis (not Docker container)
- [ ] Scale agent horizontally (load balancer)
- [ ] Use persistent storage for document cache
- [ ] Monitor resource usage (CPU, memory, GPU)

**Reliability:**
- [ ] Add health check endpoints
- [ ] Implement retry logic for LLM calls
- [ ] Set timeouts for tool execution
- [ ] Log structured errors (JSON format)
- [ ] Set up alerting (Prometheus/Grafana)

### Docker Deployment

**Build Custom Agent Image:**

Create `Dockerfile`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY task/ ./task/

# Run agent
CMD ["python", "-m", "task.app"]
```

**Build and Run:**
```bash
docker build -t general-purpose-agent:latest .
docker run -p 5030:5030 \
  -e DIAL_ENDPOINT=http://core:8080 \
  -e DIAL_API_KEY=$DIAL_API_KEY \
  general-purpose-agent:latest
```

**Add to docker-compose.yml:**
```yaml
services:
  agent:
    build: .
    ports:
      - "5030:5030"
    environment:
      DIAL_ENDPOINT: http://core:8080
      DIAL_API_KEY: ${DIAL_API_KEY}
    depends_on:
      - core
```

---

## Troubleshooting

### Common Issues

#### Issue: Agent Not Starting

**Symptoms:**
- `python -m task.app` fails
- Import errors

**Solutions:**
```bash
# Verify virtual environment
source dial_general_agent/bin/activate
which python  # Should show dial_general_agent/bin/python

# Reinstall dependencies
pip install -r requirements.txt

# Check Python version
python --version  # Must be 3.12.x
```

#### Issue: Docker Services Not Starting

**Symptoms:**
- `docker-compose ps` shows "Exit" or "Restarting"

**Solutions:**
```bash
# View logs
docker-compose logs <service_name>

# Common fixes
docker-compose down    # Stop all
docker-compose up -d   # Restart

# Check ports not in use
lsof -i :8080  # DIAL Core
lsof -i :3000  # Chat UI
lsof -i :5030  # Agent
```

#### Issue: DIAL Core Returns 401

**Symptoms:**
- Chat UI shows "Unauthorized"
- Logs show 401 errors

**Solutions:**
```bash
# Verify API key is set
echo $DIAL_API_KEY

# Check config.json has correct key
cat core/config.json | grep -A 2 "key"

# Ensure forwardAuthToken is true
cat core/config.json | grep forwardAuthToken
```

#### Issue: MCP Tools Not Available

**Symptoms:**
- Agent doesn't list web search or code execution
- "MCP server unavailable" errors

**Solutions:**
```bash
# Check MCP containers
docker-compose ps ddg-search python-interpreter

# Test MCP endpoints
curl http://localhost:8051/health
curl http://localhost:8050/health

# View MCP logs
docker-compose logs ddg-search
docker-compose logs python-interpreter

# Restart MCP services
docker-compose restart ddg-search python-interpreter
```

#### Issue: File Upload Not Working

**Symptoms:**
- File uploads fail
- "Unsupported file type" errors

**Solutions:**
```bash
# Check inputAttachmentTypes in config.json
cat core/config.json | jq '.applications["general-purpose-agent"].inputAttachmentTypes'

# Verify file type is supported
# Supported: image/png, image/jpeg, application/pdf, text/html, text/plain, text/csv

# Check file size limits (default: 10MB)
```

#### Issue: RAG Search Fails

**Symptoms:**
- "Error indexing document" messages
- FAISS import errors

**Solutions:**
```bash
# Verify FAISS installation
python -c "import faiss; print(faiss.__version__)"

# Reinstall if needed
pip uninstall faiss-cpu
pip install faiss-cpu>=1.12.0

# Check SentenceTransformer model
python -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('all-MiniLM-L6-v2')"
```

### Debug Mode

**Enable Verbose Logging:**

Edit `task/app.py`:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**View All Logs:**
```bash
# Agent logs
python -m task.app 2>&1 | tee agent.log

# Docker logs (all services)
docker-compose logs -f

# Docker logs (specific service)
docker-compose logs -f core
docker-compose logs -f ddg-search
```

### Health Check Commands

```bash
# Complete health check script
#!/bin/bash

echo "=== Checking DIAL Core ==="
curl -s http://localhost:8080/health && echo "✓ Core OK" || echo "✗ Core FAIL"

echo "=== Checking Chat UI ==="
curl -s http://localhost:3000 > /dev/null && echo "✓ Chat OK" || echo "✗ Chat FAIL"

echo "=== Checking Agent ==="
curl -s http://localhost:5030/health && echo "✓ Agent OK" || echo "✗ Agent FAIL"

echo "=== Checking MCP Servers ==="
curl -s http://localhost:8051/health && echo "✓ DuckDuckGo OK" || echo "✗ DuckDuckGo FAIL"
curl -s http://localhost:8050/health && echo "✓ Python OK" || echo "✗ Python FAIL"

echo "=== Checking Docker Services ==="
docker-compose ps
```

---

## Advanced Configuration

### Custom MCP Servers

**Add New MCP Server:**

1. **Add to docker-compose.yml:**
```yaml
services:
  my-mcp-server:
    image: my-mcp-server:latest
    ports:
      - "8052:8000"
    environment:
      LOG_LEVEL: "INFO"
```

2. **Register in app.py:**
```python
# In _create_tools()
mcp_tools = await self._get_mcp_tools("http://localhost:8052/mcp")
tools.extend(mcp_tools)
```

### Redis Configuration

**External Redis:**

Edit `docker-compose.yml`:
```yaml
services:
  core:
    environment:
      aidial.redis.singleServerConfig.address: 'redis://your-redis-host:6379'
      aidial.redis.singleServerConfig.password: 'your-redis-password'
```

### Resource Limits

**Docker Service Limits:**

Edit `docker-compose.yml`:
```yaml
services:
  python-interpreter:
    mem_limit: 4G        # Increase for large data processing
    cpus: 4.0            # More CPUs for parallel execution
    
  ddg-search:
    mem_limit: 1G
    cpus: 1.0
```

### Monitoring Setup

**Prometheus Metrics** (TODO: Implement):
```yaml
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

**Grafana Dashboard** (TODO: Implement):
```yaml
services:
  grafana:
    image: grafana/grafana
    ports:
      - "3001:3000"
    depends_on:
      - prometheus
```

---

**Next Steps:**
- [Testing Guide](./testing.md) - Validation scenarios
- [API Reference](./api.md) - Integration details
- [Architecture](./architecture.md) - System design
