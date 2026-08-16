"""Profile extraction (the preprocessing step before the graph)."""

from pathlib import Path

import job_scout.profile as profile_mod
from job_scout.profile import extract_profile
from job_scout.tools.cv_reader import extract_cv_text
from tests.conftest import structured_llm


def test_extract_profile(monkeypatch, sample_profile):
    monkeypatch.setattr(profile_mod, "get_chat_model", lambda *a, **k: structured_llm(sample_profile))
    result = extract_profile("some cv text")
    assert result is sample_profile


def test_extract_profile_heuristic_fallback(monkeypatch):
    """When LLM is unavailable, fallback heuristic extracts structured fields accurately."""
    def failing_llm(*args, **kwargs):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(profile_mod, "get_chat_model", failing_llm)

    cv_path = Path(__file__).resolve().parent.parent / "data" / "fixture_cvs" / "junior_ds_us.pdf"
    cv_text = extract_cv_text(cv_path)

    profile = extract_profile(cv_text)
    assert profile.name == "Maya Chen"
    assert profile.seniority == "junior"
    assert "Data Scientist" in profile.primary_roles or "Data Analyst" in profile.primary_roles
    assert "python" in profile.skills
    assert "sql" in profile.skills
    assert profile.years_experience == 1.5
    assert len(profile.locations) > 0
    assert "English" in profile.languages

