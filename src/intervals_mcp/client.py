"""Async client for the subset of Intervals.icu used by the MCP server."""

import hashlib
import json
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

import httpx

from .config import Settings
from .errors import ConcurrentModification, IntervalsAPIError, SafetyViolation
from .models import DraftPlanSummary, Plan, Workout, WorkoutDraft


class IntervalsClient:
    """Read training data and manage only namespaced library plan drafts."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.intervals_base_url.rstrip("/"),
            auth=httpx.BasicAuth("API_KEY", settings.intervals_api_key.get_secret_value()),
            timeout=settings.request_timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "intervals-mcp/0.1"},
        )

    async def __aenter__(self) -> "IntervalsClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def athlete_path(self) -> str:
        return f"/athlete/{self.settings.intervals_athlete_id}"

    async def get_athlete_profile(self) -> dict[str, Any]:
        """Read the athlete profile so the MCP can expose only relevant body metrics."""

        data = await self._request("GET", self.athlete_path)
        return dict(data)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise IntervalsAPIError(
                f"Intervals.icu returned {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise IntervalsAPIError(f"Could not reach Intervals.icu: {exc}") from exc

        if not response.content:
            return None
        return response.json()

    async def list_folders(self) -> list[Plan]:
        data = await self._request("GET", f"{self.athlete_path}/folders")
        return [Plan.model_validate(item) for item in data]

    async def list_workouts(self) -> list[Workout]:
        data = await self._request("GET", f"{self.athlete_path}/workouts")
        return [Workout.model_validate(item) for item in data]

    async def list_draft_plans(self) -> list[DraftPlanSummary]:
        plans = await self.list_folders()
        workouts = await self.list_workouts()
        by_folder: dict[int, list[Workout]] = {}
        for workout in workouts:
            if workout.folder_id is not None:
                by_folder.setdefault(workout.folder_id, []).append(workout)

        output: list[DraftPlanSummary] = []
        for plan in plans:
            if not self._is_managed_plan(plan):
                continue
            plan.children = by_folder.get(plan.id, plan.children)
            output.append(self._summary(plan))
        return output

    async def get_draft_plan(self, plan_id: int) -> tuple[Plan, str]:
        plans = await self.list_folders()
        plan = next((item for item in plans if item.id == plan_id), None)
        if plan is None:
            raise SafetyViolation(f"Plan {plan_id} does not exist")
        self._assert_managed_plan(plan)
        workouts = await self.list_workouts()
        plan.children = [item for item in workouts if item.folder_id == plan.id]
        return plan, self.plan_hash(plan)

    async def create_draft_plan(
        self,
        name: str,
        description: str,
        activity_types: list[str] | None = None,
    ) -> tuple[Plan, str]:
        clean_name = name.strip()
        if not clean_name:
            raise SafetyViolation("Draft plan name cannot be empty")
        if not clean_name.startswith(self.settings.draft_prefix):
            clean_name = f"{self.settings.draft_prefix} {clean_name}"

        payload = {
            "type": "PLAN",
            "name": clean_name,
            "description": self._managed_description(description),
            "visibility": "PRIVATE",
            "activity_types": activity_types or [],
        }
        data = await self._request("POST", f"{self.athlete_path}/folders", json=payload)
        plan = Plan.model_validate(data)
        return plan, self.plan_hash(plan)

    async def clone_draft_plan(
        self, plan_id: int, expected_hash: str, version_label: str
    ) -> tuple[Plan, str]:
        plan, current_hash = await self.get_draft_plan(plan_id)
        self._assert_hash(expected_hash, current_hash)
        payload = {
            "type": "PLAN",
            "name": f"{plan.name} — {version_label.strip()}",
            "description": self._managed_description(
                f"Clone of managed plan {plan.id}.\n{self._strip_marker(plan.description)}"
            ),
            "visibility": "PRIVATE",
            "copy_folder_id": plan.id,
        }
        data = await self._request("POST", f"{self.athlete_path}/folders", json=payload)
        cloned = Plan.model_validate(data)
        return cloned, self.plan_hash(cloned)

    async def rename_draft_plan(
        self,
        plan_id: int,
        expected_hash: str,
        name: str,
    ) -> tuple[Plan, str]:
        """Rename a managed plan while preserving its ownership marker and contents."""

        plan, current_hash = await self.get_draft_plan(plan_id)
        self._assert_hash(expected_hash, current_hash)
        clean_name = name.strip()
        if not clean_name:
            raise SafetyViolation("Draft plan name cannot be empty")
        if not clean_name.startswith(self.settings.draft_prefix):
            clean_name = f"{self.settings.draft_prefix} {clean_name}"
        payload = {
            **plan.model_dump(exclude={"children"}, exclude_none=True),
            "name": clean_name,
            "description": self._managed_description(plan.description),
        }
        data = await self._request("PUT", f"{self.athlete_path}/folders/{plan_id}", json=payload)
        renamed = Plan.model_validate(data)
        renamed.children = plan.children
        return renamed, self.plan_hash(renamed)

    async def add_workout(
        self, plan_id: int, expected_hash: str, workout: WorkoutDraft
    ) -> tuple[Workout, str]:
        _, current_hash = await self.get_draft_plan(plan_id)
        self._assert_hash(expected_hash, current_hash)
        payload = {"folder_id": plan_id, **workout.model_dump(exclude_none=True)}
        data = await self._request("POST", f"{self.athlete_path}/workouts", json=payload)
        created = Workout.model_validate(data)
        _, new_hash = await self.get_draft_plan(plan_id)
        return created, new_hash

    async def update_workout(
        self,
        plan_id: int,
        expected_hash: str,
        workout_id: int,
        workout: WorkoutDraft,
    ) -> tuple[Workout, str]:
        plan, current_hash = await self.get_draft_plan(plan_id)
        self._assert_hash(expected_hash, current_hash)
        existing = next((item for item in plan.children if item.id == workout_id), None)
        if existing is None:
            raise SafetyViolation(f"Workout {workout_id} is not part of managed plan {plan_id}")
        payload = {
            **existing.model_dump(exclude_none=True),
            **workout.model_dump(exclude_none=True),
            "folder_id": plan_id,
        }
        data = await self._request(
            "PUT", f"{self.athlete_path}/workouts/{workout_id}", json=payload
        )
        updated = Workout.model_validate(data)
        _, new_hash = await self.get_draft_plan(plan_id)
        return updated, new_hash

    async def list_activities(
        self, oldest: date, newest: date, limit: int = 200
    ) -> list[dict[str, Any]]:
        fields = [
            "id",
            "start_date_local",
            "name",
            "type",
            "moving_time",
            "distance",
            "icu_training_load",
            "icu_intensity",
            "average_heartrate",
            "average_watts",
            "compliance",
            "source",
        ]
        params = {
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
            "limit": limit,
            "fields": ",".join(fields),
        }
        data = await self._request("GET", f"{self.athlete_path}/activities", params=params)
        return list(data)

    async def list_wellness(self, oldest: date, newest: date) -> list[dict[str, Any]]:
        fields = [
            "id",
            "ctl",
            "atl",
            "rampRate",
            "ctlLoad",
            "atlLoad",
            "sportInfo",
            "weight",
            "restingHR",
            "hrv",
            "hrvSDNN",
            "sleepSecs",
            "sleepScore",
            "sleepQuality",
            "avgSleepingHR",
            "steps",
            "vo2max",
            "bodyFat",
            "soreness",
            "fatigue",
            "stress",
            "mood",
            "motivation",
            "injury",
            "readiness",
            "spO2",
            "systolic",
            "diastolic",
        ]
        params = {
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
            "fields": ",".join(fields),
        }
        data = await self._request("GET", f"{self.athlete_path}/wellness", params=params)
        return list(data)

    async def get_performance_curves(self, sport: str, curves: str = "42d") -> dict[str, Any]:
        """Read power, pace, and heart-rate duration curves for a sport and period."""

        params = {"type": sport, "curves": curves}
        endpoints = {
            "power": f"{self.athlete_path}/power-curves",
            "pace": f"{self.athlete_path}/pace-curves",
            "heart_rate": f"{self.athlete_path}/hr-curves",
        }
        return {
            name: await self._request("GET", path, params=params)
            for name, path in endpoints.items()
        }

    async def list_events(self, oldest: date, newest: date) -> list[dict[str, Any]]:
        params = {"oldest": oldest.isoformat(), "newest": newest.isoformat()}
        data = await self._request("GET", f"{self.athlete_path}/events", params=params)
        return list(data)

    async def training_context(self, oldest: date, newest: date) -> dict[str, Any]:
        activities = await self.list_activities(oldest, newest)
        wellness = await self.list_wellness(oldest, newest)
        events = await self.list_events(oldest, newest)
        for record in wellness:
            ctl = record.get("ctl")
            atl = record.get("atl")
            if isinstance(ctl, (int, float)) and isinstance(atl, (int, float)):
                record["tsb"] = round(ctl - atl, 2)
        return {
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
            "activities": activities,
            "wellness": wellness,
            "calendar_events": events,
        }

    async def preview_draft_schedule(
        self,
        plan_id: int,
        expected_hash: str,
        start_date: date,
    ) -> dict[str, Any]:
        """Validate and preview applying one managed plan to the athlete calendar."""

        plan, current_hash = await self.get_draft_plan(plan_id)
        self._assert_hash(expected_hash, current_hash)
        if start_date < date.today():
            raise SafetyViolation("A draft plan cannot be scheduled in the past")
        if start_date > date.today() + timedelta(days=365):
            raise SafetyViolation("Schedule draft plans at most 365 days in advance")
        if not plan.children:
            raise SafetyViolation("Cannot schedule an empty draft plan")

        invalid = [workout.id for workout in plan.children if workout.day is None]
        if invalid:
            raise SafetyViolation(f"Plan workouts without a day cannot be scheduled: {invalid}")

        last_day = max(workout.day or 0 for workout in plan.children)
        end_date = start_date + timedelta(days=last_day)
        events = await self.list_events(start_date, end_date)
        same_plan = [event for event in events if event.get("plan_folder_id") == plan.id]
        if same_plan:
            raise SafetyViolation(
                f"Managed plan {plan.id} already has {len(same_plan)} event(s) in this date range"
            )

        conflicts = [
            {
                "id": event.get("id"),
                "date": event.get("start_date_local"),
                "name": event.get("name"),
                "category": event.get("category"),
            }
            for event in events
        ]
        return {
            "plan_id": plan.id,
            "plan_name": plan.name,
            "content_hash": current_hash,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "workout_count": len(plan.children),
            "existing_calendar_events": conflicts,
            "requires_conflict_override": bool(conflicts),
        }

    async def schedule_draft_plan(
        self,
        plan_id: int,
        expected_hash: str,
        start_date: date,
        *,
        allow_calendar_conflicts: bool = False,
    ) -> dict[str, Any]:
        """Apply a managed plan to the calendar after all schedule checks pass."""

        preview = await self.preview_draft_schedule(plan_id, expected_hash, start_date)
        if preview["requires_conflict_override"] and not allow_calendar_conflicts:
            raise SafetyViolation(
                "The target range contains calendar events. Preview them and obtain explicit "
                "approval before retrying with allow_calendar_conflicts=true."
            )

        response = await self._request(
            "POST",
            f"{self.athlete_path}/events/apply-plan",
            json={
                "start_date_local": f"{start_date.isoformat()}T00:00:00",
                "folder_id": plan_id,
                "extra_workouts": [],
            },
        )
        applied_events = await self.list_events(
            date.fromisoformat(preview["start_date"]),
            date.fromisoformat(preview["end_date"]),
        )
        created = [event for event in applied_events if event.get("plan_folder_id") == plan_id]
        return {
            **preview,
            "api_response": response,
            "created_event_count": len(created),
            "created_event_ids": [event.get("id") for event in created],
        }

    async def preview_draft_unschedule(
        self,
        plan_id: int,
        expected_hash: str,
        start_date: date,
    ) -> dict[str, Any]:
        """Resolve the exact calendar events created from one managed plan application."""

        plan, current_hash = await self.get_draft_plan(plan_id)
        self._assert_hash(expected_hash, current_hash)
        if not plan.children:
            raise SafetyViolation("Cannot resolve the date range for an empty draft plan")
        invalid = [workout.id for workout in plan.children if workout.day is None]
        if invalid:
            raise SafetyViolation(f"Plan workouts without a day cannot be resolved: {invalid}")

        last_day = max(workout.day or 0 for workout in plan.children)
        end_date = start_date + timedelta(days=last_day)
        events = await self.list_events(start_date, end_date)
        targets = [event for event in events if event.get("plan_folder_id") == plan.id]
        target_ids = [event.get("id") for event in targets if event.get("id") is not None]
        if not target_ids:
            raise SafetyViolation(
                f"No calendar events from managed plan {plan.id} were found in this date range"
            )
        return {
            "plan_id": plan.id,
            "plan_name": plan.name,
            "content_hash": current_hash,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "event_count": len(target_ids),
            "event_ids": target_ids,
            "events": [
                {
                    "id": event.get("id"),
                    "date": event.get("start_date_local"),
                    "name": event.get("name"),
                    "plan_workout_id": event.get("plan_workout_id"),
                }
                for event in targets
            ],
        }

    async def unschedule_draft_plan(
        self,
        plan_id: int,
        expected_hash: str,
        start_date: date,
    ) -> dict[str, Any]:
        """Delete only calendar events belonging to one managed plan application."""

        preview = await self.preview_draft_unschedule(plan_id, expected_hash, start_date)
        response = await self._request(
            "PUT",
            f"{self.athlete_path}/events/bulk-delete",
            json=[{"id": event_id} for event_id in preview["event_ids"]],
        )
        remaining_events = await self.list_events(
            date.fromisoformat(preview["start_date"]),
            date.fromisoformat(preview["end_date"]),
        )
        remaining = [event for event in remaining_events if event.get("plan_folder_id") == plan_id]
        return {
            **preview,
            "api_response": response,
            "remaining_event_count": len(remaining),
        }

    def _is_managed_plan(self, plan: Plan) -> bool:
        return plan.type == "PLAN" and self.settings.managed_marker in plan.description

    def _assert_managed_plan(self, plan: Plan) -> None:
        if not self._is_managed_plan(plan):
            raise SafetyViolation(
                f"Plan {plan.id} is outside the managed draft namespace; refusing mutation"
            )

    @staticmethod
    def _assert_hash(expected_hash: str, actual_hash: str) -> None:
        if expected_hash != actual_hash:
            raise ConcurrentModification(
                "The remote draft changed. Read it again and retry with its new content hash."
            )

    def _managed_description(self, description: str) -> str:
        clean = self._strip_marker(description.strip())
        return f"{self.settings.managed_marker}\n{clean}".rstrip()

    def _strip_marker(self, description: str) -> str:
        return description.replace(self.settings.managed_marker, "").strip()

    def _summary(self, plan: Plan) -> DraftPlanSummary:
        return DraftPlanSummary(
            id=plan.id,
            name=plan.name,
            description=self._strip_marker(plan.description),
            workout_count=len(plan.children),
            content_hash=self.plan_hash(plan),
        )

    @staticmethod
    def plan_hash(plan: Plan) -> str:
        normalized: Mapping[str, Any] = {
            "id": plan.id,
            "name": plan.name,
            "description": plan.description,
            "children": sorted(
                (
                    {
                        "id": item.id,
                        "name": item.name,
                        "description": item.description,
                        "type": item.type,
                        "folder_id": item.folder_id,
                        "day": item.day,
                        "target": item.target,
                        "indoor": item.indoor,
                        "updated": item.updated,
                    }
                    for item in plan.children
                ),
                key=lambda item: (
                    item["day"] if item["day"] is not None else -1,
                    item["id"] or 0,
                ),
            ),
        }
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()
