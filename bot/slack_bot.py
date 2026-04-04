import os
import sys
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, JSONResponse
import uvicorn

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT", "slb-ai-agent-prod")
REGION = os.getenv("GCP_LOCATION", "us-central1")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

app = FastAPI(title="Gubbu Bot")


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "service": "gubbu-bot"})


@app.get("/")
async def root():
    return JSONResponse({"message": "Gubbu Bot is running", "project": PROJECT_ID})


async def main():
    print(f"⚡️ Gubbu Bot - Project: {PROJECT_ID}, Region: {REGION}")
    
    from slack_bolt.app import App
    from slack_bolt.adapter.fastapi import Slack BoltHandler
    
    slack_app = App(
        token=os.environ["SLACK_BOT_TOKEN"],
        signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    )

    @slack_app.message("")
    def handle_message(message, say):
        say(f"🤖 Processing: {message['text']}...")

    @slack_app.command("/gcp-status")
    def gcp_status_command(ack, say):
        ack()
        say(f"✅ Project: {PROJECT_ID}, Region: {REGION}, Model: {MODEL_NAME}")

    @slack_app.command("/cloudrun-list")
    def cloudrun_list_command(ack, say):
        ack()
        say("📋 Listing Cloud Run services...")

    handler = Slack BoltHandler(app=slack_app)
    app.add_route("/slack/events", handler.handle_events)
    app.add_route("/slack/interactive", handler.handle_interactivity)
    
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())