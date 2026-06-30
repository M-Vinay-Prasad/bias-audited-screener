"""
Resume parsing and anonymization module.

This is the first stage of the pipeline: turn raw resume text into
structured fields, and produce an ANONYMIZED version (no name, no
university name, no gendered pronouns) that gets sent to the LLM for
scoring. The original (non-anonymized) version is kept separately,
ONLY for the bias audit step later -- never for scoring.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedResume:
    candidate_id: str
    raw_text: str
    name: Optional[str] = None          # kept aside, never sent to scorer
    email: Optional[str] = None         # kept aside, never sent to scorer
    university: Optional[str] = None    # kept aside, never sent to scorer
    skills: list[str] = field(default_factory=list)
    years_experience: Optional[float] = None
    anonymized_text: str = ""


NAME_LINE_RE = re.compile(r"^[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){1,3}$", re.MULTILINE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{8,}\d)")
UNIVERSITY_RE = re.compile(
    r"(University of [\w\s]+|[\w\s]+ University|[\w\s]+ Institute of [\w\s]+|[\w\s]+ College)",
    re.IGNORECASE,
)

# A small, expandable skill vocabulary for the demo. In production this
# would be backed by a proper taxonomy (e.g. ESCO, O*NET, or a vector
# similarity lookup) rather than a hardcoded list.
SKILL_VOCAB = [
    "python", "java", "javascript", "typescript", "react", "node.js", "sql",
    "aws", "docker", "kubernetes", "machine learning", "nlp", "pytorch",
    "tensorflow", "fastapi", "django", "flask", "mongodb", "postgresql",
    "git", "ci/cd", "rest api", "graphql", "html", "css", "c++", "c#",
]


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    return [skill for skill in SKILL_VOCAB if skill in lowered]


def extract_years_experience(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)\+?\s*years?\s+(?:of\s+)?experience", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def anonymize(text: str, name: Optional[str], university: Optional[str]) -> str:
    """
    Strip the signals most correlated with demographic bias before the
    text ever reaches the LLM scorer:
      - candidate name
      - email / phone (proxy for name, also just PII)
      - university name (proxy for socioeconomic background / prestige bias)
      - gendered pronouns, normalized to a neutral form
    This is a defense-in-depth step, not a complete bias fix -- it
    narrows the LLM's ability to anchor on these signals, but bias can
    still creep in via other cues (school location, club names, etc).
    The bias audit module exists precisely because anonymization alone
    is not sufficient -- it's a mitigation, not a guarantee.
    """
    cleaned = text
    if name:
        cleaned = cleaned.replace(name, "[CANDIDATE]")
    if university:
        cleaned = re.sub(re.escape(university), "[UNIVERSITY]", cleaned, flags=re.IGNORECASE)
    cleaned = EMAIL_RE.sub("[EMAIL]", cleaned)
    cleaned = PHONE_RE.sub("[PHONE]", cleaned)

    pronoun_map = {
        r"\bhe\b": "they", r"\bshe\b": "they",
        r"\bhim\b": "them", r"\bher\b": "them",
        r"\bhis\b": "their", r"\bhers\b": "theirs",
    }
    for pattern, repl in pronoun_map.items():
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

    return cleaned


def parse_resume(candidate_id: str, raw_text: str) -> ParsedResume:
    name_match = NAME_LINE_RE.search(raw_text[:200])  # names usually appear near the top
    name = name_match.group(0) if name_match else None

    email_match = EMAIL_RE.search(raw_text)
    email = email_match.group(0) if email_match else None

    uni_match = UNIVERSITY_RE.search(raw_text)
    university = uni_match.group(0) if uni_match else None

    resume = ParsedResume(
        candidate_id=candidate_id,
        raw_text=raw_text,
        name=name,
        email=email,
        university=university,
        skills=extract_skills(raw_text),
        years_experience=extract_years_experience(raw_text),
    )
    resume.anonymized_text = anonymize(raw_text, name, university)
    return resume
