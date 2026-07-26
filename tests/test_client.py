"""Contract-style tests against an in-memory Intervals.icu HTTP fake."""

from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from intervals_mcp.client import IntervalsClient
from intervals_mcp.config import Settings
from intervals_mcp.errors import ConcurrentModification, SafetyViolation
from intervals_mcp.models import Plan, WorkoutDraft


class FakeIntervals:
    def __init__(self) -> None:
        self.plans: list[dict[str, Any]] = []
        self.workouts: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str]] = []
        self.request_bodies: list[dict[str, Any]] = []
        self.next_plan_id = 10
        self.next_workout_id = 100

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path))
        base = "/api/v1/athlete/0"

        if request.method == "GET" and path == f"{base}/folders":
            return httpx.Response(200, json=self.plans)
        if request.method == "GET" and path == f"{base}/workouts":
            return httpx.Response(200, json=self.workouts)
        if request.method == "POST" and path == f"{base}/folders":
            payload = self._json(request)
            payload.update({"id": self.next_plan_id, "children": []})
            self.next_plan_id += 1
            self.plans.append(payload)
            return httpx.Response(200, json=payload)
        if request.method == "PUT" and path.startswith(f"{base}/folders/"):
            plan_id = int(path.rsplit("/", 1)[1])
            payload = self._json(request)
            payload["id"] = plan_id
            index = next(i for i, item in enumerate(self.plans) if item["id"] == plan_id)
            self.plans[index] = payload
            return httpx.Response(200, json=payload)
        if request.method == "POST" and path == f"{base}/workouts":
            payload = self._json(request)
            payload.update({"id": self.next_workout_id, "updated": "2026-07-18T12:00:00Z"})
            self.next_workout_id += 1
            self.workouts.append(payload)
            return httpx.Response(200, json=payload)
        if request.method == "PUT" and path.startswith(f"{base}/workouts/"):
            workout_id = int(path.rsplit("/", 1)[1])
            payload = self._json(request)
            payload.update({"id": workout_id, "updated": "2026-07-18T13:00:00Z"})
            index = next(i for i, item in enumerate(self.workouts) if item["id"] == workout_id)
            self.workouts[index] = payload
            return httpx.Response(200, json=payload)
        if request.method == "GET" and path == f"{base}/activities":
            return httpx.Response(200, json=[])
        if request.method == "GET" and path == f"{base}/wellness":
            return httpx.Response(200, json=[])
        if request.method == "GET" and path == f"{base}/events":
            return httpx.Response(200, json=self.events)
        if request.method == "POST" and path == f"{base}/events/apply-plan":
            payload = self._json(request)
            self.request_bodies.append(payload)
            plan_id = payload["folder_id"]
            start = date.fromisoformat(payload["start_date_local"][:10])
            plan_workouts = [item for item in self.workouts if item["folder_id"] == plan_id]
            for workout in plan_workouts:
                event = {
                    **workout,
                    "id": 1000 + len(self.events),
                    "category": "WORKOUT",
                    "start_date_local": str(start + timedelta(days=workout["day"])),
                    "plan_folder_id": plan_id,
                    "plan_workout_id": workout["id"],
                }
                self.events.append(event)
            return httpx.Response(200, json={"created": len(plan_workouts)})
        if request.method == "PUT" and path == f"{base}/events/bulk-delete":
            doomed = self._json_list(request)
            doomed_ids = {item["id"] for item in doomed}
            before = len(self.events)
            self.events = [item for item in self.events if item["id"] not in doomed_ids]
            return httpx.Response(200, json={"eventsDeleted": before - len(self.events)})
        return httpx.Response(404, json={"error": f"Unhandled {request.method} {path}"})

    @staticmethod
    def _json(request: httpx.Request) -> dict[str, Any]:
        import json

        return dict(json.loads(request.content))

    @staticmethod
    def _json_list(request: httpx.Request) -> list[dict[str, Any]]:
        import json

        return list(json.loads(request.content))


@pytest.fixture
def settings() -> Settings:
    return Settings(
        intervals_api_key=SecretStr("test-key"),
        intervals_athlete_id="0",
        intervals_base_url="https://intervals.test/api/v1",
    )


@pytest.mark.asyncio
async def test_create_and_edit_managed_draft(settings: Settings) -> None:
    fake = FakeIntervals()
    transport = httpx.MockTransport(fake)
    async with IntervalsClient(settings, transport=transport) as client:
        plan, initial_hash = await client.create_draft_plan(
            "Base week", "Controlled draft", ["Run", "Ride"]
        )
        assert plan.name == "[IA] Base week"
        assert plan.visibility == "PRIVATE"
        assert "[intervals-mcp:managed]" in plan.description

        workout = WorkoutDraft(
            name="Easy aerobic run",
            type="Run",
            day=1,
            target="PACE",
            description="Warmup\n- 10m Z1\nMain\n- 30m Z2\nCooldown\n- 5m Z1",
        )
        created, next_hash = await client.add_workout(plan.id, initial_hash, workout)
        assert created.folder_id == plan.id
        assert next_hash != initial_hash

        replacement = workout.model_copy(update={"name": "Aerobic run revised", "day": 2})
        updated, final_hash = await client.update_workout(
            plan.id, next_hash, created.id or 0, replacement
        )
        assert updated.name == "Aerobic run revised"
        assert updated.day == 2
        assert final_hash != next_hash

        renamed, renamed_hash = await client.rename_draft_plan(
            plan.id, final_hash, "Base week clean"
        )
        assert renamed.name == "[IA] Base week clean"
        assert renamed_hash != final_hash

    assert not any("/events" in path for _, path in fake.requests)


@pytest.mark.asyncio
async def test_refuses_unmanaged_plan(settings: Settings) -> None:
    fake = FakeIntervals()
    fake.plans.append(
        {
            "id": 4,
            "type": "PLAN",
            "name": "Human coach plan",
            "description": "Do not touch",
            "children": [],
        }
    )
    async with IntervalsClient(settings, transport=httpx.MockTransport(fake)) as client:
        with pytest.raises(SafetyViolation, match="outside the managed draft namespace"):
            await client.get_draft_plan(4)


@pytest.mark.asyncio
async def test_refuses_stale_hash_before_write(settings: Settings) -> None:
    fake = FakeIntervals()
    transport = httpx.MockTransport(fake)
    async with IntervalsClient(settings, transport=transport) as client:
        plan, _ = await client.create_draft_plan("Week", "Draft")
        workout = WorkoutDraft(
            name="Recovery",
            type="Ride",
            day=0,
            description="Recovery\n- 30m Z1",
        )
        with pytest.raises(ConcurrentModification):
            await client.add_workout(plan.id, "stale", workout)

    assert [method for method, path in fake.requests if path.endswith("/workouts")] == ["GET"]


def test_workout_requires_native_step_syntax() -> None:
    with pytest.raises(ValueError, match="must contain at least one"):
        WorkoutDraft(name="Bad", description="Just run hard", type="Run", day=0)


def test_remote_workout_accepts_null_day() -> None:
    fake = FakeIntervals()
    fake.plans.append(
        {
            "id": 15,
            "type": "PLAN",
            "name": "[IA] Empty plan",
            "description": "[intervals-mcp:managed]",
            "children": [
                {
                    "id": 151,
                    "name": "Unscheduled library item",
                    "description": "- 20m Z1",
                    "type": "Run",
                    "day": None,
                }
            ],
        }
    )

    plan = Plan.model_validate(fake.plans[0])
    assert plan.children[0].day is None
    assert IntervalsClient.plan_hash(plan)


def test_remote_plan_normalizes_nullable_optional_fields() -> None:
    plan = Plan.model_validate(
        {
            "id": 16,
            "type": "FOLDER",
            "name": "Library folder",
            "description": None,
            "children": None,
            "activity_types": None,
        }
    )

    assert plan.description == ""
    assert plan.children == []
    assert plan.activity_types == []


@pytest.mark.asyncio
async def test_schedule_managed_plan_on_future_date(settings: Settings) -> None:
    fake = FakeIntervals()
    async with IntervalsClient(settings, transport=httpx.MockTransport(fake)) as client:
        plan, content_hash = await client.create_draft_plan("Schedule", "Draft")
        workout = WorkoutDraft(
            name="Easy run",
            type="Run",
            day=0,
            description="Easy\n- 20m Z1",
        )
        _, content_hash = await client.add_workout(plan.id, content_hash, workout)
        start = date.today() + timedelta(days=3)

        preview = await client.preview_draft_schedule(plan.id, content_hash, start)
        assert preview["workout_count"] == 1
        assert preview["requires_conflict_override"] is False

        result = await client.schedule_draft_plan(plan.id, content_hash, start)
        assert result["created_event_count"] == 1
        assert result["start_date"] == start.isoformat()
        apply_request = next(
            request
            for request in fake.request_bodies
            if request.get("folder_id") == plan.id and "start_date_local" in request
        )
        assert apply_request["start_date_local"] == f"{start.isoformat()}T00:00:00"

    assert ("POST", "/api/v1/athlete/0/events/apply-plan") in fake.requests


@pytest.mark.asyncio
async def test_schedule_refuses_duplicate_application(settings: Settings) -> None:
    fake = FakeIntervals()
    async with IntervalsClient(settings, transport=httpx.MockTransport(fake)) as client:
        plan, content_hash = await client.create_draft_plan("Duplicate", "Draft")
        workout = WorkoutDraft(
            name="Easy ride",
            type="Ride",
            day=0,
            description="Easy\n- 20m Z1",
        )
        _, content_hash = await client.add_workout(plan.id, content_hash, workout)
        start = date.today() + timedelta(days=4)
        await client.schedule_draft_plan(plan.id, content_hash, start)

        with pytest.raises(SafetyViolation, match="already has"):
            await client.preview_draft_schedule(plan.id, content_hash, start)


@pytest.mark.asyncio
async def test_unschedule_deletes_only_managed_plan_events(settings: Settings) -> None:
    fake = FakeIntervals()
    fake.events.append(
        {
            "id": 900,
            "category": "NOTE",
            "name": "Keep me",
            "start_date_local": str(date.today() + timedelta(days=5)),
        }
    )
    async with IntervalsClient(settings, transport=httpx.MockTransport(fake)) as client:
        plan, content_hash = await client.create_draft_plan("Remove", "Draft")
        workout = WorkoutDraft(
            name="Easy swim",
            type="Swim",
            day=0,
            description="Easy\n- 10m Z1",
        )
        _, content_hash = await client.add_workout(plan.id, content_hash, workout)
        start = date.today() + timedelta(days=5)
        await client.schedule_draft_plan(
            plan.id,
            content_hash,
            start,
            allow_calendar_conflicts=True,
        )

        preview = await client.preview_draft_unschedule(plan.id, content_hash, start)
        assert preview["event_count"] == 1
        result = await client.unschedule_draft_plan(plan.id, content_hash, start)
        assert result["remaining_event_count"] == 0

    assert [event["id"] for event in fake.events] == [900]
