"""Tests for private structured athlete memory."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from intervals_mcp.config import Settings
from intervals_mcp.errors import SafetyViolation
from intervals_mcp.personal_context import read_personal_context, set_personal_context


@pytest.fixture
def personal_settings(tmp_path: Path) -> Settings:
    personal_file = tmp_path / "PERSONAL.md"
    personal_file.write_text(
        "# Personal training context\n\n"
        "## Availability\n\n"
        "- **rest_day:** Monday\n\n"
        "## Training preferences\n",
        encoding="utf-8",
    )
    return Settings(
        intervals_api_key=SecretStr("test-key"),
        intervals_athlete_id="0",
        intervals_base_url="https://intervals.test/api/v1",
        personal_context_file=str(personal_file),
    )


def test_set_personal_context_replaces_stable_key(personal_settings: Settings) -> None:
    result = set_personal_context(
        personal_settings,
        "Availability",
        "rest_day",
        "Sunday",
    )

    assert result["changed"] is True
    assert result["previous_value"] == "Monday"
    content = read_personal_context(personal_settings)
    assert "- **rest_day:** Sunday" in content
    assert "Monday" not in content

    repeated = set_personal_context(
        personal_settings,
        "Availability",
        "rest_day",
        "Sunday",
    )
    assert repeated["changed"] is False


def test_set_personal_context_adds_new_key(personal_settings: Settings) -> None:
    set_personal_context(
        personal_settings,
        "Training preferences",
        "cycling_role",
        "Use easy cycling for aerobic volume.",
    )
    assert "- **cycling_role:** Use easy cycling for aerobic volume." in read_personal_context(
        personal_settings
    )


def test_set_personal_context_rejects_secrets(personal_settings: Settings) -> None:
    with pytest.raises(SafetyViolation, match="credential or secret"):
        set_personal_context(
            personal_settings,
            "Coaching notes",
            "intervals_login",
            "API key is abc123",
        )
