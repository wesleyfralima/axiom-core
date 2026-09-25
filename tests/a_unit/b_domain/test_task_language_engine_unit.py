import tomllib
from datetime import datetime
from importlib import resources
from typing import Any

import pytest

from b_domain.engines.task_language_engine import (
    TaskLanguageEngine,
    build_language_engine,
)
from b_domain.value_objects.enums import Priority

NOW: datetime = datetime(2026, 9, 24, 9, 0)


@pytest.fixture(scope="module")
def default_config() -> dict[str, Any]:
    """The configuration shipped with the package."""
    text: str = (
        resources.files("b_domain.engines")
        .joinpath("task_language_engine.toml")
        .read_text(encoding="utf-8")
    )
    return tomllib.loads(text)


@pytest.fixture(scope="module")
def engine(default_config: dict[str, Any]) -> TaskLanguageEngine:
    return build_language_engine(default_config, {"work": "ctx_work"})


@pytest.mark.unit
def test_shipped_config_has_every_section(default_config: dict[str, Any]) -> None:
    for key in ("archetypes", "lexicons", "modifiers", "priority_map", "date_words"):
        assert key in default_config


@pytest.mark.unit
def test_extracts_priority_duration_context_and_date(
    engine: TaskLanguageEngine,
) -> None:
    fields = engine.infer("Refatorar banco de dados amanhã 30m !!! @work", now=NOW)

    assert fields.title == "Refatorar banco de dados"
    assert fields.priority == Priority.HIGH
    assert fields.duration == 30
    assert fields.context_id == "ctx_work"
    assert fields.due_date is not None
    assert fields.due_date.date() == datetime(2026, 9, 25).date()


@pytest.mark.unit
def test_unknown_context_passes_through(engine: TaskLanguageEngine) -> None:
    fields = engine.infer("Lavar louça @casa", now=NOW)

    assert fields.context_id == "casa"


@pytest.mark.unit
def test_contexts_map_defaults_to_empty(default_config: dict[str, Any]) -> None:
    engine = build_language_engine(default_config)

    assert engine.infer("Ligar @work", now=NOW).context_id == "work"


@pytest.mark.unit
def test_english_priority_keyword(engine: TaskLanguageEngine) -> None:
    fields = engine.infer("Write report p1", now=NOW, lang="en")

    assert fields.priority == Priority.HIGH
