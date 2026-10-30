# AI Resume ATS Checker

A Streamlit app that scores a resume for ATS (Applicant Tracking System) compatibility and gives specific, prioritized improvements, powered by Claude.

## Features

- Upload a resume as PDF, DOCX or TXT
- Optional job description for keyword-match scoring
- Overall ATS score (0-100) plus a 5-part breakdown
- Strengths, weaknesses and missing keywords
- Prioritized improvements (High / Medium / Low) and before/after rewrite examples
- Download the report as JSON

## Project structure

```
.
├── app.py             # Streamlit app
├── requirements.txt   # Python dependencies
└── README.md
```

## Run locally

1. Install Python 3.10+.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Get an API key from https://console.anthropic.com and set it:
   ```bash
   # macOS / Linux
   export ANTHROPIC_API_KEY="your-key"
   # Windows PowerShell
   $env:ANTHROPIC_API_KEY="your-key"
   ```
   (Or skip this and paste the key into the app sidebar.)
4. Start the app:
   ```bash
   streamlit run app.py
   ```

## Configuration

| Setting | Where | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | env var or Streamlit secrets | none (or enter in sidebar) |
| `CLAUDE_MODEL` | env var, or the sidebar field | `claude-sonnet-5-5` |

## Deploy on Streamlit Community Cloud

1. Push this project to a GitHub repository (`app.py` and `requirements.txt` in the repo root).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, choose your repo, branch `main`, and main file `app.py`.
4. Open **Advanced settings → Secrets** and add:
   ```toml
   ANTHROPIC_API_KEY = "your-key"
   ```
5. Click **Deploy**.

**Never commit your API key to GitHub.** Use Streamlit secrets or environment variables only.

## Notes and limitations

- Scanned/image-only resumes cannot be read; export a text-based PDF or DOCX.
- The ATS score is an AI estimate based on best practices, not the output of a specific commercial ATS.
- Resume text is sent to the Anthropic API for analysis; the app itself does not store it.
