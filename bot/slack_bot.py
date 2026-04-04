import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT", "slb-ai-agent-prod")
REGION = os.getenv("GCP_LOCATION", "us-central1")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

from fastapi import FastAPI
from slack_bolt.app import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

app = FastAPI(title="Gubbu Bot")

slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN", ""),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET", ""),
)

handler = SlackRequestHandler(app=slack_app)


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


app.add_route("/slack/events", handler.handle)
app.add_route("/slack/interactive", handler.handle)


@app.get("/health")
def health():
    return {"status": "ok", "service": "gubbu-bot"}


@app.get("/")
def root():
    return {"message": "Gubbu Bot is running", "project": PROJECT_ID}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
