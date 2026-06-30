"""
FastAPI app tying the pipeline together:
  upload resumes -> parse + anonymize -> score via Gemini -> fairness audit
  -> return ranked shortlist + fairness report to the frontend.
"""

import csv
import io

import pdfplumber
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from parser import parse_resume
from scorer import score_batch
from fairness_audit import run_fairness_audit

app = FastAPI(title="Bias-Audited Resume Screener")

app.add_middleware(
    CORSMiddleware,
    # Allow both localhost and 127.0.0.1 -- browsers treat these as different
    # origins even though they point to the same machine, and Vite's dev
    # server URL can vary between the two depending on how it's launched.
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for the demo -- swap for a real DB before any real use.
CANDIDATE_STORE: dict[str, dict] = {}

# Demographics live in their own store, completely separate from the
# scoring pipeline -- this mirrors the real-world requirement that this
# data must never reach the LLM doing the scoring, only the audit step.
DEMOGRAPHICS_STORE: dict[str, str] = {}  # candidate_id (by filename) -> group


def extract_text_from_pdf(raw_bytes: bytes) -> str:
    """Pull plain text out of a PDF using pdfplumber, page by page."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_text(filename: str, raw_bytes: bytes) -> str:
    """Route to the right extraction method based on file extension."""
    if filename.lower().endswith(".pdf"):
        return extract_text_from_pdf(raw_bytes)
    # .txt and anything else: best-effort decode
    return raw_bytes.decode("utf-8", errors="ignore")


class DemographicLabel(BaseModel):
    candidate_id: str
    group: str


class ScreenRequest(BaseModel):
    job_description: str
    demographics: list[DemographicLabel] = []  # optional, for the audit only


@app.post("/upload-resumes")
async def upload_resumes(files: list[UploadFile] = File(...)):
    """Parse and anonymize each uploaded resume. Returns candidate_ids."""
    candidate_ids = []
    for i, file in enumerate(files):
        raw_bytes = await file.read()
        text = extract_text(file.filename, raw_bytes)
        candidate_id = f"cand_{i:04d}"
        parsed = parse_resume(candidate_id, text)
        CANDIDATE_STORE[candidate_id] = {
            "filename": file.filename,
            "parsed": parsed,
        }
        candidate_ids.append(candidate_id)
    return {"candidate_ids": candidate_ids, "count": len(candidate_ids)}


@app.post("/upload-demographics")
async def upload_demographics(file: UploadFile = File(...)):
    """
    Upload a CSV mapping resume filenames to a demographic group label,
    e.g.:
        filename,group
        alice_resume.pdf,Group A
        bob_resume.pdf,Group B

    This data is stored separately and is ONLY used by the fairness
    audit after scoring -- it never touches the scoring prompt itself.
    """
    raw_bytes = await file.read()
    text = raw_bytes.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None or "filename" not in reader.fieldnames or "group" not in reader.fieldnames:
        raise HTTPException(400, "CSV must have 'filename' and 'group' columns.")

    loaded = 0
    for row in reader:
        filename = row["filename"].strip()
        group = row["group"].strip()
        if filename and group:
            DEMOGRAPHICS_STORE[filename] = group
            loaded += 1

    return {"loaded": loaded, "groups": sorted(set(DEMOGRAPHICS_STORE.values()))}


@app.post("/screen")
async def screen_candidates(request: ScreenRequest):
    """Score all uploaded candidates against the JD, then run the fairness audit."""
    if not CANDIDATE_STORE:
        raise HTTPException(400, "No resumes uploaded yet. Call /upload-resumes first.")

    candidates_for_scoring = [
        (cid, data["parsed"].anonymized_text) for cid, data in CANDIDATE_STORE.items()
    ]

    score_results = score_batch(candidates_for_scoring, request.job_description)
    scores_by_id = {r.candidate_id: r.score for r in score_results}

    shortlist = sorted(
        [
            {
                "candidate_id": r.candidate_id,
                "filename": CANDIDATE_STORE[r.candidate_id]["filename"],
                "score": r.score,
                "matched_requirements": r.matched_requirements,
                "missing_requirements": r.missing_requirements,
                "reasoning": r.reasoning,
            }
            for r in score_results
        ],
        key=lambda x: x["score"],
        reverse=True,
    )

    # Build demographics keyed by candidate_id, looking them up by the
    # original filename -- this is the moment the two separate stores
    # (scoring results + demographics) get joined, purely for auditing.
    demo_by_candidate_id = {}
    for cid, data in CANDIDATE_STORE.items():
        filename = data["filename"]
        if filename in DEMOGRAPHICS_STORE:
            demo_by_candidate_id[cid] = DEMOGRAPHICS_STORE[filename]
    # Explicit client-provided demographics (if any) take priority/override.
    for d in request.demographics:
        demo_by_candidate_id[d.candidate_id] = d.group

    fairness_report = None
    if demo_by_candidate_id:
        report = run_fairness_audit(scores_by_id, demo_by_candidate_id)
        fairness_report = {
            "threshold_score": report.threshold_score,
            "flagged": report.flagged,
            "flagged_groups": report.flagged_groups,
            "summary": report.summary,
            "group_stats": {
                group: {
                    "total": s.total,
                    "advanced": s.advanced,
                    "selection_rate": round(s.selection_rate, 3),
                }
                for group, s in report.group_stats.items()
            },
        }

    return {"shortlist": shortlist, "fairness_report": fairness_report}


@app.get("/health")
async def health():
    return {"status": "ok"}

