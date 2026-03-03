#!/bin/bash

# ============================================================
#  SLACK CLIENT CHANNEL SETUP SCRIPT
#  Usage: ./create_client_channels.sh <client-name>
#  Example: ./create_client_channels.sh acmecorp
# ============================================================

# ── CONFIGURATION ───────────────────────────────────────────
SLACK_TOKEN="xoxb-your-token-here"        # Need to replace
# ────────────────────────────────────────────────────────────

CLIENT=${1,,}  # takes input and converts input to lowercase

if [ -z "$CLIENT" ]; then
  echo "Please provide a client name. Example: ./create_client_channels.sh acmecorp"
  exit 1
fi

echo "Creating Slack channels for client: $CLIENT"
echo "------------------------------------------------"

# ============================================================
#  CHANNEL NAMING CONVENTIONS
# ============================================================

CH_EXTERNAL="client-${CLIENT}-it-support"              # Client-facing IT support (public)
CH_PRIVATE="client-${CLIENT}-it-support-private" # Leadership private channel (private)
CH_ANNOUNCEMENTS="client-${CLIENT}-it-announcements"   # Announcements channel (public)
CH_INTERNAL="intl-${CLIENT}-it-support"            # RCIT internal-only (public)

# ============================================================
#  CHANNEL DESCRIPTIONS
# ============================================================

DESC_EXTERNAL="IT support channel for $CLIENT staff to reach out to RCIT."
DESC_PRIVATE="Private channel for $CLIENT leadership to communicate with RCIT."
DESC_ANNOUNCEMENTS="IT announcements and updates for $CLIENT."
DESC_INTERNAL="Internal RCIT channel for $CLIENT account - staff only."

# ────────────────────────────────────────────────────────────
#  HELPER FUNCTION
# ────────────────────────────────────────────────────────────

create_channel() {
  local name=$1
  local is_private=$2
  local description=$3

  echo "Creating: #$name (private: $is_private)"

  RESPONSE=$(curl -s -X POST https://slack.com/api/conversations.create \
    -H "Authorization: Bearer $SLACK_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"$name\", \"is_private\": $is_private}")

  SUCCESS=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok','false'))")
  CHANNEL_ID=$(echo $RESPONSE | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('channel',{}).get('id',''))" 2>/dev/null)
  ERROR=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin).get('error',''))" 2>/dev/null)

  if [ "$SUCCESS" = "True" ] && [ -n "$CHANNEL_ID" ]; then
    echo "   OK - Created #$name (ID: $CHANNEL_ID)"

    curl -s -X POST https://slack.com/api/conversations.setPurpose \
      -H "Authorization: Bearer $SLACK_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"channel\": \"$CHANNEL_ID\", \"purpose\": \"$description\"}" > /dev/null

    echo "   Description set"
  else
    echo "   FAILED to create #$name - $ERROR"
  fi

  echo ""
}

# ────────────────────────────────────────────────────────────
#  CREATE THE CHANNELS - Run Helper Function create_channel() with parameters channel name, private [true/false], channel description
# ────────────────────────────────────────────────────────────

create_channel "$CH_EXTERNAL"       "false" "$DESC_EXTERNAL"
create_channel "$CH_PRIVATE"     "true"  "$DESC_PRIVATE"
create_channel "$CH_ANNOUNCEMENTS"  "false" "$DESC_ANNOUNCEMENTS"
create_channel "$CH_INTERNAL"       "false"  "$DESC_INTERNAL"

echo "------------------------------------------------"
echo "Done! All channels created for client: $CLIENT"
echo ""
echo "Channels created:"
echo "  #$CH_EXTERNAL (public)"
echo "  #$CH_PRIVATE (private)"
echo "  #$CH_ANNOUNCEMENTS (public)"
echo "  #$CH_INTERNAL (public)"
