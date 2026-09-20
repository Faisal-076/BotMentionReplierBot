"""
Automated Koyeb Cloud Deployment Script
Creates App and Service with GitHub source, Frankfurt (fra) region, and environment variables.
"""

import os
import sys
from pathlib import Path
import requests

KOYEB_API_TOKEN = os.environ.get("KOYEB_API_TOKEN", "")
BASE_URL = "https://app.koyeb.com/v1"
APP_NAME = "mention-replier"
GITHUB_REPO = "Faisal-076/BotMentionReplierBot"


def deploy(api_token: str):
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    print("==================================================")
    print("🚀 AUTOMATED KOYEB CLUSTER DEPLOYMENT")
    print("==================================================")

    # 1. Read bot tokens and templates from local .env
    env_file = Path(__file__).parent / ".env"
    bot_tokens = ""
    reply_templates = ""
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("BOT_TOKENS="):
                bot_tokens = line.split("=", 1)[1].strip()
            elif line.startswith("REPLY_TEMPLATES="):
                reply_templates = line.split("=", 1)[1].strip()

    # 2. Create or Get Koyeb App
    print(f"\n[1/3] Creating Koyeb App '{APP_NAME}'...")
    app_res = requests.post(f"{BASE_URL}/apps", headers=headers, json={"name": APP_NAME})
    app_id = ""
    if app_res.status_code in (200, 201):
        app_id = app_res.json().get("app", {}).get("id", APP_NAME)
        print("  ✓ App created successfully!")
    elif app_res.status_code == 409:  # Already exists
        print(f"  ✓ App '{APP_NAME}' already exists, continuing...")
        app_id = APP_NAME
    else:
        print(f"  App creation notice: {app_res.text}")
        app_id = APP_NAME

    # 3. Create Service in Frankfurt (fra)
    print(f"\n[2/3] Creating Service in Frankfurt (fra) from GitHub: {GITHUB_REPO}...")
    service_payload = {
        "app_id": app_id,
        "definition": {
            "name": "bot-service",
            "type": "WEB",
            "routes": [{"path": "/", "port": 8000}],
            "ports": [{"port": 8000, "protocol": "http"}],
            "env": [
                {"key": "BOT_TOKENS", "value": bot_tokens},
                {"key": "REPLY_MODE", "value": "both"},
                {"key": "PARSE_MODE", "value": "HTML"},
                {"key": "REPLY_DELAY", "value": "0.0"},
                {"key": "PORT", "value": "8000"},
                {"key": "REPLY_TEMPLATES", "value": reply_templates},
            ],
            "regions": ["fra"],
            "instance_types": [{"type": "nano"}],
            "docker": {
                "dockerfile": "Dockerfile",
            },
            "git": {
                "repository": GITHUB_REPO,
                "branch": "main",
                "build_command": "",
                "run_command": "",
            },
        },
    }

    svc_res = requests.post(
        f"{BASE_URL}/services", headers=headers, json=service_payload
    )
    print(f"Service creation status: {svc_res.status_code}")
    print(svc_res.text)

    if svc_res.status_code in (200, 201):
        print("\n==================================================")
        print("🎉 SUCCESS! Your bot is deploying on Koyeb (Frankfurt)!")
        print("==================================================")
    else:
        print(f"Deployment response: {svc_res.status_code}")


if __name__ == "__main__":
    token = sys.argv[1] if len(sys.argv) > 1 else KOYEB_API_TOKEN
    if not token:
        print("Usage: python deploy_koyeb.py <YOUR_KOYEB_API_TOKEN>")
        sys.exit(1)
    deploy(token)
