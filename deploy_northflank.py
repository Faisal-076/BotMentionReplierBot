"""
Automated Northflank Cloud Deployment Script
Creates Project and Combined Service with Dockerfile and Environment Variables.
"""

import json
import os
import sys
from pathlib import Path
import requests

NORTHFLANK_API_TOKEN = os.environ.get(
    "NORTHFLANK_API_TOKEN",
    "nf-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1dWlkIjoiNDAzMDM1MjItN2M2ZC00ZDNiLWJmYTAtYzdiYWY0MDQzZDg1IiwiZW50aXR5SWQiOiI2YWFmZjdmNjVkMTE4MjcyMDUxMmU1ZDUiLCJlbnRpdHlUeXBlIjoidGVhbSIsInRva2VuSWQiOiI2YWFmZjhmMTVkMTE4MjcyMDUxMmU1ZTEiLCJ0b2tlbkludGVybmFsSWQiOiJib3RtZW50aW9ucmVwbGllcmJvdGFwaSIsInJvbGVJZCI6IjZhYWZmN2Y3NWQxMTgyNzIwNTEyZTVkNiIsInJvbGVFbnRpdHlJZCI6IjZhYWZmN2Y2NWQxMTgyNzIwNTEyZTVkNSIsInJvbGVFbnRpdHlUeXBlIjoidGVhbSIsInJvbGVJbnRlcm5hbElkIjoib3duZXIiLCJ0eXBlIjoicmJhYyIsImlhdCI6MTc4OTkxNzQyNX0.0LKiwXMj95ghi6gJEFNCF7WSH_zp3n-sZuZCF6juT5Q",
)

BASE_URL = "https://api.northflank.com/v1"
PROJECT_ID = "bot-mention-replier"
GITHUB_REPO_URL = "https://github.com/Faisal-076/BotMentionReplierBot"

headers = {
    "Authorization": f"Bearer {NORTHFLANK_API_TOKEN}",
    "Content-Type": "application/json",
}


def deploy():
    print("==================================================")
    print("🚀 AUTOMATED NORTHFLANK CLUSTER DEPLOYMENT")
    print("==================================================")

    # 1. Read local bot tokens from .env
    env_file = Path(__file__).parent / ".env"
    bot_tokens = ""
    reply_templates = ""
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("BOT_TOKENS="):
                bot_tokens = line.split("=", 1)[1].strip()
            elif line.startswith("REPLY_TEMPLATES="):
                reply_templates = line.split("=", 1)[1].strip()

    # 2. Check or Create Project
    print(f"\n[1/3] Checking Project '{PROJECT_ID}'...")
    res = requests.get(f"{BASE_URL}/projects/{PROJECT_ID}", headers=headers)
    if res.status_code == 200:
        print(f"  ✓ Project '{PROJECT_ID}' is active in Europe!")
    else:
        print(f"  Creating Project '{PROJECT_ID}' in europe-west...")
        p_res = requests.post(
            f"{BASE_URL}/projects",
            headers=headers,
            json={
                "name": PROJECT_ID,
                "description": "Telegram Guest Mention Replier Bot Cluster",
                "region": "europe-west",
                "color": "#6366F1",
            },
        )
        if p_res.status_code not in (200, 201):
            print(f"  ❌ Project creation failed: {p_res.text}")
            sys.exit(1)
        print("  ✓ Project created successfully!")

    # 3. Create or Update Combined Service
    print(f"\n[2/3] Configuring Service 'replier-cluster' with Dockerfile from GitHub...")
    service_payload = {
        "name": "replier-cluster",
        "description": "Telegram Guest Replier Service & Web UI",
        "billing": {
            "deploymentPlan": "micro-10"
        },
        "deployment": {
            "instances": 1
        },
        "vcsData": {
            "projectType": "github",
            "projectUrl": GITHUB_REPO_URL,
            "projectBranch": "main"
        },
        "buildSettings": {
            "dockerfile": {
                "buildEngine": "kaniko",
                "dockerFilePath": "/Dockerfile",
                "dockerWorkDir": "/"
            }
        },
        "ports": [
            {
                "name": "web",
                "port": 8000,
                "protocol": "HTTP",
                "public": True
            }
        ]
    }

    svc_res = requests.post(
        f"{BASE_URL}/projects/{PROJECT_ID}/services/combined",
        headers=headers,
        json=service_payload,
    )

    print(f"Service creation response code: {svc_res.status_code}")
    res_data = svc_res.json()
    if svc_res.status_code in (200, 201):
        svc_id = res_data.get("data", {}).get("id", "replier-cluster")
        print(f"  ✓ Service '{svc_id}' successfully created and queued for build!")

        # 4. Set Environment Variables
        print(f"\n[3/3] Setting Environment Variables...")
        env_payload = {
            "variables": {
                "BOT_TOKENS": bot_tokens,
                "REPLY_MODE": "both",
                "PARSE_MODE": "HTML",
                "REPLY_DELAY": "0.0",
                "PORT": "8000",
                "REPLY_TEMPLATES": reply_templates,
            }
        }
        env_res = requests.post(
            f"{BASE_URL}/projects/{PROJECT_ID}/services/combined/{svc_id}/environment",
            headers=headers,
            json=env_payload,
        )
        if env_res.status_code in (200, 201):
            print("  ✓ Environment variables set successfully!")

        print("\n==================================================")
        print("🎉 SUCCESS! Your bot cluster is deploying on Northflank!")
        print("==================================================")
    else:
        err_msg = res_data.get("error", {}).get("message", svc_res.text)
        print(f"  ❌ Service creation returned: {err_msg}")
        if "payment method" in err_msg.lower():
            print("\n💡 ACTION REQUIRED:")
            print("Northflank requires adding a default payment method (card verification) to unlock compute resources on their platform.")


if __name__ == "__main__":
    deploy()
