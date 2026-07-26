"""Tests for no-write previews and MCP surface safety."""

import pytest

from intervals_mcp.mcp_server import add_workout_to_draft, create_draft_plan, mcp


@pytest.mark.asyncio
async def test_create_requires_confirmation_without_loading_credentials() -> None:
    result = await create_draft_plan("Week", "Draft", ["Run"], confirmed=False)
    assert result["status"] == "confirmation_required"
    assert result["calendar_changed"] is False
    assert result["garmin_changed"] is False


@pytest.mark.asyncio
async def test_add_workout_preview_is_structured_and_safe() -> None:
    result = await add_workout_to_draft(
        plan_id=10,
        expected_hash="abc",
        name="Aerobic run",
        description="Warmup\n- 10m Z1\nMain\n- 30m Z2",
        activity_type="Run",
        day=1,
        confirmed=False,
    )
    assert result["status"] == "confirmation_required"
    assert result["proposed_change"]["workout"]["type"] == "Run"
    assert result["calendar_changed"] is False


@pytest.mark.asyncio
async def test_mcp_surface_excludes_calendar_writes() -> None:
    tools = await mcp.list_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    assert set(tools_by_name) == {
        "get_training_context",
        "get_personal_context",
        "set_personal_fact",
        "list_draft_plans",
        "get_draft_plan",
        "create_draft_plan",
        "clone_draft_plan",
        "rename_draft_plan",
        "add_workout_to_draft",
        "update_draft_workout",
        "schedule_draft_plan",
        "unschedule_draft_plan",
    }
    assert not any("event" in name for name in tools_by_name)
    assert tools_by_name["get_training_context"].annotations.readOnlyHint is True
    assert tools_by_name["get_personal_context"].annotations.readOnlyHint is True
    assert tools_by_name["set_personal_fact"].annotations.idempotentHint is True
    assert tools_by_name["create_draft_plan"].annotations.readOnlyHint is False
    assert tools_by_name["create_draft_plan"].annotations.destructiveHint is False
    assert tools_by_name["schedule_draft_plan"].annotations.readOnlyHint is False
    assert tools_by_name["unschedule_draft_plan"].annotations.destructiveHint is True
