#!/usr/bin/env python3

# ============================================================
#  SLACK CLIENT CHANNEL SETUP SCRIPT
#  Usage: python create_client_channels.py <client-name>
#  Example: python create_client_channels.py acmecorp
# ============================================================

import sys
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ── CONFIGURATION ───────────────────────────────────────────
SLACK_TOKEN = "xoxb-your-token-here"        # Need to replace with real token
# ────────────────────────────────────────────────────────────

def create_channel(client: WebClient, name: str, is_private: bool, description: str, create_canvas: bool, client_name: str):
    print(f"Creating: #{name} (private: {is_private})")

    try:
        # Create channel
        response = client.conversations_create(name=name, is_private=is_private)
        channel_id = response["channel"]["id"]
        print(f"   OK - Created #{name} (ID: {channel_id})")

        # Set channel description/purpose
        client.conversations_setPurpose(channel_id=channel_id, purpose=description)
        print("   Description set")

        # Create canvas if create_canvas = "True"
        if create_canvas:
            client.conversations_canvases_create(
                channel_id=channel_id, 
                document_content={"type": "markdown", "markdown": IT_SUPPORT_CANVAS},
                title="How to Get IT Support")


    except SlackApiError as e:
        print(f"   FAILED to create #{name} - {e.response['error']}")

    print()


def main():
    if len(sys.argv) < 2:
        print("Please provide a client name. Example: python create_client_channels.py acmecorp")
        sys.exit(1)

    client_name = sys.argv[1].lower()
    client = WebClient(token=SLACK_TOKEN)

    print(f"Creating Slack channels for client: {client_name}")
    print("------------------------------------------------")

    # ============================================================
    #  Channel Attributes
    # ============================================================
    channels = [
        {
            "name":        f"client-{client_name}-it-support",
            "is_private":  False,
            "description": f"IT support channel for {client_name} staff to reach out to RCIT.",
            "create_canvas": True,
            "label":       "public"
        },
        {
            "name":        f"client-{client_name}-it-support-private",
            "is_private":  True,
            "description": f"Private channel for {client_name} leadership to communicate with RCIT.",
            "label":       "private"
        },
        {
            "name":        f"client-{client_name}-it-announcements",
            "is_private":  False,
            "description": f"IT announcements and updates for {client_name}.",
            "label":       "public"
        },
        {
            "name":        f"intl-{client_name}-it-support",
            "is_private":  False,
            "description": f"Internal RCIT channel for {client_name} account - staff only.",
            "label":       "public"
        },
    ]

# ────────────────────────────────────────────────────────────
# Canvas Templates
# ────────────────────────────────────────────────────────────

IT_SUPPORT_CANVAS = "Test Canvas Content Description"


    # ────────────────────────────────────────────────────────────
    #  Create the Channels
    # ────────────────────────────────────────────────────────────
    for ch in channels:
        create_channel(client, ch["name"], ch["is_private"], ch["description"], ch["create_canvas"], client_name)

    print("------------------------------------------------")
    print(f"Done! All channels created for client: {client_name}")
    print()
    print("Channels created:")
    for ch in channels:
        print(f"  #{ch['name']} ({ch['label']})")


if __name__ == "__main__":
    main()
