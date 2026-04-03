import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from langchain_google_vertexai import ChatVertexAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from langchain_mcp_adapters.client import MultiServerMCPClient

app = AsyncApp(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
)

PROJECT_ID = os.getenv("GCP_PROJECT", "slb-ai-agent-prod")
REGION = os.getenv("GCP_LOCATION", "us-central1")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")


@app.message()
async def handle_message(message, say):
    user_text = message["text"]
    await say(f"🤖 Processing your request: '{user_text}'...")

    client = MultiServerMCPClient(
        {
            "gcp-manager": {
                "command": sys.executable,
                "args": ["gcp_server.py"],
                "transport": "stdio",
            }
        }
    )

    try:
        tools = await client.get_tools()

        llm = ChatVertexAI(model=MODEL_NAME, project=PROJECT_ID, location=REGION)

        agent = create_react_agent(llm, tools)

        response = await agent.ainvoke({"messages": [HumanMessage(content=user_text)]})

        final_answer = response["messages"][-1].content

        await app.client.chat_update(
            channel=message["channel"], ts=message["ts"], text=final_answer
        )
    except Exception as e:
        await say(f"💥 Error: {str(e)}")


@app.command("/gcp-status")
async def gcp_status_command(ack, say):
    await ack()
    client = MultiServerMCPClient(
        {
            "gcp-manager": {
                "command": sys.executable,
                "args": ["gcp_server.py"],
                "transport": "stdio",
            }
        }
    )
    try:
        tools = await client.get_tools()
        for tool in tools:
            if tool.name == "gcp_status":
                result = await tool.ainvoke({})
                await say(f"```\n{result}\n```")
                break
    except Exception as e:
        await say(f"Error: {str(e)}")


@app.command("/cloudrun-list")
async def cloudrun_list_command(ack, say):
    await ack()
    client = MultiServerMCPClient(
        {
            "gcp-manager": {
                "command": sys.executable,
                "args": ["gcp_server.py"],
                "transport": "stdio",
            }
        }
    )
    try:
        tools = await client.get_tools()
        for tool in tools:
            if tool.name == "cloudrun_list_services":
                result = await tool.ainvoke({})
                await say(f"```\n{result}\n```")
                break
    except Exception as e:
        await say(f"Error: {str(e)}")


async def main():
    print(
        f"⚡️ GCP AI Agent Platform - Project: {PROJECT_ID}, Region: {REGION}, Model: {MODEL_NAME}"
    )
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
