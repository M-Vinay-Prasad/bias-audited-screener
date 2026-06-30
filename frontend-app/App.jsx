import { useState } from "react";
import "./App.css";

const API_BASE = "http://localhost:8000";

function ScoreBar({ score }) {
  const color = score >= 70 ? "#1D9E75" : score >= 50 ? "#BA7517" : "#A32D2D";
  return (
    <div className="score-bar-track">
      <div className="score-bar-fill" style={{ width: `${score}%`, background: color }} />
    </div>
  );
}

function CandidateCard({ candidate }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="candidate-card">
      <div className="candidate-header" onClick={() => setExpanded(!expanded)}>
        <div>
          <p className="candidate-name">{candidate.filename}</p>
          <p className="candidate-id">{candidate.candidate_id}</p>
        </div>
        <div className="candidate-score">
          <span className="score-number">{candidate.score}</span>
          <ScoreBar score={candidate.score} />
        </div>
      </div>
      {expanded && (
        <div className="candidate-detail">
          <p className="detail-label">Why this score</p>
          <p className="detail-reasoning">{candidate.reasoning}</p>
          <div className="req-columns">
            <div>
              <p className="detail-label matched">Matched requirements</p>
              <ul>
                {candidate.matched_requirements.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
            <div>
              <p className="detail-label missing">Missing requirements</p>
              <ul>
                {candidate.missing_requirements.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FairnessPanel({ report }) {
  if (!report) return null;
  return (
    <div className={`fairness-panel ${report.flagged ? "flagged" : "clear"}`}>
      <p className="fairness-title">
        {report.flagged ? "Adverse impact flagged" : "No adverse impact detected"}
      </p>
      <p className="fairness-summary">{report.summary}</p>
      <table className="fairness-table">
        <thead>
          <tr>
            <th>Group</th>
            <th>Advanced</th>
            <th>Total</th>
            <th>Selection rate</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(report.group_stats).map(([group, stats]) => (
            <tr key={group} className={report.flagged_groups.includes(group) ? "row-flagged" : ""}>
              <td>{group}</td>
              <td>{stats.advanced}</td>
              <td>{stats.total}</td>
              <td>{(stats.selection_rate * 100).toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [files, setFiles] = useState([]);
  const [jobDescription, setJobDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [shortlist, setShortlist] = useState([]);
  const [fairnessReport, setFairnessReport] = useState(null);
  const [error, setError] = useState("");

  const handleUploadAndScreen = async () => {
    if (files.length === 0 || !jobDescription.trim()) {
      setError("Add at least one resume and a job description first.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const formData = new FormData();
      files.forEach((f) => formData.append("files", f));
      const uploadRes = await fetch(`${API_BASE}/upload-resumes`, {
        method: "POST",
        body: formData,
      });
      if (!uploadRes.ok) throw new Error("Upload failed");
      const uploadData = await uploadRes.json();

      const screenRes = await fetch(`${API_BASE}/screen`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_description: jobDescription,
          demographics: [], // wire up a real demographic CSV upload for full audit
        }),
      });
      if (!screenRes.ok) throw new Error("Screening failed");
      const screenData = await screenRes.json();
      setShortlist(screenData.shortlist);
      setFairnessReport(screenData.fairness_report);
    } catch (err) {
      setError(err.message || "Something went wrong. Is the backend running on :8000?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>Fair screen</h1>
        <p className="app-subtitle">AI resume screening with a built-in fairness audit</p>
      </header>

      <section className="input-section">
        <label className="field-label">Job description</label>
        <textarea
          value={jobDescription}
          onChange={(e) => setJobDescription(e.target.value)}
          placeholder="Paste the job description here..."
          rows={6}
        />

        <label className="field-label">Resumes</label>
        <input
          type="file"
          multiple
          accept=".txt,.pdf"
          onChange={(e) => setFiles(Array.from(e.target.files))}
        />
        <p className="file-count">{files.length} file{files.length !== 1 ? "s" : ""} selected</p>

        <button onClick={handleUploadAndScreen} disabled={loading} className="primary-btn">
          {loading ? "Screening..." : "Screen candidates"}
        </button>
        {error && <p className="error-text">{error}</p>}
      </section>

      {shortlist.length > 0 && (
        <section className="results-section">
          <div className="shortlist-column">
            <h2>Ranked shortlist</h2>
            {shortlist.map((c) => (
              <CandidateCard key={c.candidate_id} candidate={c} />
            ))}
          </div>
          <div className="fairness-column">
            <h2>Fairness audit</h2>
            <FairnessPanel report={fairnessReport} />
          </div>
        </section>
      )}
    </div>
  );
}
