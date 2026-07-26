"""Small, permissive models for the evolving Intervals.icu API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIModel(BaseModel):
    """Accept response fields added by Intervals.icu without breaking clients."""

    model_config = ConfigDict(extra="allow")


class Workout(APIModel):
    id: int | None = None
    name: str
    description: str = ""
    type: str
    folder_id: int | None = None
    day: int | None = None
    target: Literal["AUTO", "POWER", "HR", "PACE"] | None = None
    indoor: bool | None = None
    updated: str | None = None
    moving_time: int | None = None
    icu_training_load: int | None = None
    workout_doc: dict[str, Any] | None = None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_null_description(cls, value: Any) -> Any:
        return "" if value is None else value


class Plan(APIModel):
    id: int
    type: Literal["PLAN", "FOLDER"]
    name: str
    description: str = ""
    visibility: Literal["PRIVATE", "PUBLIC"] | None = None
    children: list[Workout] = Field(default_factory=list)
    activity_types: list[str] = Field(default_factory=list)
    duration_weeks: int | None = None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_null_description(cls, value: Any) -> Any:
        return "" if value is None else value

    @field_validator("children", "activity_types", mode="before")
    @classmethod
    def normalize_null_lists(cls, value: Any) -> Any:
        return [] if value is None else value


class WorkoutDraft(BaseModel):
    """A structured workout to place on a library plan."""

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=20_000)
    type: str = Field(min_length=1, max_length=80)
    day: int = Field(ge=0, le=730)
    target: Literal["AUTO", "POWER", "HR", "PACE"] = "AUTO"
    indoor: bool | None = None
    time: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def require_structured_step(cls, value: str) -> str:
        if not any(line.lstrip().startswith("-") for line in value.splitlines()):
            raise ValueError("description must contain at least one Intervals.icu step ('- ...')")
        return value


class DraftPlanSummary(BaseModel):
    id: int
    name: str
    description: str
    workout_count: int
    content_hash: str
