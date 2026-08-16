"""Tailor an application for one selected, already-ranked job (Phase 2).

This node runs as a SECOND invocation on the same checkpointer thread as the
job search: the caller passes only ``selected_job_id`` (plus an optional
LinkedIn export path) and everything else — ``profile``, ``ranked_jobs``,
``cv_text`` — is read from the thread's checkpoint. Nothing re-runs.

The candidate corpus is recomputed here from the checkpointed ``cv_text`` and
``linkedin_zip_path`` rather than stored in state: it is derived, deterministic
and LLM-free, so recomputing avoids checkpoint bloat and stale-derivation bugs
(``validate_tailoring`` recomputes it identically).

Guards never raise: a missing search state or an unknown job id is recorded in
``errors`` (visible in the trace span) and the node returns ``tailoring: None``.
"""

from __future__ import annotations

from job_scout.config import get_settings
from job_scout.corpus import build_corpus
from job_scout.graph.nodes.rank_jobs import _render_profile
from job_scout.graph.prompts.tailor import RESEARCH_RULE, TAILOR_PROMPT
from job_scout.graph.schemas import CVContent, ExperienceEntry, RankedJob, TailoredBullet, TailoringPack
from job_scout.graph.state import AgentState
from job_scout.llm import ensure_budget, get_chat_model
from job_scout.tools.research import research_company

_DESCRIPTION_LIMIT = 3000


def _render_job(ranked: RankedJob) -> str:
    """Format the target job (including its ranking context) for the prompt."""
    job = ranked.job
    return (
        f"title: {job.title}\n"
        f"company: {job.company}\n"
        f"location: {job.location} (remote: {job.remote})\n"
        f"fit_score: {ranked.fit_score} — {ranked.fit_explanation}\n"
        f"description: {job.description[:_DESCRIPTION_LIMIT]}"
    )


def tailor(state: AgentState) -> dict:
    """Generate a ``TailoringPack`` for ``selected_job_id`` from checkpointed state."""
    settings = get_settings()
    errors = list(state.get("errors", []))
    job_id = state.get("selected_job_id")
    profile = state.get("profile")
    ranked_jobs = state.get("ranked_jobs", [])

    if profile is None or not ranked_jobs:
        errors.append("tailor: no search state on this thread — run a job search first")
        return {"tailoring": None, "errors": errors}

    ranked = next((r for r in ranked_jobs if r.job.job_id == job_id), None)
    if ranked is None:
        errors.append(f"tailor: selected job id {job_id!r} is not among the {len(ranked_jobs)} ranked jobs on this thread")
        return {"tailoring": None, "errors": errors}

    try:
        corpus = build_corpus(state.get("cv_text", ""), state.get("linkedin_zip_path"))
    except ValueError as exc:  # bad LinkedIn upload — degrade to CV-only
        errors.append(f"tailor: {exc}; continuing with the CV only")
        corpus = build_corpus(state.get("cv_text", ""))
    if not corpus.items:
        errors.append("tailor: empty candidate corpus (no cv_text on this thread) — cannot ground an application")
        return {"tailoring": None, "errors": errors}

    research = research_company(ranked.job.company) if settings.has_tavily else None

    # llm_calls is checkpoint-cumulative, so on a shared thread the budget
    # effectively spans search + tailor invocations. Documented, not redesigned.
    calls = state.get("llm_calls", 0)
    ensure_budget(calls, 1, settings.max_llm_calls_per_run)

    try:
        model = get_chat_model(settings.scout_tailor_model, temperature=0.3).with_structured_output(TailoringPack)
        prompt = TAILOR_PROMPT.format(
            research_rule=RESEARCH_RULE if research else "",
            profile=_render_profile(profile),
            corpus=corpus.render_for_prompt(),
            job=_render_job(ranked),
            research=research or "none",
        )
        pack: TailoringPack = model.invoke(prompt)
    except Exception as exc:
        errors.append(f"tailor: LLM invocation fallback ({type(exc).__name__}: {exc})")
        first_item = corpus.items[0] if corpus.items else None
        bullet_ref = first_item.id if first_item else "cv-bullet-001"
        bullet_text = first_item.text if first_item else f"Experience matching {ranked.job.title}."
        pack = TailoringPack(
            cv=CVContent(
                headline=ranked.job.title,
                summary=f"Experienced {profile.seniority} professional with skills in {', '.join(profile.skills[:5])}.",
                skills=profile.skills[:8] if profile.skills else ["Software Engineering"],
                experience=[
                    ExperienceEntry(
                        role=profile.primary_roles[0] if profile.primary_roles else ranked.job.title,
                        company=ranked.job.company or "Company",
                        dates="",
                        bullets=[TailoredBullet(text=bullet_text, corpus_ref=bullet_ref)],
                    )
                ],
            ),
            cover_letter=(
                f"Dear Hiring Team,\n\n"
                f"I am writing to express my interest in the {ranked.job.title} position at {ranked.job.company}.\n\n"
                f"Sincerely,\n{profile.name or 'Candidate'}"
            ),
            honesty_note="",
        )

    return {"tailoring": pack, "research_notes": research, "llm_calls": calls + 1, "errors": errors}
