---
name: manage-intervals-icu
description: Safely use persistent personal athlete context plus Intervals.icu training history, wellness, calendar, workout library, and IA-managed plans through the intervals_icu MCP server. Use when an athlete asks to remember training preferences, analyze recent endurance training, create or revise a running/cycling/swimming/triathlon plan, construct Intervals.icu workout syntax, compare planned versus completed work, or schedule an approved managed plan from an exact future date before Garmin synchronization.
---

# Manage Intervals.icu

Use the `intervals_icu` MCP server for live data and mutations. Keep the skill as procedural guidance; never handle or request the API key in conversation.

## Personal context first

1. Call `get_personal_context` or read `intervals://personal-context` before every analysis, plan creation, revision, scheduling, or removal.
   Use `get_athlete_profile` when body or health metrics are relevant.
2. Treat it as durable user-provided context, but prefer a newer explicit statement when the conversation conflicts with memory.
3. When the user states a durable goal, recurring availability, preference, performance marker, equipment fact, or constraint, call `set_personal_fact` before finishing. Reuse a stable `snake_case` key so corrections replace old values.
4. Do not store hypotheticals or examples. “I never train Sunday” is durable; “for example, imagine I cannot train Sunday” is not.
5. Never store credentials, payment data, unrelated personal data, inferred facts, or diagnoses. Store health information only when the user explicitly asks to remember it.
6. Do not merge facts about different people. If athlete identity is ambiguous, flag it and ask before changing `athlete_identity`.

## Non-negotiable boundary

- Read activities, wellness, calendar events, zones, and library data as needed.
- Use `get_performance_curves` for power, pace, and heart-rate duration curves; keep the sport and period explicit.
- Write only managed library plans whose description contains `[intervals-mcp:managed]`. Use `[IA]` as a short display convention for new names, not as the ownership credential.
- Apply or remove only a complete managed-plan application through `schedule_draft_plan` or `unschedule_draft_plan`. Never create, edit, or delete arbitrary calendar events.
- Treat relative dates such as “next Monday” as unresolved until converted to an ISO date and shown to the user.
- Never claim a workout reached Garmin. Scheduling only makes eligible workouts available for Intervals.icu's automatic synchronization.
- Never modify plans or workouts outside the managed namespace.
- Preview every mutation. Call a mutating tool with `confirmed=true` only after the user explicitly approves the displayed change.
- Re-read a draft before editing and pass its latest `content_hash`. On a conflict, stop and re-read instead of overwriting.
- Ask before cloning or removing content. Prefer cloning a plan before substantial revision.

## Choose the workflow

### Analyze training

1. Call `get_training_context` for 6-12 recent weeks, using ISO dates.
2. Summarize volume and load separately for each sport.
3. Distinguish recorded facts from inference.
4. Treat missing wellness fields as unknown, not normal.
5. Flag pain, illness, unusual fatigue, abrupt load changes, and insufficient data; do not diagnose.

### Create a draft plan

1. Collect goal, event date/priority, current volume, available days/hours, preferred long-session days, zones, equipment, constraints, injury/illness status, and recent experience.
2. Read recent context before prescribing intensities.
3. Explain the proposed weekly structure and load progression.
4. Build workouts using native Intervals.icu text syntax. Read [workout-syntax.md](references/workout-syntax.md) before authoring unfamiliar targets or repetitions.
5. Call `create_draft_plan` without confirmation to obtain a preview.
6. Show the preview and request approval.
7. Repeat with `confirmed=true`, then add workouts one at a time using the returned current hash after every mutation.
8. Validate the resulting plan holistically using [planning-guardrails.md](references/planning-guardrails.md).
9. Keep the plan in the library unless the user explicitly asks to schedule it.

### Schedule an approved draft

1. Re-read the plan immediately before scheduling and use its latest `content_hash`.
2. Resolve the requested start day to an exact ISO date and show the derived end date.
3. Call `schedule_draft_plan` with `confirmed=false` and inspect existing calendar events.
4. If conflicts exist, explain them. Set `allow_calendar_conflicts=true` only after the user explicitly accepts those overlaps.
5. Show the final preview and obtain explicit approval for the calendar write.
6. Repeat with `confirmed=true`.
7. Report event count and dates, state that calendar changed, and describe Garmin as pending automatic sync rather than completed.

### Remove a scheduled draft

1. Confirm which managed plan application and start date the user means.
2. Call `unschedule_draft_plan` with `confirmed=false` and verify its exact event count, IDs, and date range.
3. State explicitly that the calendar copies will be deleted while the library plan remains.
4. Obtain explicit approval, then repeat with `confirmed=true`.
5. Verify `remaining_event_count == 0` and report Garmin removal synchronization as pending.

### Revise a draft

1. Call `get_draft_plan` immediately before editing.
2. Explain the exact session-level change and its weekly effect.
3. For a large revision, call `clone_draft_plan` first after approval.
4. Preview the update with `confirmed=false`.
5. After explicit approval, repeat with `confirmed=true` and the latest hash.
6. Re-read the plan and report its new hash.

## API fallback

Prefer MCP because it keeps credentials out of model context and enforces the namespace. If MCP is unavailable, diagnose its installation using the repository README. Do not improvise write calls with `curl`. Read [api-reference.md](references/api-reference.md) only when maintaining or debugging the integration.

## Output standard

For every proposed plan, include:

- objective and assumptions;
- sessions by day, sport, purpose, duration, target, and structured steps;
- weekly totals by sport;
- key intensity and recovery decisions;
- validation warnings and missing data;
- whether the result is previewed, present only in the library, or scheduled on the calendar;
- explicit and separate calendar and Garmin synchronization states.
