"""AI Resume ATS Checker - Streamlit app powered by Claude."""

import io
import json
import os
import re

import anthropic
import streamlit as st
from docx import Document
from pypdf import PdfReader

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_RESUME_CHARS = 20000
MAX_JD_CHARS = 8000

SYSTEM_PROMPT = """You are an expert technical recruiter and ATS (Applicant Tracking System) specialist.
You analyze resumes honestly and strictly. Never invent facts that are not in the resume.
Respond with a single valid JSON object only, with no markdown fences and no extra text."""

ANALYSIS_PROMPT = """Analyze the resume below for ATS compatibility and quality.
{jd_block}
Return JSON with exactly this schema:
{{
  "overall_score": <integer 0-100>,
  "score_breakdown": {{
    "formatting_and_structure": <integer 0-100>,
    "keywords_and_skills": <integer 0-100>,
    "work_experience_impact": <integer 0-100>,
    "education_and_certifications": <integer 0-100>,
    "readability_and_clarity": <integer 0-100>
  }},
  "summary": "<2-3 sentence overall assessment>",
  "strengths": ["<string>", ...],
  "weaknesses": ["<string>", ...],
  "missing_keywords": ["<string>", ...],
  "improvements": [
    {{"priority": "High|Medium|Low", "section": "<resume section>", "issue": "<what is wrong>", "suggestion": "<specific fix>"}}
  ],
  "rewrite_examples": [
    {{"original": "<line from the resume>", "improved": "<stronger version, no invented facts>"}}
  ]
}}

Scoring guidance: be realistic. A typical average resume scores 55-70. Reserve 85+ for excellent resumes.
Give 5-8 improvements and 2-4 rewrite examples. If no job description is provided, judge against general best practices
and infer the likely target role from the resume.

RESUME:
<resume>
{resume}
</resume>
"""


# ---------------------------------------------------------------- file parsing
def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from a PDF, DOCX or TXT upload."""
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValueError("This PDF is password protected.")
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts).strip()
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore").strip()
    raise ValueError("Unsupported file type. Please upload a PDF, DOCX or TXT file.")


# ------------------------------------------------------------------ Claude call
def parse_json_response(text: str) -> dict:
    """Parse JSON from the model, tolerating code fences or surrounding text."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _clamp(value, default=0) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def normalize_result(result: dict) -> dict:
    """Make sure every expected key exists with a sane type."""
    breakdown_keys = [
        "formatting_and_structure",
        "keywords_and_skills",
        "work_experience_impact",
        "education_and_certifications",
        "readability_and_clarity",
    ]
    breakdown = result.get("score_breakdown") or {}
    return {
        "overall_score": _clamp(result.get("overall_score")),
        "score_breakdown": {k: _clamp(breakdown.get(k)) for k in breakdown_keys},
        "summary": str(result.get("summary", "")),
        "strengths": list(result.get("strengths") or []),
        "weaknesses": list(result.get("weaknesses") or []),
        "missing_keywords": list(result.get("missing_keywords") or []),
        "improvements": [i for i in (result.get("improvements") or []) if isinstance(i, dict)],
        "rewrite_examples": [r for r in (result.get("rewrite_examples") or []) if isinstance(r, dict)],
    }


def analyze_resume(resume_text: str, job_description: str, api_key: str, model: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    jd_block = ""
    if job_description.strip():
        jd_block = (
            "\nTarget job description (score keyword match against this):\n<job_description>\n"
            f"{job_description.strip()[:MAX_JD_CHARS]}\n</job_description>\n"
        )
    prompt = ANALYSIS_PROMPT.format(jd_block=jd_block, resume=resume_text[:MAX_RESUME_CHARS])
    message = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
    return normalize_result(parse_json_response(text))


# --------------------------------------------------------------------- helpers
def get_api_key() -> str:
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        key = ""
    return key or os.environ.get("ANTHROPIC_API_KEY", "")


def score_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Needs work"
    return "Poor"


def render_results(result: dict) -> None:
    score = result["overall_score"]
    st.divider()
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("ATS Score", f"{score}/100", score_label(score), delta_color="off")
        st.progress(score / 100)
    with col2:
        st.subheader("Summary")
        st.write(result["summary"] or "No summary returned.")

    st.subheader("Score breakdown")
    cols = st.columns(len(result["score_breakdown"]))
    for col, (key, val) in zip(cols, result["score_breakdown"].items()):
        col.metric(key.replace("_", " ").title(), f"{val}")

    left, right = st.columns(2)
    with left:
        st.subheader("Strengths")
        for s in result["strengths"] or ["None identified."]:
            st.markdown(f"- {s}")
    with right:
        st.subheader("Weaknesses")
        for w in result["weaknesses"] or ["None identified."]:
            st.markdown(f"- {w}")

    if result["missing_keywords"]:
        st.subheader("Missing keywords")
        st.write(", ".join(f"`{k}`" for k in result["missing_keywords"]))

    st.subheader("Recommended improvements")
    order = {"high": 0, "medium": 1, "low": 2}
    improvements = sorted(
        result["improvements"], key=lambda i: order.get(str(i.get("priority", "")).lower(), 3)
    )
    icons = {"high": "🔴", "medium": "🟠", "low": "🟢"}
    for imp in improvements:
        pr = str(imp.get("priority", "")).lower()
        title = f"{icons.get(pr, '⚪')} {imp.get('priority', '')} - {imp.get('section', 'General')}"
        with st.expander(title, expanded=(pr == "high")):
            st.markdown(f"**Issue:** {imp.get('issue', '')}")
            st.markdown(f"**Fix:** {imp.get('suggestion', '')}")

    if result["rewrite_examples"]:
        st.subheader("Rewrite examples")
        for ex in result["rewrite_examples"]:
            st.markdown(f"**Before:** {ex.get('original', '')}")
            st.markdown(f"**After:** {ex.get('improved', '')}")
            st.write("")

    st.download_button(
        "Download report (JSON)",
        data=json.dumps(result, indent=2),
        file_name="ats_report.json",
        mime="application/json",
    )


# ------------------------------------------------------------------------ UI
def main() -> None:
    st.set_page_config(page_title="AI Resume ATS Checker", page_icon="📄", layout="wide")
    st.title("📄 AI Resume ATS Checker")
    st.caption("Upload your resume and get an ATS score with specific improvements, powered by Claude.")

    with st.sidebar:
        st.header("Settings")
        api_key = get_api_key()
        if api_key:
            st.success("API key loaded from secrets/environment.")
        else:
            api_key = st.text_input("Anthropic API key", type="password", help="Get one at console.anthropic.com")
        model = st.text_input("Claude model", value=os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL))
        st.caption("Your resume is sent to the Anthropic API for analysis and is not stored by this app.")

    uploaded = st.file_uploader("Upload resume", type=["pdf", "docx", "txt"])
    job_description = st.text_area(
        "Job description (optional, improves keyword matching)", height=150,
        placeholder="Paste the job posting here...",
    )

    if st.button("Analyze resume", type="primary", disabled=uploaded is None):
        if not api_key:
            st.error("Please provide an Anthropic API key in the sidebar.")
            return
        try:
            text = extract_text(uploaded.name, uploaded.getvalue())
        except Exception as e:
            st.error(f"Could not read the file: {e}")
            return
        if len(text) < 100:
            st.error(
                "Very little text was extracted. If your resume is a scanned image, "
                "ATS systems cannot read it either - export a text-based PDF or DOCX."
            )
            return
        try:
            with st.spinner("Analyzing your resume with Claude..."):
                st.session_state["result"] = analyze_resume(text, job_description, api_key, model)
        except anthropic.AuthenticationError:
            st.error("Invalid API key.")
            return
        except anthropic.NotFoundError:
            st.error(f"Model '{model}' was not found. Check the model name in the sidebar.")
            return
        except anthropic.RateLimitError:
            st.error("Rate limit reached. Please wait a moment and try again.")
            return
        except anthropic.APIError as e:
            st.error(f"Claude API error: {e}")
            return
        except (json.JSONDecodeError, ValueError):
            st.error("The model returned an unreadable response. Please try again.")
            return

    if "result" in st.session_state:
        render_results(st.session_state["result"])


if __name__ == "__main__":
    main()
