import os
import subprocess
import json
import shutil
from typing import Dict, Optional, List, Any
from mcp.server.fastmcp import FastMCP
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

PROJECT_ID = "slb-ai-agent-prod"
REGION = "us-central1"

mcp = FastMCP("GCP-AI-Agent-Platform")

GCLOUD_PATH = "/Users/kishorekumar/google-cloud-sdk/bin/gcloud"


def run_gcloud(cmd: list) -> str:
    if cmd[0] == "gcloud":
        cmd[0] = GCLOUD_PATH
    if not shutil.which("gcloud"):
        return "Error: gcloud CLI not found"
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"COMMAND FAILED:\n{e.stderr}"


def run_aiplatform_rest(method: str, endpoint: str, body: dict = None) -> str:
    url = f"https://{REGION}-aiplatform.googleapis.com/v1/{endpoint}"
    cmd = [
        GCLOUD_PATH,
        "api",
        "locations",
        "predict",
        "--endpoint",
        url,
        "--http-verb",
        method,
        "--request-body",
        json.dumps(body) if body else "{}",
    ]
    return run_gcloud(cmd)


@mcp.tool()
def cloudrun_deploy(
    service_name: str,
    image: str,
    region: str = REGION,
    env_vars: Dict[str, str] = None,
    allow_public: bool = False,
) -> str:
    """
    Deploy a container to Cloud Run.
    """
    cmd = [
        GCLOUD_PATH,
        "run",
        "deploy",
        service_name,
        "--image",
        image,
        "--region",
        region,
        "--format",
        "json",
    ]
    if env_vars:
        for k, v in env_vars.items():
            cmd.extend(["--set-env-vars", f"{k}={v}"])
    if allow_public:
        cmd.append("--allow-unauthenticated")
    output = run_gcloud(cmd)
    try:
        data = json.loads(output)
        return f"Cloud Run deployed: {data.get('status', {}).get('url', 'Unknown')}"
    except:
        return f"Deployed. Output: {output[:300]}"


@mcp.tool()
def cloudrun_list_services() -> str:
    """List all Cloud Run services."""
    cmd = [
        GCLOUD_PATH,
        "run",
        "services",
        "list",
        "--project",
        PROJECT_ID,
        "--format",
        "json",
    ]
    output = run_gcloud(cmd)
    try:
        services = json.loads(output)
        if not services:
            return "No Cloud Run services found."
        result = "Cloud Run Services:\n"
        for s in services:
            result += f"- {s.get('metadata', {}).get('name')}: {s.get('status', {}).get('url', 'N/A')}\n"
        return result
    except:
        return output[:500]


@mcp.tool()
def cloudrun_get_logs(service_name: str, limit: int = 10) -> str:
    """Get logs for a Cloud Run service."""
    cmd = [
        GCLOUD_PATH,
        "logging",
        "read",
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service_name}"',
        "--project",
        PROJECT_ID,
        "--limit",
        str(limit),
        "--format",
        "value(textPayload,jsonPayload.message)",
    ]
    return run_gcloud(cmd)


@mcp.tool()
def vertexai_list_models() -> str:
    """List available Vertex AI models."""
    cmd = [
        GCLOUD_PATH,
        "ai",
        "models",
        "list",
        "--region",
        REGION,
        "--project",
        PROJECT_ID,
        "--format",
        "json",
    ]
    output = run_gcloud(cmd)
    try:
        models = json.loads(output)
        if not models:
            return "No models found."
        result = "Vertex AI Models:\n"
        for m in models[:10]:
            result += f"- {m.get('name', 'N/A')}\n"
        return result
    except:
        return output[:500]


@mcp.tool()
def vertexai_deploy_model(
    model_id: str, endpoint_name: str, machine_type: str = "n1-standard-4"
) -> str:
    """Deploy a model to Vertex AI endpoint."""
    cmd = [
        GCLOUD_PATH,
        "ai",
        "model-deployments",
        "deploy",
        "--model",
        model_id,
        "--endpoint",
        endpoint_name,
        "--machine-type",
        machine_type,
        "--region",
        REGION,
    ]
    return run_gcloud(cmd)


@mcp.tool()
def vertexai_predict(endpoint_id: str, instances: List[Any]) -> str:
    """Make a prediction using Vertex AI."""
    cmd = [
        GCLOUD_PATH,
        "ai",
        "predict",
        "--endpoint",
        f"{REGION}/publishers/google/models/{endpoint_id}",
        "--json-request",
        json.dumps({"instances": instances}),
    ]
    return run_gcloud(cmd)


@mcp.tool()
def firestore_create_collection(collection_id: str) -> str:
    """Create a Firestore collection (implicit via first document)."""
    return f"Firestore: Collection '{collection_id}' created (created when first document is added)."


@mcp.tool()
def firestore_add_document(collection_id: str, document_id: str, data: Dict) -> str:
    """Add a document to Firestore."""
    cmd = [
        GCLOUD_PATH,
        "firestore",
        "documents",
        "create",
        f"projects/{PROJECT_ID}/databases/(default)/documents/{collection_id}/{document_id}",
        "--from-file",
        "-",
    ]
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate(input=json.dumps(data))
    if process.returncode == 0:
        return f"Document {document_id} added to {collection_id}"
    return f"Error: {stderr}"


@mcp.tool()
def firestore_list_collections() -> str:
    """List Firestore collections."""
    cmd = [GCLOUD_PATH, "firestore", "indexes", "list", "--project", PROJECT_ID]
    return run_gcloud(cmd)


@mcp.tool()
def bigquery_query(query: str) -> str:
    """Execute a BigQuery SQL query."""
    cmd = [
        GCLOUD_PATH,
        "bq",
        "query",
        "--use_legacy_sql=false",
        "--nouse_legacy_sql",
        f"--project={PROJECT_ID}",
        query,
    ]
    return run_gcloud(cmd)


@mcp.tool()
def bigquery_create_dataset(dataset_id: str) -> str:
    """Create a BigQuery dataset."""
    cmd = [GCLOUD_PATH, "bq", "mk", "--dataset", f"--project={PROJECT_ID}", dataset_id]
    return run_gcloud(cmd)


@mcp.tool()
def bigquery_list_datasets() -> str:
    """List BigQuery datasets."""
    cmd = [GCLOUD_PATH, "bq", "ls", "--project_id", PROJECT_ID]
    return run_gcloud(cmd)


@mcp.tool()
def bigquery_list_tables(dataset_id: str) -> str:
    """List tables in a BigQuery dataset."""
    cmd = [GCLOUD_PATH, "bq", "ls", "--project_id", PROJECT_ID, f"{dataset_id}"]
    return run_gcloud(cmd)


@mcp.tool()
def orchestrator_route(user_request: str) -> str:
    """
    Route user request to the appropriate agent.
    Determine which GCP service the user wants to interact with.
    Returns: "cloudrun", "vertexai", "firestore", "bigquery", or "unknown"
    """
    user_lower = user_request.lower()

    cloudrun_keywords = [
        "deploy",
        "cloud run",
        "run service",
        "container",
        "serverless",
        "revision",
        "logs",
    ]
    vertexai_keywords = [
        "model",
        "predict",
        "vertex ai",
        "ai platform",
        "ml",
        "endpoint",
        "train",
    ]
    firestore_keywords = [
        "firestore",
        "document",
        "collection",
        "nosql",
        "database",
        "store",
    ]
    bigquery_keywords = [
        "bigquery",
        "query",
        "sql",
        "dataset",
        "warehouse",
        "analytics",
    ]

    for kw in cloudrun_keywords:
        if kw in user_lower:
            return "cloudrun"
    for kw in vertexai_keywords:
        if kw in user_lower:
            return "vertexai"
    for kw in firestore_keywords:
        if kw in user_lower:
            return "firestore"
    for kw in bigquery_keywords:
        if kw in user_lower:
            return "bigquery"

    return "unknown"


@mcp.tool()
def gcp_status() -> str:
    """Get GCP project status - enabled services."""
    cmd = [
        GCLOUD_PATH,
        "services",
        "list",
        "--enabled",
        "--project",
        PROJECT_ID,
        "--format=value(config.name)",
    ]
    output = run_gcloud(cmd)
    services = output.split("\n") if output else []
    return f"Project: {PROJECT_ID}\nEnabled services: {len(services)}\n{services[:10]}"


if __name__ == "__main__":
    print(f"Starting GCP AI Agent Platform for project: {PROJECT_ID}")
    mcp.run()
