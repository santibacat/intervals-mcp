"""Private, structured Markdown memory for durable athlete context."""

import re
from pathlib import Path
from typing import Final

from .config import Settings
from .errors import SafetyViolation

SECTIONS: Final[tuple[str, ...]] = (
    "Profile",
    "Goals and events",
    "Availability",
    "Training preferences",
    "Performance markers",
    "Equipment and integrations",
    "Health and constraints",
    "Coaching notes",
)
KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
SENSITIVE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(api[_ -]?key|password|passwd|access[_ -]?token|bearer\s+|secret|\.env)"
)


def personal_context_path(settings: Settings) -> Path:
    path = Path(settings.personal_context_file)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path


def read_personal_context(settings: Settings) -> str:
    path = personal_context_path(settings)
    if not path.exists():
        raise SafetyViolation(f"Personal context file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def set_personal_context(
    settings: Settings,
    section: str,
    key: str,
    value: str,
) -> dict[str, str | bool | None]:
    """Insert or replace one scoped key without rewriting unrelated user content."""

    if section not in SECTIONS:
        raise SafetyViolation(f"Unsupported personal-context section: {section}")
    if not KEY_PATTERN.fullmatch(key):
        raise SafetyViolation("Context key must be 2–64 lowercase letters, digits, or underscores")
    clean_value = " ".join(value.split()).strip()
    if not clean_value or len(clean_value) > 500:
        raise SafetyViolation("Context value must contain between 1 and 500 characters")
    if SENSITIVE_PATTERN.search(key) or SENSITIVE_PATTERN.search(clean_value):
        raise SafetyViolation("Refusing to store a credential or secret in personal context")

    path = personal_context_path(settings)
    text = read_personal_context(settings)
    lines = text.splitlines()
    heading = f"## {section}"
    try:
        section_start = lines.index(heading)
    except ValueError as exc:
        raise SafetyViolation(f"Missing section in personal context: {section}") from exc

    section_end = next(
        (index for index in range(section_start + 1, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    prefix = f"- **{key}:** "
    previous: str | None = None
    changed = True
    for index in range(section_start + 1, section_end):
        if not lines[index].startswith(prefix):
            continue
        previous = lines[index][len(prefix) :]
        replacement = f"{prefix}{clean_value}"
        changed = lines[index] != replacement
        lines[index] = replacement
        break
    else:
        insertion = section_end
        while insertion > section_start + 1 and not lines[insertion - 1].strip():
            insertion -= 1
        lines.insert(insertion, f"{prefix}{clean_value}")

    if changed:
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        temporary.replace(path)
    return {
        "section": section,
        "key": key,
        "value": clean_value,
        "previous_value": previous,
        "changed": changed,
    }
