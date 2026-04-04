#!/usr/bin/env python3
"""
CI/CD Orchestrator Agent
Fixes failing workflow issues and pushes code to GitHub
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path

REPO = "KishoreKu/slackbot-gcp-mcp-server"
GCP_PROJECT = "slb-ai-agent-prod"
PROJECT_NUM = "220128978456"
NOTIFICATION_FILE = "/tmp/workflow_alert.json"


def run_cmd(cmd, check=False):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"   ⚠️ {result.stderr[:100]}")
    return result.returncode, result.stdout, result.stderr


class CI/CDOrchestrator:
    def __init__(self):
        self.repo = REPO
        self.gcp_project = GCP_PROJECT
        self.project_num = PROJECT_NUM
        self.notification_file = Path(NOTIFICATION_FILE)
    
    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    
    def check_notification(self):
        if not self.notification_file.exists():
            return None
        
        try:
            alert = json.loads(self.notification_file.read_text())
            if alert.get("action_required"):
                return alert
        except:
            pass
        return None
    
    def clear_notification(self):
        if self.notification_file.exists():
            self.notification_file.unlink()
            self.log("Notification cleared")
    
    def fix_iam_api(self):
        self.log("🔧 Enabling IAM Service Account Credentials API...")
        run_cmd(f"gcloud services enable iamcredentials.googleapis.com --project={self.gcp_project}")
        return True
    
    def fix_artifact_registry(self):
        self.log("🔧 Fixing Artifact Registry...")
        run_cmd(f"gcloud artifacts repositories create gcr.io "
                f"--repository-format=docker --location=us "
                f"--project={self.gcp_project} 2>/dev/null")
        run_cmd(f"gcloud projects add-iam-policy-binding {self.gcp_project} "
                f"--member=serviceAccount:gubbu-cicd-sa@{self.gcp_project}.iam.gserviceaccount.com "
                f"--role=roles/artifactregistry.writer 2>/dev/null")
        return True
    
    def fix_service_account_permission(self):
        self.log("🔧 Adding Service Account permissions...")
        run_cmd(f"gcloud projects add-iam-policy-binding {self.gcp_project} "
                f"--member=serviceAccount:gubbu-cicd-sa@{self.gcp_project}.iam.gserviceaccount.com "
                f"--role=roles/resourcemanager.projectIamAdmin 2>/dev/null")
        run_cmd(f"gcloud projects add-iam-policy-binding {self.gcp_project} "
                f"--member=serviceAccount:gubbu-cicd-sa@{self.gcp_project}.iam.gserviceaccount.com "
                f"--role=roles/iam.serviceAccountUser 2>/dev/null")
        return True
    
    def fix_python_dependencies(self):
        self.log("🔧 Updating bot dependencies...")
        
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
        
        # Also fix workflow if needed
        workflow_path = Path(".github/workflows/deploy.yml")
        if workflow_path.exists():
            content = workflow_path.read_text()
            if "--platform linux/amd64" not in content:
                content = content.replace("docker build", "docker build --platform linux/amd64")
                workflow_path.write_text(content)
        
        return True
    
    def fix_workload_identity(self):
        self.log("🔧 Verifying Workload Identity...")
        run_cmd(f"gcloud projects add-iam-policy-binding {self.gcp_project} "
                f"--member=principalSet://iam.googleapis.com/projects/{self.project_num}/"
                f"locations/global/workloadIdentityPools/github-actions-pool/"
                f"attribute.repository/KishoreKu/slackbot-gcp-mcp-server "
                f"--role=roles/iam.workloadIdentityUser 2>/dev/null")
        return True
    
    def push_fix(self, fix_description):
        self.log(f"📤 Pushing fix: {fix_description}")
        
        run_cmd("git add -A")
        
        code, out, _ = run_cmd("git diff --cached --stat")
        if not out.strip():
            self.log("No changes to push")
            return False
        
        run_cmd(f'git commit -m "Auto-fix: {fix_description}"')
        run_cmd("git push origin master")
        
        self.log(f"✅ Fix pushed: {fix_description}")
        return True
    
    def process_failure(self, alert):
        issues = alert.get("issues", [])
        run_id = alert.get("run_id", "unknown")
        
        self.log(f"📋 Processing failure for run {run_id}")
        self.log(f"   Issues detected: {issues}")
        
        fixes_applied = []
        
        # Map issues to fix functions
        issue_map = {
            "IAM_API_DISABLED": (self.fix_iam_api, "Enable IAM API"),
            "ARTIFACT_REGISTRY_PERMISSION": (self.fix_artifact_registry, "Artifact Registry permissions"),
            "SERVICE_ACCOUNT_PERMISSION": (self.fix_service_account_permission, "Service Account permissions"),
            "PYTHON_DEPENDENCY": (self.fix_python_dependencies, "Python dependencies"),
            "BUILD_FAILED": (self.fix_python_dependencies, "Python dependencies"),
            "AUTH_FAILED": (self.fix_workload_identity, "Workload Identity"),
        }
        
        for issue in issues:
            if issue in issue_map:
                fix_func, fix_desc = issue_map[issue]
                try:
                    fix_func()
                    fixes_applied.append(fix_desc)
                except Exception as e:
                    self.log(f"   Failed to apply {fix_desc}: {e}")
        
        if fixes_applied:
            self.log(f"Applied fixes: {fixes_applied}")
            time.sleep(3)
            
            if self.push_fix(", ".join(fixes_applied)):
                self.log("Waiting for next workflow run...")
                time.sleep(90)  # Wait for CI to run
                return True
        
        return False
    
    def run(self):
        print("="*60)
        print("🚀 CI/CD ORCHESTRATOR AGENT")
        print("="*60)
        print(f"Monitoring: {self.repo}")
        print(f"Notification file: {NOTIFICATION_FILE}")
        print("Press Ctrl+C to stop\n")
        
        consecutive_failures = 0
        max_retries = 15
        
        while True:
            try:
                alert = self.check_notification()
                
                if alert:
                    self.log("⚠️ Workflow failure detected!")
                    
                    if self.process_failure(alert):
                        # Clear the notification after processing
                        self.clear_notification()
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        self.log(f"Could not fix (attempt {consecutive_failures}/{max_retries})")
                        
                        if consecutive_failures >= max_retries:
                            self.log("❌ Max retries reached - stopping")
                            break
                else:
                    # Check if current workflow is passing
                    code, out, _ = run_cmd(f"gh run list --repo {self.repo} --limit 1")
                    if code == 0 and out.strip():
                        parts = out.strip().split('\n')
                        if len(parts) >= 2:
                            status = parts[1].split()[0]
                            conclusion = parts[1].split()[1] if len(parts[1].split()) > 1 else ""
                            
                            if status == "completed" and conclusion == "success":
                                print("✅ Workflow passing!")
                            elif status == "in_progress":
                                self.log("🔄 CI/CD running...")
                
                time.sleep(30)
                
            except KeyboardInterrupt:
                print("\n👋 Orchestrator stopped")
                break
            except Exception as e:
                self.log(f"Error: {e}")
                time.sleep(30)


if __name__ == "__main__":
    # Change to project directory
    os.chdir("/Users/kishorekumar/CascadeProjects/slackbot-gcp-mcp-server")
    
    orchestrator = CI/CDOrchestrator()
    orchestrator.run()