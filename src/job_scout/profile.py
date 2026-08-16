"""Extract a structured candidate profile from CV text.

This is a preprocessing step that runs *before* the job-finding graph: the graph
takes the resulting ``Profile`` as input and focuses on searching and ranking
jobs. Keeping extraction out of the graph keeps the graph about one thing —
finding jobs — and lets a caller (like the UI) extract once and reuse it.
"""

from __future__ import annotations

import contextlib
import re

from job_scout.config import get_settings
from job_scout.graph.schemas import Profile, Seniority
from job_scout.llm import get_chat_model

EXTRACT_PROFILE_PROMPT_NAME = "extract_profile"

EXTRACT_PROFILE_PROMPT = """You are a recruiting assistant. Read the CV text below and extract a structured candidate profile.

Fill in every field:
- name: the candidate's name, or null if not present.
- seniority: one of junior, mid, senior, lead, or unknown.
- primary_roles: the job titles/roles this person is a fit for, ordered with their current or most recent role first.
- skills: a list of their skills, lowercased.
- years_experience: total years of professional experience as a number, or null.
- locations: locations where they could work.
- languages: spoken languages.
- remote_ok: true if they are open to remote work.
- raw_summary: a 3-4 sentence summary, starting with their most recent experience.

CV text:
{cv_text}
"""

_KNOWN_LANGUAGES = {
    "english",
    "portuguese",
    "português",
    "spanish",
    "español",
    "german",
    "deutsch",
    "hindi",
    "french",
    "français",
    "malayalam",
    "mandarin",
    "italian",
    "italiano",
}

_ROLE_PATTERNS: list[tuple[str, str]] = [
    ("data scientist", r"\bdata scientist\b"),
    ("machine learning engineer", r"\bmachine learning engineer\b|\bml engineer\b"),
    ("data analyst", r"\bdata analyst\b"),
    ("data product manager", r"\bdata product manager\b"),
    ("product manager", r"\bproduct manager\b"),
    ("software engineer", r"\bsoftware engineer\b"),
    ("backend engineer", r"\bbackend engineer\b"),
    ("frontend engineer", r"\bfrontend engineer\b"),
    ("fullstack engineer", r"\bfullstack engineer\b"),
    ("devops engineer", r"\bdevops engineer\b"),
    ("mlops engineer", r"\bmlops engineer\b|\bmlops\b"),
    ("analytics engineer", r"\banalytics engineer\b"),
    ("business analyst", r"\bbusiness analyst\b"),
    ("mathematics teacher", r"\bmathematics teacher\b"),
]


_COMMON_TECHS = (
    "python",
    "java",
    "c++",
    "c#",
    ".net",
    "javascript",
    "typescript",
    "react",
    "node.js",
    "sql",
    "pl/sql",
    "oracle",
    "postgres",
    "postgresql",
    "kafka",
    "kafka streams",
    "spring boot",
    "spring cloud",
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
    "linux",
    "unix",
    "perl",
    "bash",
    "git",
    "ci/cd",
    "rest api",
    "microservices",
    "pandas",
    "scikit-learn",
    "matplotlib",
    "jupyter",
    "tableau",
    "pytorch",
    "tensorflow",
    "mlflow",
    "spark",
    "feature stores",
    "llm fine-tuning",
    "statistics",
    "excel",
)


def _heuristic_extract_profile(cv_text: str) -> Profile:
    """Deterministic fallback extractor when LLM credentials or services are unavailable."""
    lines = [line.strip() for line in cv_text.splitlines() if line.strip()]
    if not lines:
        return Profile(
            name="Candidate",
            seniority="unknown",
            primary_roles=["Software Engineer"],
            skills=[],
            locations=[],
            languages=["English"],
            remote_ok=False,
            raw_summary="",
        )

    is_linkedin_pdf = lines[0].lower() in {"contact", "contato"} or any(
        "linkedin.com/in/" in line.lower() for line in lines[:10]
    )

    name = lines[0]
    locations: list[str] = []
    languages: list[str] = []
    headline_role = ""

    if is_linkedin_pdf:
        summary_idx = -1
        for i, line in enumerate(lines):
            if line.lower() in {"summary", "resumo", "zusammenfassung", "perfil", "sobre"}:
                summary_idx = i
                break

        if summary_idx > 0:
            if summary_idx >= 3:
                name = lines[summary_idx - 3]
                headline_role = lines[summary_idx - 2]
                locations.append(lines[summary_idx - 1])
            elif summary_idx == 2:
                name = lines[0]
                locations.append(lines[1])

        in_skills = False
        in_languages = False
        sidebar_skills = []
        for i, line in enumerate(lines[:summary_idx if summary_idx > 0 else 25]):
            line_clean = line.strip()
            if line_clean.lower() in {"top skills", "principais competências", "habilidades"}:
                in_skills = True
                in_languages = False
                continue
            if line_clean.lower() in {"languages", "idiomas", "sprachen"}:
                in_skills = False
                in_languages = True
                continue
            if line_clean.lower() in {"contact", "contato", "summary", "resumo"}:
                in_skills = False
                in_languages = False
                continue

            if in_skills and line_clean:
                sidebar_skills.append(line_clean.lower())
            elif in_languages and line_clean:
                if summary_idx > 0 and i >= summary_idx - 3:
                    in_languages = False
                    continue
                lang_name = re.split(r"[\(\[\:]", line_clean)[0].strip()
                if (
                    lang_name
                    and lang_name not in languages
                    and any(known in lang_name.lower() for known in _KNOWN_LANGUAGES)
                ):
                    languages.append(lang_name)
    else:
        # Standard CV layout
        if len(lines) > 1 and ("|" in lines[1] or "@" in lines[1]):
            parts = [p.strip() for p in lines[1].split("|")]
            for p in parts:
                if "@" in p or "http" in p:
                    continue
                sub_items = [s.strip() for s in p.split(",")]
                if any(s.lower() in _KNOWN_LANGUAGES for s in sub_items):
                    for s in sub_items:
                        if s.lower() in _KNOWN_LANGUAGES and s not in languages:
                            languages.append(s)
                        elif s and s.lower() not in _KNOWN_LANGUAGES and not locations:
                            locations.append(s)
                elif not locations and p:
                    locations.append(p)

    text_lower = cv_text.lower()
    _section_ends = "experience|berufserfahrung|experiência|skills|kenntnisse|education|ausbildung|top skills"
    summary_match = re.search(
        rf"(?:summary|zusammenfassung|resumo|perfil|about|sobre)\s*\n(.*?)(?=\n(?:{_section_ends}|\Z))",
        cv_text,
        re.IGNORECASE | re.DOTALL,
    )
    if summary_match:
        raw_summary = summary_match.group(1).strip().replace("\n", " ")
        first_summary_part = raw_summary.split(".")[0].lower()
    else:
        raw_summary = " ".join(lines[1:5])
        first_summary_part = raw_summary.lower()

    # Years of experience
    years_exp: float | None = None
    m_exp = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:years?|anos|jahren|jahre)", text_lower)
    if m_exp:
        with contextlib.suppress(ValueError):
            years_exp = float(m_exp.group(1))

    # Seniority extraction
    seniority: Seniority = "unknown"
    if any(k in first_summary_part for k in ("lead ", "principal", "staff", "head of")):
        seniority = "lead"
    elif "senior" in first_summary_part or "sr." in first_summary_part:
        seniority = "senior"
    elif any(k in first_summary_part for k in ("junior", "jr.", "entry-level", "entry level", "transitioning")):
        seniority = "junior"
    elif "mid " in first_summary_part or "intermediate" in first_summary_part:
        seniority = "mid"
    elif years_exp and years_exp >= 6.0:
        seniority = "senior"
    elif years_exp and years_exp >= 3.0:
        seniority = "mid"
    elif years_exp:
        seniority = "junior"

    remote_ok = any(k in text_lower for k in ("remote", "remoto", "offen für remote", "híbrido", "hybrid"))

    # Skills extraction: section + sidebar + keyword detection
    skills: list[str] = []
    if is_linkedin_pdf and sidebar_skills:
        for sk in sidebar_skills:
            if sk not in skills:
                skills.append(sk)

    skills_match = re.search(
        r"(?:skills|kenntnisse|competências|habilidades|technologies)\s*\n([^\n]+(?:\n[^\n]+)?)",
        cv_text,
        re.IGNORECASE,
    )
    if skills_match:
        raw_skills = skills_match.group(1).replace("\n", " ")
        _headers = (
            "Experience",
            "Berufserfahrung",
            "Experiência",
            "Education",
            "Ausbildung",
            "Formação",
            "Projects",
            "Projekte",
        )
        for header in _headers:
            if header.lower() in raw_skills.lower():
                raw_skills = re.split(rf"\b{header}\b", raw_skills, flags=re.IGNORECASE)[0]
        for s in re.split(r"[,;•|]", raw_skills):
            s_clean = s.strip().lower()
            s_clean = re.sub(r"^(?:basic|strong|advanced|good|grundkenntnisse)\s+", "", s_clean).strip()
            s_clean = s_clean.rstrip(".").strip()
            if s_clean and len(s_clean) > 1 and s_clean not in skills:
                skills.append(s_clean)

    for tech in _COMMON_TECHS:
        if re.search(rf"\b{re.escape(tech)}\b", text_lower) and tech not in skills:
            skills.append(tech)

    # Primary roles extraction
    primary_roles: list[str] = []
    if headline_role:
        for part in headline_role.split("|"):
            p_clean = part.strip()
            if any(
                role_word in p_clean.lower()
                for role_word in [
                    "developer",
                    "engineer",
                    "consultant",
                    "architect",
                    "analyst",
                    "manager",
                    "specialist",
                ]
            ):
                primary_roles.append(p_clean)

    for r_title, r_regex in _ROLE_PATTERNS:
        if re.search(r_regex, text_lower):
            t_cap = " ".join(w.capitalize() for w in r_title.split())
            if t_cap not in primary_roles:
                primary_roles.append(t_cap)

    if not primary_roles:
        primary_roles = ["Software Engineer"]

    return Profile(
        name=name,
        seniority=seniority,
        primary_roles=primary_roles[:3],
        skills=skills[:15],
        years_experience=years_exp,
        locations=locations,
        languages=languages or ["English", "Portuguese"],
        remote_ok=remote_ok,
        raw_summary=raw_summary,
    )


def extract_profile(
    cv_text: str, *, thread_id: str | None = None, tags: list[str] | None = None, model: str | None = None
) -> Profile:
    """Extract a structured profile from CV text with a single LLM call.

    Pass ``thread_id`` and ``tags`` to trace the call in Opik (grouped with the
    search run on the same thread). ``model`` overrides ``SCOUT_MODEL`` — used
    by the eval harness to compare extractors.
    """
    from job_scout.tracing import get_tracer

    settings = get_settings()
    tracer = get_tracer(thread_id, tags or ["extract"]) if thread_id else None
    config = {"callbacks": [tracer]} if tracer else {}

    try:
        llm = get_chat_model(model or settings.scout_model, temperature=0.0).with_structured_output(Profile)
        profile: Profile = llm.invoke(EXTRACT_PROFILE_PROMPT.format(cv_text=cv_text), config=config)
    except Exception:
        # Resilient heuristic fallback in case of LLM credentials / model errors
        profile = _heuristic_extract_profile(cv_text)

    if tracer:
        tracer.flush()
    return profile
