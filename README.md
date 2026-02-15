Google Cloud MCP Server
An open-source Model Context Protocol (MCP) server that enables AI agents (like Claude, Llama 3.1, or custom LangChain bots) to interact with Google Cloud Platform safely and autonomously.

This server acts as a bridge between your LLM and the gcloud CLI, allowing you to manage Cloud Run services and Secrets using natural language.

🚀 Features
🔍 List Services: detailed inspection of running Cloud Run services.

🔐 Manage Secrets: Safely create and update secrets in Google Secret Manager.

Self-Healing: Automatically detects if the Secret Manager API is disabled and enables it for you.

🚀 Deploy & Update: Deploy new revisions or update memory/image configuration for Cloud Run services.

Safe-Guards: Checks existing configuration before applying changes to prevent accidental overwrites.

🛠️ Prerequisites
Python 3.10+

Google Cloud SDK (gcloud): Must be installed and authenticated.

Install: brew install --cask google-cloud-sdk (Mac) or see Official Docs.

Auth: Run gcloud auth login and gcloud config set project [YOUR_PROJECT_ID].

📦 Installation
Clone the repository:

Bash
git clone https://github.com/YOUR_USERNAME/mcp-gcp-manager.git
cd mcp-gcp-manager
Create a Virtual Environment (Recommended):

Bash
python3 -m venv venv
source venv/bin/activate
Install Dependencies:

Bash
pip install mcp
⚙️ Configuration
The server attempts to automatically find your gcloud executable.

If you see a "gcloud not found" error: You can manually tell the server where gcloud is by setting an environment variable:

Bash
# Example for Mac/Linux
export GCLOUD_PATH="/usr/local/bin/gcloud"

# Example for Windows (PowerShell)
$env:GCLOUD_PATH="C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.exe"
💻 Usage
Option 1: Using with Claude Desktop
To use this with the official Claude Desktop app, add the following to your claude_desktop_config.json:

JSON
{
  "mcpServers": {
    "gcp-manager": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["/path/to/mcp-gcp-manager/server.py"]
    }
  }
}
Option 2: Using with LangChain / Custom Python Agents
You can connect to this server using langchain-mcp-adapters:

Python
from langchain_mcp_adapters.client import MultiServerMCPClient

# Connect to the local server process
client = MultiServerMCPClient({
    "gcp": {
        "command": "python",
        "args": ["server.py"],
        "transport": "stdio"
    }
})

# Get tools and bind to your model (Llama 3, GPT-4, etc.)
tools = await client.get_tools()
🛡️ Tools Available
Tool Name	Description
list_running_services	Lists all Cloud Run services in a specific project.
create_secret	Creates/Updates secrets. Handles API enablement automatically.
deploy_service	Deploys a new revision. Supports updating memory, image, etc.
🤝 Contributing
Pull requests are welcome! Please ensure any new tools include proper error handling and do not hardcode local paths.

📄 License
MIT