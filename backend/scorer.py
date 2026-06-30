"""
LLM scoring engine.

Sends the ANONYMIZED resume text + job description to Google Gemini
(free tier, no credit card needed), and asks for a structured score +
reasoning. Structured output (JSON) makes the result easy to store,
rank, and -- crucially -- to show the recruiter *why* a candidate
scored the way they did. That explainability is not a nice-to-have:
under the EU AI Act's high-risk classification for hiring algorithms
(effective Aug 2026), an unexplainable score is a compliance liability,
not just bad UX.
"""

import json
import os
from dataclasses import dataclass

import google.generativeai as genai

MODEL = "gemini-2.5-flash-lite"  # most generous free-tier daily quota (1,500+ RPD)

SCORING_SYSTEM_PROMPT = """You are a fair, evidence-based resume screener.
You will be given an anonymized resume (no name, no university, no contact
info) and a job description. Score how well the candidate's skills and
experience match the role.

Rules:
- Base your score ONLY on skills, experience, and demonstrated impact.
- Never infer or factor in gender, ethnicity, age, or any demographic trait,
  even if implied indirectly (e.g. by club names, hobbies, or phrasing style).
- If the resume lacks information to judge a requirement, say so explicitly
  rather than guessing.
- Respond with ONLY valid JSON, no markdown fences, no preamble.

Output schema:
{
  "score": <integer 0-100>,
  "matched_requirements": [<string>, ...],
  "missing_requirements": [<string>, ...],
  "reasoning": "<2-3 sentence plain-English explanation of the score>"
}"""


@dataclass
class ScoreResult:
    candidate_id: str
    score: int
    matched_requirements: list[str]
    missing_requirements: list[str]
    reasoning: str


def get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get a free key from Google AI Studio "
            "(aistudio.google.com/apikey) and set it as an environment variable."
        )
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL, system_instruction=SCORING_SYSTEM_PROMPT)


def score_resume(model, candidate_id: str, anonymized_resume: str, job_description: str) -> ScoreResult:
    user_prompt = f"""JOB DESCRIPTION:
{job_description}

ANONYMIZED RESUME:
{anonymized_resume}

Score this candidate against the job description, following the rules above."""

    response = model.generate_content(user_prompt)

    raw_text = response.text.strip()
    # Defensive: strip accidental markdown fences if the model adds them anyway
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`").lstrip("json").strip()

    data = json.loads(raw_text)
    return ScoreResult(
        candidate_id=candidate_id,
        score=int(data["score"]),
        matched_requirements=data.get("matched_requirements", []),
        missing_requirements=data.get("missing_requirements", []),
        reasoning=data.get("reasoning", ""),
    )


def score_batch(candidates: list[tuple[str, str]], job_description: str) -> list[ScoreResult]:
    """candidates: list of (candidate_id, anonymized_resume_text)"""
    model = get_client()
    results = []
    for candidate_id, anonymized_text in candidates:
        try:
            result = score_resume(model, candidate_id, anonymized_text, job_description)
            results.append(result)
        except (json.JSONDecodeError, KeyError) as e:
            # Never let one bad LLM response crash the whole batch --
            # flag it for human review instead of silently dropping it.
            results.append(ScoreResult(
                candidate_id=candidate_id, score=0,
                matched_requirements=[], missing_requirements=[],
                reasoning=f"SCORING_ERROR: needs manual review ({e})",
            ))
    return results
