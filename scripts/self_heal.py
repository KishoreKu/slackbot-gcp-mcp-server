#!/usr/bin/env python3
"""
GitHub Actions Self-Healing Agent
Monitors CI/CD workflow continuously until success, auto-fixes common issues
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime

REPO = "KishoreKu/slackbot-gcp-mcp-server"
GCP_PROJECT = "slb-ai-agent-prod"
PROJECT_NUM = "220128978456"
CHECK_INTERVAL = 30


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


class GitHubActionsAgent:
    def __init__(self):
        self.repo = REPO
        self.gcp_project = GCP_PROJECT
        self.project_num = PROJECT_NUM
        self.fixed = False

    def get_latest_run(self):
        code, out, _ = run_cmd(f"gh run list --repo {self.repo} --limit 1")
        if code != 0 or not out.strip():
            return None

        lines = out.strip().split("\n")
        if len(lines) < 2:
            return None

        parts = lines[1].split()
        return {
            "id": parts[-1] if parts else None,
            "status": parts[0] if len(parts) > 0 else None,
            "conclusion": parts[1] if len(parts) > 1 else None,
        }

    def get_failure_logs(self, run_id):
        _, out, _ = run_cmd(
            f"gh run view {run_id} --repo {self.repo} --log 2>&1 | tail -150"
        )
        return out

    def analyze_failure(self, logs):
        issues = []

        if (
            "IAM Service Account Credentials API" in logs
            and "has not been used" in logs
        ):
            issues.append("IAM_API")

        if "artifactregistry.repositories.uploadArtifacts" in logs:
            issues.append("ARTIFACT_REGISTRY")

        if "exit code: 1" in logs:
            if "pip install" in logs:
                issues.append("PIP_INSTALL")

        if "denied: Unauthenticated" in logs:
            issues.append("AUTH")

        return issues

    def fix_iam_api(self):
        print("🔧 Enabling IAM Service Account Credentials API...")
        run_cmd(
            f"gcloud services enable iamcredentials.googleapis.com --project={self.gcp_project}"
        )
        return True

    def fix_artifact_registry(self):
        print("🔧 Fixing Artifact Registry...")

        run_cmd(
            f"gcloud artifacts repositories create gcr.io "
            f"--repository-format=docker --location=us "
            f"--project={self.gcp_project} 2>/dev/null"
        )

        run_cmd(
            f"gcloud projects add-iam-policy-binding {self.gcp_project} "
            f"--member=serviceAccount:gubbu-cicd-sa@{self.gcp_project}.iam.gserviceaccount.com "
            f"--role=roles/artifactregistry.writer 2>/dev/null"
        )

        return True

    def fix_dependencies(self):
        print("🔧 Updating bot dependencies...")

        req_path = Path("bot/requirements.txt")
        deps = [
            "mcp>=1.0.0",
            "google-cloud-aiplatform>=1.50.0",
            "google-auth>=2.35.0",
            "langchain-core>=0.3.0",
            "langgraph>=0.2.0",
            "langchain-google-vertexai>=1.0.0",
            "langchain-mcp-adapters>=0.1.0",
            "slack-bolt>=1.20.0",
            "python-dotenv>=1.0.0",
        ]
        req_path.write_text("\n".join(deps) + "\n")

        workflow_path = Path(".github/workflows/deploy.yml")
        if workflow_path.exists():
            content = workflow_path.read_text()
            if "--platform linux/amd64" not in content:
                content = content.replace(
                    "docker build", "docker build --platform linux/amd64"
                )
                workflow_path.write_text(content)

        return True

    def fix_workload_identity(self):
        print("🔧 Fixing Workload Identity...")

        run_cmd(
            f"gcloud projects add-iam-policy-binding {self.gcp_project} "
            f"--member=principalSet://iam.googleapis.com/projects/{self.project_num}/"
            f"locations/global/workloadIdentityPools/github-actions-pool/"
            f"attribute.repository/KishoreKu/slackbot-gcp-mcp-server "
            f"--role=roles/iam.workloadIdentityUser 2>/dev/null"
        )

        run_cmd(
            f"gcloud projects add-iam-policy-binding {self.gcp_project} "
            f"--member=serviceAccount:gubbu-cicd-sa@{self.gcp_project}.iam.gserviceaccount.com "
            f"--role=roles/artifactregistry.writer 2>/dev/null"
        )

        return True

    def apply_fixes(self, issues):
        fixed = False

        for issue in issues:
            if issue == "IAM_API":
                if self.fix_iam_api():
                    fixed = True
                    time.sleep(5)

            elif issue == "ARTIFACT_REGISTRY":
                if self.fix_artifact_registry():
                    fixed = True

            elif issue == "PIP_INSTALL":
                if self.fix_dependencies():
                    fixed = True

            elif issue == "AUTH":
                if self.fix_workload_identity():
                    fixed = True

        return fixed

    def push_fixes(self):
        run_cmd("git add -A")

        code, out, _ = run_cmd("git diff --cached --stat")
        if not out.strip():
            return False

        run_cmd('git commit -m "Auto-fix: CI/CD build issues"')
        run_cmd("git push origin master")
        print("✅ Fixes pushed!")
        self.fixed = True
        return True

    def run(self):
        print("🚀 Starting GitHub Actions Self-Healing Agent...")
        print(f"Monitoring: {self.repo}")
        print("Press Ctrl+C to stop\n")

        consecutive_failures = 0
        max_retries = 10

        while True:
            try:
                run = self.get_latest_run()

                if not run:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for workflow..."
                    )
                    time.sleep(CHECK_INTERVAL)
                    continue

                run_id = run.get("id")
                status = run.get("status")
                conclusion = run.get("conclusion")

                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Run {run_id}: {status} - {conclusion}"
                )

                if status == "completed":
                    if conclusion == "success":
                        print("\n" + "=" * 50)
                        print("🎉 WORKFLOW SUCCEEDED!")
                        print("=" * 50)
                        print("\n✅ Self-healing agent can now be stopped.")
                        break

                    elif conclusion == "failure":
                        consecutive_failures += 1
                        print(
                            f"❌ Workflow failed (attempt {consecutive_failures}/{max_retries})"
                        )

                        if consecutive_failures >= max_retries:
                            print("⚠️ Max retries reached - stopping")
                            break

                        logs = self.get_failure_logs(run_id)
                        issues = self.analyze_failure(logs)
                        print(f"Issues: {issues}")

                        if self.apply_fixes(issues):
                            time.sleep(3)
                            if self.push_fixes():
                                print("🔄 Waiting for next run after fix...")
                                time.sleep(60)
                        else:
                            print("⚠️ Could not auto-fix")

                    else:
                        consecutive_failures = 0

                elif status == "in_progress":
                    consecutive_failures = 0
                    print("🔄 Workflow in progress...")

                else:
                    print(f"Status: {status}")

                time.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                print("\n👋 Stopping agent...")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    agent = GitHubActionsAgent()
    agent.run()
