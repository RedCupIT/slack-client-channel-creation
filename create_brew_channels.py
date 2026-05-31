#!/usr/bin/env python3
"""Roll out Red Cup IT #brew-* brain dump channels (INT-2477).

Creates one public "brain dump" channel per staff member from a roster file,
sets the channel topic, invites the owner, and posts + pins a kickoff message
explaining the norm.

Standard library only (urllib) — no pip install required, runs as-is in CI.

Usage:
    SLACK_BOT_TOKEN=xoxb-... python create_brew_channels.py            # dry run (default)
    SLACK_BOT_TOKEN=xoxb-... python create_brew_channels.py --execute  # actually create
    SLACK_BOT_TOKEN=xoxb-... python create_brew_channels.py --execute --announce general

Required bot token scopes: channels:manage, chat:write. For pinning the kickoff
message you also need pins:write (the script degrades gracefully without it).
channels:history lets a re-run find an already-posted kickoff and pin it instead
of posting a duplicate; without it a re-run re-posts the kickoff.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

SLACK_API = "https://slack.com/api"

TOPIC_TEMPLATE = "Brain dump from {name}. Lurk freely. Reactions over replies."

KICKOFF_TEMPLATE = (
    ":coffee: *Welcome to #{channel} — {name}'s brain dump channel*\n\n"
    "This is {name}'s space to think out loud: what they're working on, "
    "half-formed ideas, things they want to change. The `brew-` prefix means "
    "ideas still _brewing_ — not finished.\n\n"
    "*How this works*\n"
    "• Public — anyone can lurk. Join freely, leave freely.\n"
    "• Reactions over replies. :+1: :eyes: :fire: encouraged.\n"
    "• Not a deliverables queue. Not a request inbox. No pressure to respond.\n"
    "• {first_name} — drop your first brain dump within 48 hours :smile:\n\n"
    "_Inspired by Shopify's `#shhtobi` pattern._"
)

ANNOUNCEMENT = (
    ":coffee: *Introducing #brew-* — brain dump channels for the whole team*\n\n"
    "Every Red Cup IT staff member now has a public `#brew-<name>` channel: a "
    "space to think out loud about what you're working on, half-formed ideas, and "
    "things you'd like to change. Inspired by Shopify's `#shhtobi` pattern.\n\n"
    "*Etiquette*\n"
    "• They're public — lurk freely, join the ones you care about, leave anytime.\n"
    "• Reactions over replies. No pressure to respond.\n"
    "• Not a deliverables queue or a request inbox — just thinking out loud.\n\n"
    "*How to join:* search `brew-` in the channel browser and hop into whoever's "
    "brain you want to follow. Find your own `#brew-` channel and post your first "
    "brain dump this week. :brain:"
)


class SlackError(Exception):
    pass


def slack_api(token, method, payload):
    """POST to a Slack Web API method, returning the parsed JSON response.

    Retries on HTTP 429 honoring Retry-After.
    """
    url = f"{SLACK_API}/{method}"
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = int(exc.headers.get("Retry-After", "2"))
                time.sleep(retry_after)
                continue
            raise SlackError(f"{method} HTTP {exc.code}: {exc.read().decode('utf-8')}")
        if body.get("error") == "ratelimited":
            time.sleep(int(body.get("retry_after", 2)))
            continue
        return body
    raise SlackError(f"{method}: still rate limited after retries")


def find_channel_id(token, name):
    """Look up an existing channel id by name (paginates public + archived)."""
    cursor = ""
    while True:
        resp = slack_api(
            token,
            "conversations.list",
            {
                "types": "public_channel",
                "exclude_archived": False,
                "limit": 1000,
                "cursor": cursor,
            },
        )
        if not resp.get("ok"):
            raise SlackError(f"conversations.list: {resp.get('error')}")
        for ch in resp.get("channels", []):
            if ch.get("name") == name:
                return ch.get("id")
        cursor = resp.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            return None


def ensure_channel(token, name, dry_run):
    """Create the public channel; return (channel_id, status).

    status is one of: created, exists, error.
    """
    if dry_run:
        return None, "dry-run"
    resp = slack_api(token, "conversations.create", {"name": name, "is_private": False})
    if resp.get("ok"):
        return resp["channel"]["id"], "created"
    if resp.get("error") == "name_taken":
        cid = find_channel_id(token, name)
        if cid:
            return cid, "exists"
        return None, "error: name_taken but not found"
    return None, f"error: {resp.get('error')}"


def set_topic(token, channel_id, topic, dry_run):
    if dry_run:
        return True
    resp = slack_api(token, "conversations.setTopic", {"channel": channel_id, "topic": topic})
    return bool(resp.get("ok")) or resp.get("error")


def invite_user(token, channel_id, user_id, dry_run):
    if dry_run:
        return True
    resp = slack_api(token, "conversations.invite", {"channel": channel_id, "users": user_id})
    if resp.get("ok"):
        return True
    # already_in_channel is fine and idempotent
    if resp.get("error") in ("already_in_channel", "cant_invite_self"):
        return True
    return resp.get("error")


def find_existing_kickoff(token, channel_id, channel_name):
    """Return the ts of an already-posted kickoff message, or None.

    Lets a re-run pin the existing kickoff instead of posting a duplicate.
    Requires channels:history; returns None (so the caller posts a fresh
    kickoff) if history is unavailable.
    """
    marker = f":coffee: *Welcome to #{channel_name} "
    resp = slack_api(token, "conversations.history", {"channel": channel_id, "limit": 100})
    if not resp.get("ok"):
        return None
    for msg in resp.get("messages", []):
        if msg.get("text", "").startswith(marker):
            return msg.get("ts")
    return None


def post_and_pin(token, channel_id, channel_name, text, dry_run):
    if dry_run:
        return None, "dry-run"
    ts = find_existing_kickoff(token, channel_id, channel_name)
    if ts:
        prefix = "kickoff exists"
    else:
        resp = slack_api(token, "chat.postMessage", {"channel": channel_id, "text": text})
        if not resp.get("ok"):
            return None, f"post error: {resp.get('error')}"
        ts = resp.get("ts")
        prefix = "posted"
    pin = slack_api(token, "pins.add", {"channel": channel_id, "timestamp": ts})
    if pin.get("ok") or pin.get("error") == "already_pinned":
        return ts, f"{prefix}+pinned"
    return ts, f"{prefix} (pin failed: {pin.get('error')})"


def main():
    parser = argparse.ArgumentParser(description="Create Red Cup IT #brew-* brain dump channels.")
    parser.add_argument("--roster", default=os.path.join(os.path.dirname(__file__), "brew_roster.json"))
    parser.add_argument("--execute", action="store_true", help="Actually create channels (default is dry run).")
    parser.add_argument("--announce", metavar="CHANNEL", default="", help="Post a launch announcement to this channel name (e.g. 'general').")
    args = parser.parse_args()

    dry_run = not args.execute

    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("ERROR: SLACK_BOT_TOKEN environment variable is not set.", file=sys.stderr)
        return 2

    with open(args.roster, encoding="utf-8") as fh:
        roster = json.load(fh)
    channels = roster["channels"]

    if dry_run:
        print("=== DRY RUN (no changes will be made). Pass --execute to apply. ===\n")
    else:
        # Verify token before mutating anything.
        auth = slack_api(token, "auth.test", {})
        if not auth.get("ok"):
            print(f"ERROR: auth.test failed: {auth.get('error')}", file=sys.stderr)
            return 2
        print(f"Authenticated as {auth.get('user')} on team {auth.get('team')}.\n")

    created, existing, failed = [], [], []

    for entry in channels:
        name = entry["channel"]
        display = entry["name"]
        topic = TOPIC_TEMPLATE.format(name=display)
        kickoff = KICKOFF_TEMPLATE.format(channel=name, name=display, first_name=entry["first_name"])

        print(f"▶ #{name}  ({display})")
        cid, status = ensure_channel(token, name, dry_run)
        print(f"    create: {status}")

        if dry_run:
            print(f"    topic : {topic}")
            print(f"    invite: {entry['user_id']} ({entry['email']})")
            print("    kickoff: would post + pin\n")
            continue

        if cid is None:
            print(f"    SKIPPED follow-up steps ({status})\n")
            failed.append(name)
            continue

        print(f"    topic : {set_topic(token, cid, topic, dry_run)}")
        print(f"    invite: {invite_user(token, cid, entry['user_id'], dry_run)}")
        ts, pin_status = post_and_pin(token, cid, name, kickoff, dry_run)
        print(f"    kickoff: {pin_status}")
        print(f"    -> https://redcupit.slack.com/archives/{cid}\n")

        (created if status == "created" else existing).append(name)

    if args.announce:
        print(f"▶ Launch announcement -> #{args.announce}")
        if dry_run:
            print("    (dry-run) would post announcement\n")
        else:
            cid = find_channel_id(token, args.announce)
            if not cid:
                print(f"    ERROR: could not find #{args.announce}\n")
            else:
                resp = slack_api(token, "chat.postMessage", {"channel": cid, "text": ANNOUNCEMENT})
                print(f"    {'posted' if resp.get('ok') else 'error: ' + str(resp.get('error'))}\n")

    print("=" * 48)
    print("Summary")
    print(f"  created : {len(created)}")
    print(f"  existing: {len(existing)}")
    print(f"  failed  : {len(failed)}")
    if failed:
        print("  failed channels: " + ", ".join(failed))
    print("=" * 48)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
