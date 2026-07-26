"""Idempotently seed the approved test-triatlon-1 Intervals.icu draft plan."""

import argparse
import asyncio
from dataclasses import dataclass
from typing import Literal

from intervals_mcp.mcp_server import (
    add_workout_to_draft,
    get_draft_plan,
    list_draft_plans,
)

Target = Literal["AUTO", "POWER", "HR", "PACE"]


@dataclass(frozen=True)
class WorkoutSpec:
    day: int
    sport: str
    name: str
    target: Target
    indoor: bool
    purpose: str
    steps: str

    @property
    def description(self) -> str:
        return f"{self.purpose}\n\n{self.steps}"


def spec(
    day: int,
    sport: str,
    name: str,
    target: Target,
    indoor: bool,
    purpose: str,
    steps: str,
) -> WorkoutSpec:
    return WorkoutSpec(
        day, sport, f"D{day + 1:02d} {sport} — {name}", target, indoor, purpose, steps
    )


WORKOUTS = [
    spec(
        0,
        "Swim",
        "Technique easy",
        "AUTO",
        True,
        "Easy technique-focused swim. Keep every repetition relaxed.",
        "Warmup\n- 3m Z1\n\nTechnique\n- 6m Z1\n\nCooldown\n- 3m Z1",
    ),
    spec(
        0,
        "Ride",
        "Easy aerobic",
        "POWER",
        False,
        "Easy aerobic ride with smooth cadence.",
        "Warmup\n- 5m Z1\n\nMain\n- 10m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        0,
        "Run",
        "Easy transition",
        "PACE",
        False,
        "Short relaxed run. Conversational effort throughout.",
        "Warmup\n- 5m Z1\n\nMain\n- 5m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        1,
        "Swim",
        "Recovery",
        "AUTO",
        True,
        "Very easy recovery swim with long, relaxed strokes.",
        "Warmup\n- 2m Z1\n\nEasy swim\n- 6m Z1\n\nCooldown\n- 2m Z1",
    ),
    spec(
        1,
        "Ride",
        "Recovery spin",
        "POWER",
        False,
        "Recovery spin. Use light resistance and comfortable cadence.",
        "Recovery\n- 15m Z1",
    ),
    spec(
        1,
        "Run",
        "Aerobic easy",
        "PACE",
        False,
        "Easy aerobic run without pace pressure.",
        "Warmup\n- 5m Z1\n\nMain\n- 10m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        2,
        "Swim",
        "Aerobic repetitions",
        "AUTO",
        True,
        "Short controlled aerobic repetitions. Never strain.",
        "Warmup\n- 3m Z1\n\n3x\n- 2m Z2\n- 1m Z1\n\nCooldown\n- 3m Z1",
    ),
    spec(
        2,
        "Ride",
        "Cadence blocks",
        "POWER",
        False,
        "Controlled aerobic cadence blocks. Keep power low.",
        "Warmup\n- 4m Z1\n\n3x\n- 3m Z2\n- 1m Z1\n\nCooldown\n- 4m Z1",
    ),
    spec(
        2,
        "Run",
        "Recovery",
        "PACE",
        False,
        "Recovery run with relaxed form.",
        "Warmup\n- 5m Z1\n\nEasy run\n- 5m Z1\n\nCooldown\n- 5m Z1",
    ),
    spec(
        3,
        "Swim",
        "Recovery short",
        "AUTO",
        True,
        "Short recovery swim for the low-load day.",
        "Warmup\n- 2m Z1\n\nEasy swim\n- 4m Z1\n\nCooldown\n- 2m Z1",
    ),
    spec(
        3, "Ride", "Recovery spin", "POWER", False, "Low-load recovery spin.", "Recovery\n- 15m Z1"
    ),
    spec(
        3,
        "Run",
        "Recovery short",
        "PACE",
        False,
        "Short recovery jog. Stop if it does not feel easy.",
        "Warmup\n- 4m Z1\n\nEasy jog\n- 4m Z1\n\nCooldown\n- 4m Z1",
    ),
    spec(
        4,
        "Swim",
        "Progressive easy",
        "AUTO",
        True,
        "Gentle progression while staying aerobic.",
        "Warmup\n- 3m Z1\n\nMain\n- 6m Z2\n\nCooldown\n- 3m Z1",
    ),
    spec(
        4,
        "Ride",
        "Aerobic steady",
        "POWER",
        False,
        "Steady aerobic ride. Avoid drifting above Z2.",
        "Warmup\n- 5m Z1\n\nMain\n- 15m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        4,
        "Run",
        "Aerobic steady",
        "PACE",
        False,
        "Steady conversational run.",
        "Warmup\n- 5m Z1\n\nMain\n- 8m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        5,
        "Swim",
        "Technique reset",
        "AUTO",
        True,
        "Easy technique reset. Prioritize relaxed form.",
        "Warmup\n- 2m Z1\n\nTechnique\n- 6m Z1\n\nCooldown\n- 2m Z1",
    ),
    spec(
        5,
        "Ride",
        "Easy aerobic",
        "POWER",
        False,
        "Easy aerobic spin with no muscular strain.",
        "Warmup\n- 4m Z1\n\nMain\n- 10m Z2\n\nCooldown\n- 4m Z1",
    ),
    spec(
        5,
        "Run",
        "Gentle progression",
        "PACE",
        False,
        "Gentle progression without exceeding Z2.",
        "Warmup\n- 5m Z1\n\nMain\n- 5m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        6,
        "Swim",
        "Aerobic repetitions",
        "AUTO",
        True,
        "Controlled aerobic repetitions with easy recoveries.",
        "Warmup\n- 3m Z1\n\n3x\n- 2m Z2\n- 1m Z1\n\nCooldown\n- 3m Z1",
    ),
    spec(
        6,
        "Ride",
        "Aerobic blocks",
        "POWER",
        False,
        "Three low-intensity aerobic blocks.",
        "Warmup\n- 5m Z1\n\n3x\n- 4m Z2\n- 1m Z1\n\nCooldown\n- 5m Z1",
    ),
    spec(
        6,
        "Run",
        "Aerobic easy",
        "PACE",
        False,
        "Easy aerobic run at conversational effort.",
        "Warmup\n- 5m Z1\n\nMain\n- 10m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        7,
        "Swim",
        "Recovery short",
        "AUTO",
        True,
        "Short recovery swim for the low-load day.",
        "Warmup\n- 2m Z1\n\nEasy swim\n- 4m Z1\n\nCooldown\n- 2m Z1",
    ),
    spec(
        7, "Ride", "Recovery spin", "POWER", False, "Low-load recovery spin.", "Recovery\n- 15m Z1"
    ),
    spec(
        7,
        "Run",
        "Recovery short",
        "PACE",
        False,
        "Short recovery jog with relaxed mechanics.",
        "Warmup\n- 4m Z1\n\nEasy jog\n- 4m Z1\n\nCooldown\n- 4m Z1",
    ),
    spec(
        8,
        "Swim",
        "Technique easy",
        "AUTO",
        True,
        "Easy technique swim. Keep effort controlled.",
        "Warmup\n- 3m Z1\n\nTechnique\n- 6m Z1\n\nCooldown\n- 3m Z1",
    ),
    spec(
        8,
        "Ride",
        "Aerobic steady",
        "POWER",
        False,
        "Steady low-intensity aerobic ride.",
        "Warmup\n- 5m Z1\n\nMain\n- 10m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        8,
        "Run",
        "Short aerobic changes",
        "PACE",
        False,
        "Short aerobic changes with equal easy recoveries.",
        "Warmup\n- 5m Z1\n\n4x\n- 1m Z2\n- 1m Z1\n\nCooldown\n- 5m Z1",
    ),
    spec(
        9,
        "Swim",
        "Easy finish",
        "AUTO",
        True,
        "Easy final swim for synchronization testing.",
        "Warmup\n- 2m Z1\n\nEasy swim\n- 6m Z1\n\nCooldown\n- 2m Z1",
    ),
    spec(
        9,
        "Ride",
        "Easy finish",
        "POWER",
        False,
        "Easy aerobic finish. Remain below Z3.",
        "Warmup\n- 5m Z1\n\nMain\n- 10m Z2\n\nCooldown\n- 5m Z1",
    ),
    spec(
        9,
        "Run",
        "Easy finish",
        "PACE",
        False,
        "Relaxed final run. Keep it conversational.",
        "Warmup\n- 5m Z1\n\nMain\n- 5m Z2\n\nCooldown\n- 5m Z1",
    ),
]


async def seed(limit: int | None) -> None:
    summaries = await list_draft_plans()
    matches = [plan for plan in summaries["draft_plans"] if plan["name"] == "[IA] test-triatlon-1"]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one managed test plan, found {len(matches)}")

    plan_id = matches[0]["id"]
    current = await get_draft_plan(plan_id)
    content_hash = current["content_hash"]
    existing_names = {item["name"] for item in current["plan"]["children"]}
    missing = [item for item in WORKOUTS if item.name not in existing_names]
    selected = missing if limit is None else missing[:limit]

    for workout in selected:
        result = await add_workout_to_draft(
            plan_id=plan_id,
            expected_hash=content_hash,
            name=workout.name,
            description=workout.description,
            activity_type=workout.sport,
            day=workout.day,
            target=workout.target,
            indoor=workout.indoor,
            tags=["test-triatlon-1", "low-load"],
            confirmed=True,
        )
        content_hash = result["content_hash"]
        parsed = result["workout"].get("workout_doc") is not None
        print(f"Added {workout.name}; parsed={parsed}; hash={content_hash[:12]}")

    print(
        f"Plan {plan_id}: added={len(selected)}, previously_present={len(existing_names)}, "
        f"remaining={len(missing) - len(selected)}, calendar_changed=False, garmin_changed=False"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(seed(args.limit))


if __name__ == "__main__":
    main()
