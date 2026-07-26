"""MCP server exposing safe Intervals.icu draft-plan operations."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .client import IntervalsClient
from .config import get_settings
from .models import WorkoutDraft
from .personal_context import SECTIONS, read_personal_context, set_personal_context

PersonalSection = Literal[
    "Profile",
    "Goals and events",
    "Availability",
    "Training preferences",
    "Performance markers",
    "Equipment and integrations",
    "Health and constraints",
    "Coaching notes",
]

INSTRUCTIONS = """
Always read intervals://personal-context before analyzing or changing training data. Remember new
durable athlete preferences with set_personal_fact, but never store examples, guesses, credentials,
or sensitive health information unless the user explicitly asks for it to be remembered.
Read Intervals.icu training context and manage private AI draft plans.
Mutations are restricted to managed plans whose descriptions carry the intervals-mcp marker.
New and renamed plans use the configured display prefix. Calendar writes are restricted to applying
one such managed plan on an exact approved future date; generic event writes are not available.
Before a write, show the proposed change to the user and call the tool again with confirmed=true
only after explicit approval. Always pass the latest content_hash when editing a draft.
""".strip()

mcp = FastMCP("Intervals.icu Draft Coach", instructions=INSTRUCTIONS, json_response=True)
personal_context_lock = asyncio.Lock()


@asynccontextmanager
async def client_session() -> AsyncIterator[IntervalsClient]:
    async with IntervalsClient(get_settings()) as client:
        yield client


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Expected an ISO date (YYYY-MM-DD), got {value!r}") from exc


def confirmation_required(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "confirmation_required",
        "operation": operation,
        "proposed_change": payload,
        "calendar_changed": False,
        "garmin_changed": False,
        "next_step": "Show this preview to the user. Retry with confirmed=true only if approved.",
    }


@mcp.resource("intervals://safety-policy")
def safety_policy() -> str:
    """Return the non-negotiable mutation boundary for this server."""

    return INSTRUCTIONS


@mcp.resource("intervals://personal-context")
def personal_context_resource() -> str:
    """Return the private durable athlete context that must inform planning."""

    return read_personal_context(get_settings())


@mcp.resource("intervals://draft-plans")
async def draft_plans_resource() -> str:
    """List managed AI draft plans as JSON."""

    async with client_session() as client:
        plans = await client.list_draft_plans()
    return json.dumps([plan.model_dump(mode="json") for plan in plans], ensure_ascii=False)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_training_context(oldest: str, newest: str) -> dict[str, Any]:
    """Read activities, wellness and calendar events for an inclusive ISO date range."""

    oldest_date = parse_date(oldest)
    newest_date = parse_date(newest)
    if oldest_date > newest_date:
        raise ValueError("oldest must be on or before newest")
    if (newest_date - oldest_date).days > 180:
        raise ValueError("Request at most 180 days at a time")
    async with client_session() as client:
        return await client.training_context(oldest_date, newest_date)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_athlete_profile() -> dict[str, Any]:
    """Read health and body-composition fields from the athlete profile only."""

    profile_fields = {
        "height",
        "weight",
        "body_fat",
        "bodyFat",
        "resting_hr",
        "restingHR",
        "max_hr",
        "maxHR",
    }
    async with client_session() as client:
        profile = await client.get_athlete_profile()
    return {
        "profile_metrics": {
            key: value
            for key, value in profile.items()
            if key in profile_fields and value is not None
        },
        "available_profile_fields": sorted(key for key in profile if key in profile_fields),
        "privacy": (
            "Only body and health-related profile fields are returned; "
            "contact and location fields are filtered."
        ),
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_personal_context() -> dict[str, Any]:
    """Read durable athlete preferences and constraints before planning or editing."""

    return {
        "content": read_personal_context(get_settings()),
        "sections": list(SECTIONS),
        "privacy": "local file ignored by Git; credentials are forbidden",
    }


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)
)
async def set_personal_fact(section: PersonalSection, key: str, value: str) -> dict[str, Any]:
    """Remember one durable, non-secret athlete fact; the same section/key is replaced safely."""

    async with personal_context_lock:
        result = set_personal_context(get_settings(), section, key, value)
    return {
        "status": "personal_context_updated" if result["changed"] else "already_current",
        **result,
        "calendar_changed": False,
        "garmin_changed": False,
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def list_draft_plans() -> dict[str, Any]:
    """List only plans managed by this server, including their current content hashes."""

    async with client_session() as client:
        plans = await client.list_draft_plans()
    return {"draft_plans": [plan.model_dump(mode="json") for plan in plans]}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def get_draft_plan(plan_id: int) -> dict[str, Any]:
    """Read a managed plan and its workouts; reject plans outside the draft namespace."""

    async with client_session() as client:
        plan, content_hash = await client.get_draft_plan(plan_id)
    return {"plan": plan.model_dump(mode="json"), "content_hash": content_hash}


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
)
async def create_draft_plan(
    name: str,
    description: str,
    activity_types: list[str] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Create a private managed library PLAN; never apply it to the calendar."""

    preview = {
        "name": name,
        "description": description,
        "activity_types": activity_types or [],
        "destination": "Intervals.icu workout library only",
    }
    if not confirmed:
        return confirmation_required("create_draft_plan", preview)
    async with client_session() as client:
        plan, content_hash = await client.create_draft_plan(name, description, activity_types)
    return {
        "status": "created_in_library",
        "plan": plan.model_dump(mode="json"),
        "content_hash": content_hash,
        "calendar_changed": False,
        "garmin_changed": False,
    }


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
)
async def clone_draft_plan(
    plan_id: int,
    expected_hash: str,
    version_label: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Clone a managed draft plan to preserve a version before editing."""

    preview = {
        "plan_id": plan_id,
        "expected_hash": expected_hash,
        "version_label": version_label,
    }
    if not confirmed:
        return confirmation_required("clone_draft_plan", preview)
    async with client_session() as client:
        plan, content_hash = await client.clone_draft_plan(plan_id, expected_hash, version_label)
    return {
        "status": "cloned_in_library",
        "plan": plan.model_dump(mode="json"),
        "content_hash": content_hash,
        "calendar_changed": False,
        "garmin_changed": False,
    }


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
)
async def rename_draft_plan(
    plan_id: int,
    expected_hash: str,
    name: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Rename one managed library plan using the configured short display prefix."""

    preview = {"plan_id": plan_id, "expected_hash": expected_hash, "requested_name": name}
    if not confirmed:
        return confirmation_required("rename_draft_plan", preview)
    async with client_session() as client:
        plan, content_hash = await client.rename_draft_plan(plan_id, expected_hash, name)
    return {
        "status": "renamed_in_library",
        "plan": plan.model_dump(mode="json"),
        "content_hash": content_hash,
        "calendar_changed": False,
        "garmin_changed": False,
    }


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
)
async def add_workout_to_draft(
    plan_id: int,
    expected_hash: str,
    name: str,
    description: str,
    activity_type: str,
    day: int,
    target: Literal["AUTO", "POWER", "HR", "PACE"] = "AUTO",
    indoor: bool | None = None,
    time: str | None = None,
    tags: list[str] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Add one structured workout to a managed library plan."""

    workout = WorkoutDraft(
        name=name,
        description=description,
        type=activity_type,
        day=day,
        target=target,
        indoor=indoor,
        time=time,
        tags=tags or [],
    )
    preview = {"plan_id": plan_id, "workout": workout.model_dump(mode="json")}
    if not confirmed:
        return confirmation_required("add_workout_to_draft", preview)
    async with client_session() as client:
        created, content_hash = await client.add_workout(plan_id, expected_hash, workout)
    return {
        "status": "added_to_library_plan",
        "workout": created.model_dump(mode="json"),
        "content_hash": content_hash,
        "calendar_changed": False,
        "garmin_changed": False,
    }


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
)
async def update_draft_workout(
    plan_id: int,
    expected_hash: str,
    workout_id: int,
    name: str,
    description: str,
    activity_type: str,
    day: int,
    target: Literal["AUTO", "POWER", "HR", "PACE"] = "AUTO",
    indoor: bool | None = None,
    time: str | None = None,
    tags: list[str] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Replace one workout on a managed plan after checking the plan hash."""

    workout = WorkoutDraft(
        name=name,
        description=description,
        type=activity_type,
        day=day,
        target=target,
        indoor=indoor,
        time=time,
        tags=tags or [],
    )
    preview = {
        "plan_id": plan_id,
        "workout_id": workout_id,
        "replacement": workout.model_dump(mode="json"),
    }
    if not confirmed:
        return confirmation_required("update_draft_workout", preview)
    async with client_session() as client:
        updated, content_hash = await client.update_workout(
            plan_id, expected_hash, workout_id, workout
        )
    return {
        "status": "updated_in_library_plan",
        "workout": updated.model_dump(mode="json"),
        "content_hash": content_hash,
        "calendar_changed": False,
        "garmin_changed": False,
    }


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
)
async def schedule_draft_plan(
    plan_id: int,
    expected_hash: str,
    start_date: str,
    allow_calendar_conflicts: bool = False,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Apply one managed draft plan to the calendar on an exact future ISO date."""

    schedule_date = parse_date(start_date)
    async with client_session() as client:
        preview = await client.preview_draft_schedule(plan_id, expected_hash, schedule_date)

    proposed = {
        **preview,
        "allow_calendar_conflicts": allow_calendar_conflicts,
        "destination": "Intervals.icu calendar; eligible workouts may sync to Garmin",
    }
    if not confirmed:
        return confirmation_required("schedule_draft_plan", proposed)

    async with client_session() as client:
        result = await client.schedule_draft_plan(
            plan_id,
            expected_hash,
            schedule_date,
            allow_calendar_conflicts=allow_calendar_conflicts,
        )
    return {
        "status": "scheduled_on_calendar",
        **result,
        "calendar_changed": True,
        "garmin_sync_eligible": True,
        "garmin_changed": "automatic_sync_pending",
    }


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)
)
async def unschedule_draft_plan(
    plan_id: int,
    expected_hash: str,
    start_date: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Delete only calendar copies from one managed plan application; keep the library plan."""

    schedule_date = parse_date(start_date)
    async with client_session() as client:
        preview = await client.preview_draft_unschedule(plan_id, expected_hash, schedule_date)
    proposed = {
        **preview,
        "library_plan_changed": False,
        "destination": "Intervals.icu calendar; Garmin removal sync may follow",
    }
    if not confirmed:
        return confirmation_required("unschedule_draft_plan", proposed)

    async with client_session() as client:
        result = await client.unschedule_draft_plan(plan_id, expected_hash, schedule_date)
    return {
        "status": "removed_from_calendar",
        **result,
        "library_plan_changed": False,
        "calendar_changed": True,
        "garmin_changed": "automatic_removal_sync_pending",
    }


@mcp.prompt()
def draft_training_week(goal: str, week_start: str) -> str:
    """Guide an agent through a safe weekly-plan drafting workflow."""

    return f"""
Create a draft training week for goal: {goal}
Week starts: {week_start}

1. Read 6-12 weeks with get_training_context.
2. Read intervals://safety-policy and list_draft_plans.
3. Explain volume, intensity, recovery and missing-data assumptions.
4. Validate each workout description uses Intervals.icu native step syntax.
5. Preview every mutation and obtain explicit user approval.
6. Create or edit only a managed library draft.
7. Schedule it only when the user supplies or approves an exact start date.
8. Never claim the plan reached Garmin; report automatic synchronization as pending.
""".strip()


def main() -> None:
    """Run the local MCP server over stdio."""

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
