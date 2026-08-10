"""Render a concise cover letter as a print-ready one-page HTML document."""

from __future__ import annotations

from datetime import date
from html import escape

from models import CandidateProfile, GeneratedCoverLetterContent, JobPosting


COVER_LETTER_CSS = """
:root {
  color-scheme: light;
  --ink: #172033;
  --muted: #536176;
  --accent: #1d4e89;
  --paper: #ffffff;
  --canvas: #eef1f5;
}

* { box-sizing: border-box; }

html { font-size: 11pt; }

body {
  margin: 0;
  color: var(--ink);
  background: var(--canvas);
  font-family: Arial, "Helvetica Neue", sans-serif;
  line-height: 1.42;
}

.cover-letter {
  width: min(8.5in, 100%);
  min-height: 11in;
  margin: 32px auto;
  padding: 0.7in 0.78in;
  background: var(--paper);
  box-shadow: 0 14px 40px rgba(23, 32, 51, 0.13);
}

header {
  padding-bottom: 14px;
  border-bottom: 3px solid var(--accent);
}

h1 {
  margin: 0;
  font-size: 23pt;
  font-weight: 400;
  letter-spacing: -0.025em;
}

.contact {
  display: flex;
  flex-wrap: wrap;
  gap: 3px 15px;
  margin-top: 7px;
  color: var(--muted);
  font-size: 9.25pt;
}

.contact a { color: inherit; text-decoration: none; }

.date, .recipient { margin-top: 18px; }
.recipient { color: var(--muted); }
.salutation { margin-top: 22px; }
.body p { margin: 13px 0 0; }
.closing { margin-top: 20px; }

@page { size: Letter; margin: 0.58in 0.66in; }

@media print {
  body { background: #ffffff; }
  .cover-letter {
    width: auto;
    min-height: auto;
    margin: 0;
    padding: 0;
    box-shadow: none;
  }
}

@media (max-width: 650px) {
  .cover-letter { margin: 0; padding: 28px 24px; }
}
""".strip()


class CoverLetterHTMLRenderer:
    def render(
        self,
        candidate: CandidateProfile,
        content: GeneratedCoverLetterContent,
        *,
        job: JobPosting,
        generated_on: date | None = None,
    ) -> str:
        generated_date = generated_on or date.today()
        contact = [
            f'<a href="mailto:{escape(candidate.email, quote=True)}">'
            f"{escape(candidate.email)}</a>"
        ]
        for value in (candidate.phone, candidate.location):
            if value:
                contact.append(f"<span>{escape(value)}</span>")
        for url in (candidate.linkedin_url, candidate.website_url):
            if url:
                contact.append(
                    f'<a href="{escape(url, quote=True)}">{escape(url)}</a>'
                )
        paragraphs = "".join(
            f"<p>{escape(paragraph.text)}</p>" for paragraph in content.paragraphs
        )
        recipient_location = (
            f"<br>{escape(job.location)}" if job.location else ""
        )
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(candidate.full_name)} - {escape(job.company)} Cover Letter</title>
  <style>{COVER_LETTER_CSS}</style>
</head>
<body>
  <main class="cover-letter">
    <header>
      <h1>{escape(candidate.full_name)}</h1>
      <div class="contact">{"".join(contact)}</div>
    </header>
    <p class="date">{escape(_format_date(generated_date))}</p>
    <p class="recipient">{escape(job.company)}<br>{escape(job.title)}{recipient_location}</p>
    <p class="salutation">Dear {escape(job.company)} Hiring Team,</p>
    <section class="body">{paragraphs}</section>
    <p class="closing">Sincerely,<br>{escape(candidate.full_name)}</p>
  </main>
</body>
</html>
"""


def _format_date(value: date) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"
