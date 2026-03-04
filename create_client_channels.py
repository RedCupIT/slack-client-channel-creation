#!/usr/bin/env python3

# ============================================================
#  SLACK CLIENT CHANNEL SETUP SCRIPT
#  Usage: python create_client_channels.py <client-name>
#  Example: python create_client_channels.py acmecorp
# ============================================================

import sys
import json
import requests

# ── CONFIGURATION ───────────────────────────────────────────
SLACK_TOKEN = "xoxb-your-token-here"        # Need to replace
# ────────────────────────────────────────────────────────────

def create_channel(token: str, name: str, is_private: bool, description: str):
    print(f"Creating: #{name} (private: {is_private})")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Create channel
    response = requests.post(
        "https://slack.com/api/conversations.create",
        headers=headers,
        json={"name": name, "is_private": is_private}
    )
    data = response.json()

    if data.get("ok") and data.get("channel", {}).get("id"):
        channel_id = data["channel"]["id"]
        print(f"   OK - Created #{name} (ID: {channel_id})")

        # Set channel description/purpose
        requests.post(
            "https://slack.com/api/conversations.setPurpose",
            headers=headers,
            json={"channel": channel_id, "purpose": description}
        )
        print("   Description set")
    else:
        error = data.get("error", "unknown error")
        print(f"   FAILED to create #{name} - {error}")

    print()


def main():
    if len(sys.argv) < 2:
        print("Please provide a client name. Example: python create_client_channels.py acmecorp")
        sys.exit(1)

    client = sys.argv[1].lower()

    print(f"Creating Slack channels for client: {client}")
    print("------------------------------------------------")

    # ============================================================
    #  CHANNEL NAMING CONVENTIONS
    # ============================================================
    channels = [
        {
            "name":        f"client-{client}-it-support",
            "is_private":  False,
            "description": f"IT support channel for {client} staff to reach out to RCIT.",
            "label":       "public"
        },
        {
            "name":        f"client-{client}-it-support-private",
            "is_private":  True,
            "description": f"Private channel for {client} leadership to communicate with RCIT.",
            "label":       "private"
        },
        {
            "name":        f"client-{client}-it-announcements",
            "is_private":  False,
            "description": f"IT announcements and updates for {client}.",
            "label":       "public"
        },
        {
            "name":        f"intl-{client}-it-support",
            "is_private":  False,
            "description": f"Internal RCIT channel for {client} account - staff only.",
            "label":       "public"
        },
    ]

    # ────────────────────────────────────────────────────────────
    #  CREATE THE CHANNELS
    # ────────────────────────────────────────────────────────────
    for ch in channels:
        create_channel(SLACK_TOKEN, ch["name"], ch["is_private"], ch["description"])

    print("------------------------------------------------")
    print(f"Done! All channels created for client: {client}")
    print()
    print("Channels created:")
    for ch in channels:
        print(f"  #{ch['name']} ({ch['label']})")


if __name__ == "__main__":
    main()
