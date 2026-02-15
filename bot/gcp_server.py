import subprocess
import json
import shutil
from time import time
from typing import Dict, Optional
from mcp.server.fastmcp import FastMCP

# Initialize Server
mcp = FastMCP("GCP-DevOps-Manager")

GCLOUD_PATH = "/Users/kishorekumar/google-cloud-sdk/bin/gcloud"

def run_command(cmd_list: list) -> str:
    """Runs a shell command and returns the output or error."""
    if cmd_list[0] == "gcloud":
        cmd_list[0] = GCLOUD_PATH
    # Security: Ensure gcloud is installed
    if not shutil.which("gcloud"):
        return "Error: 'gcloud' CLI is not found. Please install the Google Cloud SDK."
    try:
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Return the error message from the CLI (e.g., "Permissions denied")
        return f"COMMAND FAILED:\n{e.stderr}"

@mcp.tool()
def create_secret(name: str, value: str, project_id: str) -> str:
    """
    Creates a secret. Automatically enables the Secret Manager API if needed.
    """
    import os
    import time  # <--- FIX: Importing it here guarantees it works
    if not os.path.exists(GCLOUD_PATH):
        return f"Error: gcloud not found at {GCLOUD_PATH}"

    # --- STEP 1: Check & Enable API ---
    print(f"🔍 Checking if Secret Manager API is enabled for {project_id}...")
    
    check_cmd = [
        GCLOUD_PATH, "services", "list", 
        "--project", project_id, 
        "--enabled", 
        "--filter=name:secretmanager.googleapis.com", 
        "--format=value(config.name)"
    ]
    
    check_result = subprocess.run(check_cmd, capture_output=True, text=True)
    
    if "secretmanager.googleapis.com" not in check_result.stdout:
        print("⚙️ API not found. Enabling Secret Manager API (this takes ~10s)...")
        enable_cmd = [
            GCLOUD_PATH, "services", "enable", "secretmanager.googleapis.com", 
            "--project", project_id
        ]
        enable_result = subprocess.run(enable_cmd, capture_output=True, text=True)
        
        if enable_result.returncode != 0:
            return f"❌ Failed to enable Secret Manager API: {enable_result.stderr}"
        
        # Give Google Cloud a moment to propagate the change
        time.sleep(2)
        print("✅ Secret Manager API is enabled.")

    # 1. Create the secret container (idempotent: fails silently if exists)
    subprocess.run(
        ["gcloud", "secrets", "create", name, "--project", project_id, "--replication-policy", "automatic", "--quiet"],
        capture_output=True
    )

    # 2. Add the payload
    # We use pipe input for security so the secret isn't in process args
    process = subprocess.Popen(
        ["gcloud", "secrets", "versions", "add", name, "--project", project_id, "--data-file=-", "--format=json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate(input=value)
    
    if process.returncode == 0:
        return f"✅ Secret '{name}' updated successfully."
    else:
        return f"❌ Error updating secret: {stderr}"

@mcp.tool()
def deploy_cloud_run(service_name: str, image: str, region: str, env_secrets: Dict[str, str], allow_public: bool = False) -> str:
    """
    Deploys a container to Cloud Run.
    Args:
        service_name: Name of the service (e.g., "hotel-api")
        image: Container image (e.g., "gcr.io/proj/img:tag")
        env_secrets: Map of ENV_VAR to SECRET_NAME (e.g., {"DB_PASS": "DB_PASSWORD_SECRET"})
        allow_public: If True, allows unauthenticated access (use carefully!)
    """
    # Build secrets flag: --set-secrets="ENV_VAR=SECRET:latest,ENV2=SEC2:latest"
    secret_args = []
    for env_var, secret_name in env_secrets.items():
        secret_args.append(f"{env_var}={secret_name}:latest")
    
    cmd = [
        "gcloud", "run", "deploy", service_name,
        "--image", image,
        "--region", region,
        "--format", "json"
    ]

    if secret_args:
        cmd.extend(["--set-secrets", ",".join(secret_args)])
    
    if allow_public:
        cmd.append("--allow-unauthenticated")
    
    output = run_command(cmd)
    
    if "COMMAND FAILED" in output:
        return output

    try:
        data = json.loads(output)
        url = data.get("status", {}).get("url", "Unknown URL")
        return f"🚀 Deployment Complete!\nService: {service_name}\nURL: {url}"
    except:
        return f"Deployment finished, but output parsing failed.\nRaw: {output[:200]}..."

@mcp.tool()
def check_service_logs(service_name: str, project_id: str) -> str:
    """
    Reads the last 20 log entries for a specific service. 
    Useful for debugging failed deployments.
    """
    cmd = [
        "gcloud", "logging", "read",
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service_name}"',
        "--project", project_id,
        "--limit", "20",
        "--format", "value(textPayload,jsonPayload.message)",
        "--order", "desc"
    ]
    return run_command(cmd)

@mcp.tool()
def list_running_services(project_id: str) -> str:
    """Lists all active Cloud Run services and their URLs."""
    cmd = [
        "gcloud", "run", "services", "list",
        "--project", project_id,
        "--format", "table(metadata.name, status.url, status.latestCreatedRevisionName)"
    ]
    return run_command(cmd)

@mcp.tool()
def list_enabled_services(project_id: str) -> str:
    """
    Lists all enabled Google Cloud APIs/Services for a given project.
    Useful for debugging permission errors.
    """
    import os
    import subprocess

    if not os.path.exists(GCLOUD_PATH):
        return f"Error: gcloud not found at {GCLOUD_PATH}"

    cmd = [
        GCLOUD_PATH, "services", "list",
        "--enabled",
        "--project", project_id,
        "--format=value(config.name)" # Clean output (just names)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Format the output to be readable
        services = result.stdout.strip().split('\n')
        count = len(services)
        service_list = "\n- ".join(services[:15]) # Show top 15 to avoid spamming Slack
        
        return f"✅ Found {count} enabled services in '{project_id}'.\nHere are some of them:\n- {service_list}\n... (and {count - 15} more)"

    except subprocess.CalledProcessError as e:
        return f"❌ Failed to list services: {e.stderr}"

if __name__ == "__main__":
    mcp.run()
