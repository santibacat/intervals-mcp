# Intervals.icu API reference

Use this reference only when maintaining the client or diagnosing API behavior. Prefer the MCP tools for normal coaching work.

## Authentication

- Base URL: `https://intervals.icu/api/v1`
- Personal API key: HTTP Basic authentication with username `API_KEY` and the personal key as password.
- Athlete path: use athlete ID `0` for the athlete associated with the credential.
- Never place credentials in prompts, logs, checked-in config, URLs, or tool results.

## Read endpoints used

| Purpose | Method and path |
|---|---|
| List library containers | `GET /athlete/{id}/folders` |
| List library workouts | `GET /athlete/{id}/workouts` |
| Activities | `GET /athlete/{id}/activities?oldest=...&newest=...` |
| Wellness | `GET /athlete/{id}/wellness?oldest=...&newest=...` |
| Calendar context | `GET /athlete/{id}/events?oldest=...&newest=...` |
| Athlete profile | `GET /athlete/{id}` |
| Power curves | `GET /athlete/{id}/power-curves` |
| Pace curves | `GET /athlete/{id}/pace-curves` |
| Heart-rate curves | `GET /athlete/{id}/hr-curves` |

Request only needed activity and wellness fields. Limit normal context reads to 6-12 weeks and never exceed 180 days in one MCP call.

## Library write endpoints used

| Purpose | Method and path |
|---|---|
| Create plan | `POST /athlete/{id}/folders` |
| Clone plan | `POST /athlete/{id}/folders` with `copy_folder_id` |
| Create workout | `POST /athlete/{id}/workouts` |
| Update workout | `PUT /athlete/{id}/workouts/{workoutId}` |

A plan is a library container with `type: PLAN`. Workouts reference it with `folder_id`; `day` is zero-based from the plan start. Keep plan visibility `PRIVATE`.

Intervals.icu accepts structured steps in the workout `description`. It parses the text and returns computed fields such as `workout_doc`, duration, load, and intensity. It also accepts ZWO, MRC, ERG, and FIT content, but the MCP MVP uses native text.

## Constrained plan application

`POST /athlete/{id}/events/apply-plan` is exposed only through `schedule_draft_plan`. The request contains `folder_id`, exact `start_date_local`, and an empty `extra_workouts` list. Before calling it, verify managed ownership, current hash, non-empty plan, future date, duplicate applications, and calendar conflicts.

Do not expose generic event create/update/delete tools. Calendar workouts inside the Garmin upload window can reach the device before adequate review.

`PUT /athlete/{id}/events/bulk-delete` is used only by `unschedule_draft_plan`. Resolve targets by managed `plan_folder_id` and the exact application range, preview their IDs, and delete only those IDs after confirmation. Never delete by an unscoped date range.

## Managed-object test

A writable plan must satisfy all conditions:

1. `type == "PLAN"`
2. Description contains configured `[intervals-mcp:managed]` marker.

`[IA]` is only the configured display prefix for plans created or renamed by the MCP. Ownership must not depend on a mutable human-facing name.

Before changing a workout, confirm its `folder_id` belongs to that managed plan. Before every write, compare the caller's `expected_hash` with a fresh hash of the remote plan and workouts.
