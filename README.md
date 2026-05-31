# RCIT — Slack Channel Automation for New Customers

Automates creation of standard Slack channels whenever RCIT onboards a new client.
Triggered manually via GitHub Actions `workflow_dispatch` — no code changes needed per customer.

---

## Prerequisites

Before you start, make sure you have:
- **Slack workspace admin access** (needed to create and install the bot app)
- **GitHub repo access** with permission to add repository secrets and run Actions

---

## Setup (one-time)

### 1. Create a Slack Bot Token

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From Scratch**
2. Name it something like `rcit-channel-bot` and select your workspace
3. Under **OAuth & Permissions**, add these **Bot Token Scopes**:
   - `channels:manage` — create public channels
   - `groups:write` — create private channels
   - `chat:write` — post summary messages
4. Click **Install to Workspace** → copy the **Bot OAuth Token** (starts with `xoxb-...`)

### 2. Add the token to GitHub Secrets

In your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret Name | Value |
|---|---|
| `SLACK_BOT_TOKEN` | `xoxb-your-token-here` |

### 3. Invite the bot to your internal channel

The workflow posts a completion summary to `#team_rcit-internal` after each run.
You must invite the bot there first — otherwise the notification will silently fail.

In Slack, open `#team_rcit-internal` and run:
```
/invite @rcit-channel-bot
```

That's it — the workflow file is already included in this repo, so no additional setup is needed.

---

## Usage

1. Go to your GitHub repo → **Actions** tab
2. Select **"New Customer Slack Channel Setup"** in the left sidebar
3. Click **"Run workflow"** (top right)
4. Fill in:
   - **Customer slug** — lowercase, hyphens only (e.g. `acme-corp`)
   - **Customer display name** — human-readable (e.g. `Acme Corp`)
   - **Channel preset** — choose from the options below
5. Click **Run workflow** — channels will be created within seconds

---

## Channel Presets

### `standard` (default — most new clients)
| Channel | Visibility |
|---|---|
| `client_{name}-it-support` | Public |
| `client_{name}-it-support-private` | Private |
| `client_{name}-hr-it-support` | Private |
| `client_{name}_onboarding_offboarding` | Private |

### `full` (clients with deeper engagement — DevOps, security alerts)
All of standard, plus:
| Channel | Visibility |
|---|---|
| `client_{name}-devops` | Private |
| `client_{name}-access-alerts` | Public |
| `client_{name}-it-announcements` | Public |

### `minimal` (trial / short-term engagements)
| Channel | Visibility |
|---|---|
| `client_{name}-it-support` | Public |

---

## Example

**Inputs:**
- Customer slug: `ignition-benefits`
- Display name: `Ignition Benefits`
- Preset: `standard`

**Channels created:**
- `#client_ignition-benefits-it-support` (public)
- `#client_ignition-benefits-it-support-private` (private)
- `#client_ignition-benefits-hr-it-support` (private)
- `#client_ignition-benefits_onboarding_offboarding` (private)

---

## Behavior Notes

- **Idempotent** — if a channel already exists (`name_taken`), it's skipped, not errored.
- **Purpose auto-set** — each channel gets a description set via API automatically.
- **Completion notification** — a summary is posted to `#team_rcit-internal` after every run.
- **Validation** — the slug is validated before any API calls are made.

---

## Brain Dump Channels (`#brew-*`) — INT-2477

In addition to client channels, this repo provisions the internal `#brew-<name>`
brain dump channels — one public channel per Red Cup IT staff member for thinking
out loud (inspired by Shopify's `#shhtobi`). Reactions over replies; not a
deliverables queue.

- **Roster**: [`brew_roster.json`](brew_roster.json) — channel name, display name,
  email, and Slack user ID for each staff member. Edit this file to add/remove people.
- **Script**: [`create_brew_channels.py`](create_brew_channels.py) — standard library
  only (no `pip install`). For each roster entry it creates the public channel
  (idempotent on `name_taken`), sets the topic
  (`Brain dump from <Name>. Lurk freely. Reactions over replies.`), invites the
  owner, and posts + pins a kickoff message.
- **Workflow**: **"Brew Brain Dump Channels (INT-2477)"** in the Actions tab.

### Run it

Via GitHub Actions (uses the existing `SLACK_BOT_TOKEN` secret):
1. Actions → **Brew Brain Dump Channels (INT-2477)** → **Run workflow**
2. `mode`: `dry-run` (default, prints planned actions) or `execute` (applies changes)
3. `announce_channel` (optional): e.g. `general` to post the launch announcement

Locally:
```bash
SLACK_BOT_TOKEN=xoxb-... python create_brew_channels.py            # dry run (default)
SLACK_BOT_TOKEN=xoxb-... python create_brew_channels.py --execute  # apply
SLACK_BOT_TOKEN=xoxb-... python create_brew_channels.py --execute --announce general
```

### Required scopes & limitations

- Token scopes: `channels:manage` and `chat:write` (the README setup above). Pinning
  the kickoff message additionally needs **`pins:write`** — without it the kickoff
  is still posted, only the pin is skipped (logged, non-fatal).
- **Channel owner**: the bot is the channel *creator*. Slack Business+ has no API to
  transfer channel ownership to another user (that requires Enterprise Grid admin
  APIs), so each person is **invited as a member** rather than set as owner. "Owner
  posts first message within 48 hours" remains a manual step for each person.

---

## Future Enhancements (optional)
- Trigger from Pylon webhook when a new account is created (instead of manual dispatch)
- Auto-invite RCIT team members to the new private channels
- Create matching Notion SOP page for the client automatically
- Post a welcome message in `it-support` with RCIT contact info
