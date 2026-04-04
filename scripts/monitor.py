#!/usr/bin/env python3
"""
GitHub Actions Monitor Agent
Monitors CI/CD workflow and notifies orchestrator on failure
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path

REPO = "KishoreKu/slackbot-gcp-mcp-server"
CHECK_INTERVAL = 30
NOTIFICATION_FILE = "/tmp/workflow_alert.json"


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def notify_orchestrator(run_id, status, conclusion, issues):
    """Notify orchestrator via notification file"""
    alert = {
        "timestamp": datetime.now().isoformat(),
        "run_id": run_id,
        "status": status,
        "conclusion": conclusion,
        "issues": issues,
        "repo": REPO,
        "action_required": True,
    }

    with open(NOTIFICATION_FILE, "w") as f:
        import json

        json.dump(alert, f, indent=2)

    print(f"🔔 NOTIFICATION: Workflow {run_id} {conclusion}")
    print(f"   Issues: {issues}")
    print(f"   Alert written to: {NOTIFICATION_FILE}")


def get_issues_from_logs(run_id):
    """Analyze logs to determine what needs fixing"""
    _, out, _ = run_cmd(f"gh run view {run_id} --repo {REPO} --log 2>&1 | tail -100")

    issues = []

    if "IAM Service Account Credentials API" in out and "has not been used" in out:
        issues.append("IAM_API_DISABLED")

    if "artifactregistry.repositories.uploadArtifacts" in out:
        issues.append("ARTIFACT_REGISTRY_PERMISSION")

    if "does not have permission" in out and "iam.serviceaccounts.actAs" in out:
        issues.append("SERVICE_ACCOUNT_PERMISSION")
        if "pip install" in out:
            issues.append("PYTHON_DEPENDENCY")
        issues.append("BUILD_FAILED")

    if "denied: Unauthenticated" in out:
        issues.append("AUTH_FAILED")

    return issues if issues else ["UNKNOWN_ERROR"]


def main():
    print("🚀 GitHub Actions Monitor Agent started")
    print(f"Monitoring: {REPO}")
    print(f"Check interval: {CHECK_INTERVAL}s\n")

    last_run_id = None

    while True:
        try:
            code, out, err = run_cmd(f"gh run list --repo {REPO} --limit 1")

            if code != 0 or not out.strip():
                time.sleep(CHECK_INTERVAL)
                continue

            lines = out.strip().split("\n")
            if len(lines) < 2:
                time.sleep(CHECK_INTERVAL)
                continue

            parts = lines[1].split()
            run_id = parts[-1] if parts else None
            status = parts[0] if len(parts) > 0 else None
            conclusion = parts[1] if len(parts) > 1 else None

            print(f"[{datetime.now().strftime('%H:%M:%S')}] {status} - {conclusion}")

            # Detect new failure
            if (
                status == "completed"
                and conclusion == "failure"
                and run_id != last_run_id
            ):
                last_run_id = run_id

                issues = get_issues_from_logs(run_id)
                notify_orchestrator(run_id, status, conclusion, issues)

            elif status == "completed" and conclusion == "success":
                print("✅ Workflow succeeded!")
                last_run_id = run_id

                # Clear notification if exists
                if Path(NOTIFICATION_FILE).exists():
                    Path(NOTIFICATION_FILE).unlink()

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n👋 Monitor stopped")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
