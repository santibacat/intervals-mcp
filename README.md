# Intervals MCP

Local Python client and MCP server for analyzing an Intervals.icu account, building AI-assisted training plans, and applying only managed drafts to the calendar after explicit confirmation.

Intervals.icu is the operational source of truth. When an account is connected to Garmin Connect, this MCP can also read the Garmin-derived activities and wellness data exposed by Intervals.icu. It does not call the Garmin API directly.

## Quick start

Install the project and create your local configuration:

```bash
uv sync --dev
cp .env.example .env
```

Set `INTERVALS_API_KEY` in `.env`, then register the local MCP server with Codex:

```bash
codex mcp add intervals_icu -- \
  uv run --directory /absolute/path/to/intervals-mcp intervals-mcp
```

Restart Codex if it was already open, then use `/mcp` to confirm that `intervals_icu` is connected. You can now ask Codex things such as:

```text
Read my private training context and list my managed Intervals.icu draft plans.
Read my recent training context and summarize the last two weeks.
Create a draft plan for next week, but show me the preview before writing anything.
```

The server is local and communicates over `stdio`. It does not send data to a separate service. Read operations can run immediately; every mutation first returns a preview and requires a second call with `confirmed=true` after explicit approval. Scheduling can make workouts available for Garmin synchronization, but Garmin delivery must still be verified separately.

For Claude Code, use the equivalent command in [Connect to Claude Code](#connect-to-claude-code). For detailed setup, safety rules, and development commands, continue below.

```text
Codex or Claude Code
        │
        ▼ MCP (stdio)
intervals-mcp ──────── Intervals.icu API
                              │
                              ▼
                  Library: [IA] ...
                              │
                       athlete review
                              │
                    apply plan in Intervals
                              │
                              ▼
                    Calendar → Garmin
```

## Why a skill plus MCP

- The **skill** teaches the LLM the training workflow, workout syntax, and safety guardrails.
- The **MCP** keeps API access outside the conversation context and exposes typed operations.
- `PERSONAL.md` stores stable athlete goals, availability, and preferences locally. It is intentionally ignored by Git.
- The Python client verifies that writes belong to the managed namespace.
- Intervals.icu remains the dashboard, calendar, and analysis system.

The MCP provides a deterministic safety boundary around the API: it avoids exposing credentials in prompts and does not provide unrestricted calendar CRUD.

## Current capabilities

The server exposes tools for:

- Reading private athlete context with `get_personal_context` and `set_personal_fact`.
- Reading activities, wellness, and calendar data with `get_training_context` for ranges up to 180 days.
- Listing and reading managed plans with `list_draft_plans` and `get_draft_plan`.
- Creating, cloning, renaming, and editing private managed library plans.
- Adding and updating structured workouts inside managed plans.
- Applying a managed plan to the calendar from an exact future date with `schedule_draft_plan`.
- Removing only calendar copies from a managed application with `unschedule_draft_plan`.
- Serving `intervals://safety-policy`, `intervals://personal-context`, and `intervals://draft-plans` resources.
- Serving the `draft_training_week` MCP prompt.

Generic event create, edit, and delete operations are not exposed. Every mutation first returns a preview with `confirmed=false`; it can only proceed with `confirmed=true` after explicit approval.

## Local personal memory

`PERSONAL.md` is the active athlete's private memory and is ignored by Git. The skill requires reading it before analyzing or changing a plan. Durable information can be stored through `set_personal_fact`; reusing the same key replaces the previous value.

Store only goals, events, recurring availability, preferences, performance markers, equipment, integrations, and training constraints. Never store examples, guesses, API keys, passwords, tokens, payment data, or sensitive health information unless explicitly requested.

## Requirements

- Python 3.13 or newer.
- [`uv`](https://docs.astral.sh/uv/).
- An Intervals.icu account and personal API key.
- Codex or Claude Code to consume the MCP.

## Setup

```bash
uv sync --dev
cp .env.example .env
```

Then set `INTERVALS_API_KEY` in the local `.env` file. Never commit `.env` or paste the key into a conversation. Personal Intervals.icu authentication uses HTTP Basic with the literal username `API_KEY`; the client configures this automatically.

To check read access:

```bash
uv run intervals-mcp-cli doctor
```

The command only lists library containers and does not write anything.

## Run and inspect the MCP

```bash
uv run intervals-mcp
```

The process waits for JSON-RPC messages on `stdin`; this is expected. For visual inspection, use:

```bash
uv run mcp dev src/intervals_mcp/mcp_server.py
npx -y @modelcontextprotocol/inspector uv run intervals-mcp
```

## Connect to Codex

```bash
codex mcp add intervals_icu -- \
  uv run --directory /absolute/path/to/intervals-mcp intervals-mcp
codex mcp list
```

Use `/mcp` inside Codex to inspect the server and its tools. The equivalent configuration is:

```toml
[mcp_servers.intervals_icu]
command = "uv"
args = ["run", "intervals-mcp"]
cwd = "/absolute/path/to/intervals-mcp"
startup_timeout_sec = 20
tool_timeout_sec = 90
default_tools_approval_mode = "writes"
```

The `writes` setting makes Codex request approval for mutating tools. The server also requires its own `confirmed=true`.

### Enable the skill in Codex

```bash
mkdir -p .agents/skills
ln -s ../../skills/manage-intervals-icu .agents/skills/manage-intervals-icu
```

## Connect to Claude Code

```bash
claude mcp add --transport stdio --scope local intervals_icu -- \
  uv run --directory /absolute/path/to/intervals-mcp intervals-mcp
claude mcp list
```

For a project-shared command, use `--scope project`, which creates `.mcp.json`. Do not put the API key in that file; every user must keep a local `.env`.

Claude Code discovers project skills under `.claude/skills`:

```bash
mkdir -p .claude/skills
ln -s ../../skills/manage-intervals-icu .claude/skills/manage-intervals-icu
```

## Recommended first run

1. Run `doctor`.
2. Connect the MCP to Codex or Claude Code.
3. Ask it to use the Intervals.icu skill and list managed drafts.
4. Request recent training context and verify that no secrets are returned.
5. Create an empty plan with `confirmed=false` and inspect the preview.
6. Approve the second call with `confirmed=true`.
7. Open Intervals.icu and confirm that a private `[IA] ...` plan appears.
8. Add one easy session and verify that Intervals.icu interprets its steps correctly.
9. Preview `schedule_draft_plan`, review dates and conflicts, and approve only when ready.

## Safety model

- A managed plan must have `type == PLAN` and a description containing `[intervals-mcp:managed]`.
- `[IA]` is only a display prefix; security does not depend on the human-facing name.
- Every edit requires the latest remote content hash.
- Only complete managed-plan applications can be scheduled or removed; generic event CRUD is unavailable.
- Scheduling rejects past dates, empty plans, stale hashes, and duplicate applications.
- Existing events in the target dates require additional approval through `allow_calendar_conflicts=true`.
- Unscheduling resolves IDs by `plan_folder_id` and application range, then deletes only those exact events after confirmation.
- The server never prints the API key or authentication responses.
- Scheduling may make eligible workouts available for Garmin synchronization; Garmin delivery must be reported as pending until verified.

## Development

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
uv run python scripts/smoke_mcp.py
```

HTTP tests use a mocked Intervals.icu service. They do not need credentials or modify a real account.

## Project status

The client and MCP are implemented and tested against the current public Intervals.icu contract. A manual test with a real API key is still needed to verify exactly how the library displays plans and processes workouts in a specific account.
