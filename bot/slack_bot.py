import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

# Import Ollama
from langchain_ollama import ChatOllama

# Import LangGraph
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

# Import MCP Client
from langchain_mcp_adapters.client import MultiServerMCPClient

app = AsyncApp(
    token=os.environ["SLACK_BOT_TOKEN"], 
    signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)

@app.message()
async def handle_message(message, say):
    user_text = message['text']
    status_msg = await say(f"🦙 Gubbu is thinking about: '{user_text}'...")

    # --- FIX: Initialize Client directly (No 'async with') ---
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
        # --- FIX: Await get_tools() explicitly ---
        # The connection happens automatically here now
        tools = await client.get_tools()

        # Initialize Model
        llm = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            temperature=0,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )

        # Create the Agent (LangGraph)
        agent = create_react_agent(llm, tools)

        # Run the Agent
        response = await agent.ainvoke({"messages": [HumanMessage(content=user_text)]})
        
        # Extract answer
        final_answer = response["messages"][-1].content
        
        await app.client.chat_update(
            channel=message["channel"],
            ts=status_msg["ts"],
            text=final_answer
        )
    except Exception as e:
        await say(f"💥 Error: {str(e)}")

async def main():
    print("⚡️ Gubbu Bot (Modern Stack) is running!")
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()

if __name__ == "__main__":
    asyncio.run(main())
