# Fair Screen — bias-audited resume screener

An AI resume screening tool that doesn't just rank candidates — it audits
its own scores for demographic bias, using the same four-fifths rule the
EEOC uses to detect adverse impact in hiring.

## Why this project

In 2026, AI resume screening is standard (87% of companies use it), but
most tools optimize for speed and accuracy while treating fairness as a
secondary concern. The EU AI Act now classifies hiring algorithms as
high-risk systems, requiring documented bias testing and human oversight
from August 2026. This project builds that fairness check directly into
the pipeline instead of bolting it on after the fact.

## How it works

1. **Parse + anonymize** — resumes are parsed into structured fields, then
   stripped of name, contact info, and university name before scoring.
2. **Score via Claude** — the anonymized resume + job description are sent
   to Claude, which returns a score (0-100), matched/missing requirements,
   and a plain-English reasoning string — full explainability, not a
   black-box number.
3. **Bias audit** — after scoring, demographic labels (kept separate from
   the scoring pipeline the whole time) are reattached just to check: does
   any group's selection rate fall below 80% of the top group's rate at the
   shortlist threshold? If so, it's flagged for human review.
4. **Dashboard** — recruiters see the ranked shortlist and the fairness
   report side by side.

## Project structure

```
backend/
  parser.py          resume parsing + anonymization
  scorer.py          Claude API scoring engine
  fairness_audit.py  four-fifths rule bias audit
  main.py            FastAPI app wiring it together
  requirements.txt
frontend/
  App.jsx            React dashboard
  App.css
```

## Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
export GEMINI_API_KEY=your_key_here   # free, get one at aistudio.google.com/apikey
uvicorn main:app --reload --port 8000
```

### Frontend

You'll need a Vite + React project shell (this folder only has the two
files you edit — `App.jsx` and `App.css`). Quick setup:

```bash
npm create vite@latest frontend-app -- --template react
cd frontend-app
# replace src/App.jsx and src/App.css with the files from this project
npm install
npm run dev
```

Open `http://localhost:5173`, paste a job description, upload a few
`.txt` resumes, and click "Screen candidates."

## Honest limitations (say these out loud in an interview)

- The demo only accepts `.txt` resumes — wire in a PDF text extraction
  step (e.g. `pdfplumber`) for real PDF uploads.
- The anonymization regex is a starting point, not a guarantee — names
  outside the expected pattern, or indirect signals (club names, school
  locations), can still leak through.
- The fairness audit needs demographic labels to run. In a real product,
  these would come from voluntary, separately-stored candidate
  self-identification data — never inferred from a name or photo, which
  would reintroduce exactly the bias you're trying to detect.
- The four-fifths rule is a starting heuristic, not a substitute for a
  real legal/compliance review before this touches live hiring decisions.

## What to say about this project in an interview

"I built a resume screener that scores candidates with Claude, but the
part I'm most proud of is the audit layer — it checks the AI's own scores
for adverse impact using the same statistical rule the EEOC uses, and
flags any group whose pass rate falls too far below the top group's. The
scoring engine never sees demographic data; that's only reattached
afterward, purely to audit fairness."
