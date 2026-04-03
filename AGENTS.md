# AGENTS.md - Development Guidelines for This Repository

This repository contains a Slack bot with GCP MCP server integration. It uses Python with async/await patterns, LangChain, LangGraph, and MCP.

## Project Structure

```
.
├── bot/
│   ├── slack_bot.py      # Main Slack bot (AsyncApp)
│   ├── gcp_server.py    # MCP server for GCP operations
│   ├── Dockerfile       # Container configuration
│   └── requirements.txt # Python dependencies
├── n8n/                  # n8n workflow configurations
└── .env                  # Environment variables (not committed)
```

## Build & Runtime Commands

### Installation
```bash
cd bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Running the Slack Bot
```bash
cd bot
python slack_bot.py
```

### Running the GCP MCP Server (standalone)
```bash
cd bot
python gcp_server.py
```

### Running Tests
No tests currently exist. To add tests:
```bash
pytest
pytest tests/test_gcp_server.py
pytest tests/test_gcp_server.py::test_function_name
```

### Linting & Formatting
Recommended: `pip install ruff black mypy`
```bash
ruff format .
ruff check .
mypy .
```

## Code Style Guidelines

### Imports
Order imports strictly:
1. Standard library (`os`, `sys`, `asyncio`, `subprocess`, `json`)
2. Third-party packages (`dotenv`, `slack_bolt`, `langchain_ollama`, `langgraph`)
3. Local imports

```python
import os
import sys
import asyncio
from dotenv import load_dotenv
from slack_bolt.async_app import AsyncApp
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from mcp.server.fastmcp import FastMCP
```

### Naming Conventions
- **Functions/variables**: snake_case (`create_secret`, `run_command`)
- **Constants**: UPPER_SNAKE_CASE (`GCLOUD_PATH`, `OLLAMA_BASE_URL`)
- **Classes**: PascalCase
- **File names**: snake_case (`slack_bot.py`, `gcp_server.py`)

### Type Hints
Use type hints for all function parameters and return values.

### Async/Await Patterns
Use `async def` and `await`; wrap main entry with `asyncio.run()`.

### Error Handling
Use try/except blocks. Return meaningful error messages as strings (MCP tools return strings, not exceptions).

```python
try:
    result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
    return result.stdout.strip()
except subprocess.CalledProcessError as e:
    return f"COMMAND FAILED:\n{e.stderr}"
```

### Docstrings
Use Google-style docstrings for all public functions.

### Handling Secrets & Sensitive Data
- Never commit `.env` files or credentials
- Use environment variables for secrets
- Use stdin rather than CLI args when passing secrets

### MCP Tool Functions
All MCP tools must be decorated with `@mcp.tool()` and return strings.

### Hardcoded Paths
Avoid hardcoding paths. Use environment variables:
```python
GCLOUD_PATH = os.environ.get("GCLOUD_PATH", "/usr/local/bin/gcloud")
```

### Logging
Use `print()` for simple output (current convention).

### Docker
When modifying the Dockerfile:
- Use slim Python images
- Install dependencies in a single layer
- Run as non-root user when possible

## Common Issues & Solutions

### MCP Connection Issues
Initialize MCP client without `async with`:
```python
client = MultiServerMCPClient({"gcp-manager": {...}})
tools = await client.get_tools()
```

### gcloud Not Found
If gcloud is not found, the server returns a helpful error. Configure the `GCLOUD_PATH` environment variable if the default doesn't work.

### Slack Token Errors
Ensure `.env` contains: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_APP_TOKEN`

## Dependencies
- `mcp` - Model Context Protocol
- `google-cloud-sdk` - GCP CLI wrapper
- `slack-bolt` - Slack app framework
- `langchain-ollama` - Ollama LLM integration
- `langgraph` - Agent workflow orchestration
- `langchain-mcp-adapters` - MCP client for LangChain
- `python-dotenv` - Environment variable loading

## Key Files

- `bot/slack_bot.py` - Main Slack bot entry point using AsyncApp
- `bot/gcp_server.py` - MCP server exposing GCP DevOps tools