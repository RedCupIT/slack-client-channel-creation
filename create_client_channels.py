#!/usr/bin/env python3
"""Provision the standard Slack channels for a new RCIT customer.

Creates the channels for the selected preset, sets each channel's purpose, and
invites the Pylon app to every channel so client work is tracked as tickets.

Standard library only (urllib) — no pip install required, runs as-is in CI.

Usage:
    SLACK_USER_TOKEN=xoxp-... \\
        python create_client_channels.py \\
        --slug acme-corp --display-name "Acme Corp" --preset standard

Inputs may also be supplied via environment variables (used by the GitHub
Actions workflow): CUSTOMER_NAME, CUSTOMER_DISPLAY_NAME, CHANNEL_PRESET.

Auth token (channel create + purpose + Pylon invite): the script prefers
SLACK_USER_TOKEN (a user/xoxp token) and falls back to SLACK_BOT_TOKEN. A user
token from a Workspace Admin is required to create *private* channels when the
workspace restricts private-channel creation to admins/owners — a bot token
hits 'restricted_action' in that case. The channels are then owned by that user.

Pylon's Slack member id is read from PYLON_SLACK_USER_ID. If unset, the script
resolves it by scanning the workspace user list for the Pylon app/bot (requires
the users:read scope). Set PYLON_SLACK_USER_ID to skip the lookup.

Required token scopes (user token scopes if using SLACK_USER_TOKEN):
    channels:manage   create public channels + set purpose + invite
    groups:write      create private channels + invite
    groups:read       look up an existing private channel by name (name_taken)
    users:read        resolve the Pylon member id by name (only if
                      PYLON_SLACK_USER_ID is not provided)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

SLACK_API = "https://slack.com/api"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")

# Each entry: (name_template, is_private, purpose_template)
PRESETS = {
    "minimal": [
        ("client_{slug}-it-support", False,
         "Public IT support channel for {slug} end users and RCIT team."),
    ],
    "standard": [
        ("client_{slug}-it-support", False,
         "Public IT support channel for {slug} end users and RCIT team."),
        ("client_{slug}-it-support-private", True,
         "Private RCIT-only channel for internal {slug} IT coordination."),
        ("client_{slug}-hr-it-support", True,
         "Private channel for HR + IT onboarding/offboarding coordination."),
        ("client_{slug}_onboarding_offboarding", True,
         "Private channel for tracking onboarding and offboarding tickets for {slug}."),
    ],
    "full": [
        ("client_{slug}-it-support", False,
         "Public IT support channel for {slug} end users and RCIT team."),
        ("client_{slug}-it-support-private", True,
         "Private RCIT-only channel for internal {slug} IT coordination."),
        ("client_{slug}-hr-it-support", True,
         "Private channel for HR + IT onboarding/offboarding coordination."),
        ("client_{slug}_onboarding_offboarding", True,
         "Private channel for tracking onboarding and offboarding tickets for {slug}."),
        ("client_{slug}-devops", True,
         "Private channel for DevOps/infrastructure work scoped to {slug}."),
        ("client_{slug}-access-alerts", False,
         "Automated access change alerts for {slug} (Okta, Entra, etc.)."),
        ("client_{slug}-it-announcements", False,
         "IT announcements and maintenance notices for {slug} users."),
    ],
}

RESTRICTED_ACTION_HINT = (
    "    HINT: 'restricted_action' means a Slack workspace setting forbids the\n"
    "    bot from creating this channel — it is NOT a code or scope bug. A\n"
    "    Workspace Owner/Admin must allow it under Settings & administration ->\n"
    "    Workspace settings -> Permissions -> Channel management -> 'who can\n"
    "    create private channels', and include the rcit-channel-bot app (or set\n"
    "    it to allow all members). Public channels are unaffected."
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
    for _ in range(5):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(int(exc.headers.get("Retry-After", "2")))
                continue
            raise SlackError(f"{method} HTTP {exc.code}: {exc.read().decode('utf-8')}")
        if body.get("error") == "ratelimited":
            time.sleep(int(body.get("retry_after", 2)))
            continue
        return body
    raise SlackError(f"{method}: still rate limited after retries")


def resolve_pylon_user_id(token, explicit):
    """Return the Slack member id for the Pylon app, or None.

    Prefers the explicit id (PYLON_SLACK_USER_ID). Otherwise scans the workspace
    user list for an app/bot whose name looks like Pylon. Requires users:read.
    """
    if explicit:
        return explicit
    cursor = ""
    while True:
        resp = slack_api(token, "users.list", {"limit": 200, "cursor": cursor})
        if not resp.get("ok"):
            print(f"    WARN: could not look up Pylon user (users.list: {resp.get('error')}).")
            return None
        for member in resp.get("members", []):
            if member.get("deleted"):
                continue
            profile = member.get("profile", {})
            names = [
                member.get("name", ""),
                member.get("real_name", ""),
                profile.get("real_name", ""),
                profile.get("display_name", ""),
            ]
            if any("pylon" in (n or "").lower() for n in names):
                return member.get("id")
        cursor = resp.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            return None


def find_channel_id(token, name):
    """Look up an existing channel id by name (public + private, incl. archived)."""
    cursor = ""
    while True:
        resp = slack_api(
            token,
            "conversations.list",
            {
                "types": "public_channel,private_channel",
                "exclude_archived": False,
                "limit": 1000,
                "cursor": cursor,
            },
        )
        if not resp.get("ok"):
            return None
        for ch in resp.get("channels", []):
            if ch.get("name") == name:
                return ch.get("id")
        cursor = resp.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            return None


def ensure_channel(token, name, is_private):
    """Create the channel; return (channel_id, status, error).

    status is one of: created, exists, error.
    """
    resp = slack_api(token, "conversations.create", {"name": name, "is_private": is_private})
    if resp.get("ok"):
        return resp["channel"]["id"], "created", None
    error = resp.get("error")
    if error == "name_taken":
        cid = find_channel_id(token, name)
        if cid:
            return cid, "exists", None
        return None, "error", "name_taken but channel not found"
    return None, "error", error


def set_purpose(token, channel_id, purpose):
    resp = slack_api(token, "conversations.setPurpose", {"channel": channel_id, "purpose": purpose})
    return bool(resp.get("ok")) or resp.get("error")


def invite_user(token, channel_id, user_id):
    """Invite a user to a channel; idempotent."""
    resp = slack_api(token, "conversations.invite", {"channel": channel_id, "users": user_id})
    if resp.get("ok"):
        return "invited"
    error = resp.get("error")
    if error in ("already_in_channel", "cant_invite_self"):
        return "already in channel"
    return f"error: {error}"


def build_channels(preset, slug, display_name):
    rows = PRESETS[preset]
    channels = []
    for name_tpl, is_private, purpose_tpl in rows:
        channels.append({
            "name": name_tpl.format(slug=slug),
            "is_private": is_private,
            "purpose": purpose_tpl.format(slug=display_name or slug),
        })
    return channels


def main():
    parser = argparse.ArgumentParser(description="Provision Slack channels for a new RCIT customer.")
    parser.add_argument("--slug", default=os.environ.get("CUSTOMER_NAME", ""),
                        help="Customer slug (lowercase, hyphens). Defaults to $CUSTOMER_NAME.")
    parser.add_argument("--display-name", default=os.environ.get("CUSTOMER_DISPLAY_NAME", ""),
                        help="Human-readable customer name. Defaults to $CUSTOMER_DISPLAY_NAME.")
    parser.add_argument("--preset", default=os.environ.get("CHANNEL_PRESET", "standard"),
                        choices=sorted(PRESETS), help="Channel preset. Defaults to $CHANNEL_PRESET or 'standard'.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without calling Slack.")
    args = parser.parse_args()

    slug = args.slug.strip().lower()
    display_name = args.display_name.strip()

    if not SLUG_RE.match(slug):
        print(f"ERROR: invalid customer slug: '{slug}'", file=sys.stderr)
        print("       must be lowercase alphanumeric with hyphens, no leading/trailing hyphen.", file=sys.stderr)
        return 2

    channels = build_channels(args.preset, slug, display_name)

    if args.dry_run:
        print(f"=== DRY RUN — preset '{args.preset}' for '{display_name or slug}' ===")
        for ch in channels:
            kind = "private" if ch["is_private"] else "public"
            print(f"  #{ch['name']} ({kind}) — {ch['purpose']}")
        print("  + invite Pylon to each channel")
        return 0

    token = os.environ.get("SLACK_USER_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("ERROR: neither SLACK_USER_TOKEN nor SLACK_BOT_TOKEN is set.", file=sys.stderr)
        return 2
    token_kind = "user" if os.environ.get("SLACK_USER_TOKEN") else "bot"
    print(f"Using {token_kind} token for channel creation.")

    pylon_user_id = resolve_pylon_user_id(token, os.environ.get("PYLON_SLACK_USER_ID", "").strip())
    if pylon_user_id:
        print(f"Pylon Slack member id: {pylon_user_id}\n")
    else:
        print("WARN: Pylon Slack member id not found — channels will be created "
              "without inviting Pylon. Set PYLON_SLACK_USER_ID to enable.\n")

    created, existing, failed = [], [], []
    restricted_seen = False

    for ch in channels:
        name, is_private, purpose = ch["name"], ch["is_private"], ch["purpose"]
        kind = "private" if is_private else "public"
        print(f"> #{name} ({kind})")

        cid, status, error = ensure_channel(token, name, is_private)
        print(f"    create: {status}" + (f" — {error}" if error else ""))

        if status == "error":
            failed.append(name)
            if error == "restricted_action" and not restricted_seen:
                print(RESTRICTED_ACTION_HINT)
                if token_kind == "bot":
                    print("    Using SLACK_USER_TOKEN (a Workspace Admin's xoxp token) "
                          "avoids this without changing the workspace setting.")
                restricted_seen = True
            print()
            continue

        print(f"    purpose: {set_purpose(token, cid, purpose)}")
        if pylon_user_id:
            print(f"    pylon  : {invite_user(token, cid, pylon_user_id)}")
        print()

        (created if status == "created" else existing).append(name)

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
