"""Render validated resume content as a standalone professional HTML document."""

from __future__ import annotations

from html import escape

from models import (
    CandidateProfile,
    GeneratedResumeContent,
    GeneratedResumeRole,
    ResumeAchievement,
    ResumeCertification,
    ResumeEducation,
)
from utils.dates import format_month_year


RESUME_CSS = """
:root {
  color-scheme: light;
  --ink: #172033;
  --muted: #536176;
  --accent: #1d4e89;
  --rule: #d8dee8;
  --paper: #ffffff;
  --canvas: #eef1f5;
}

* { box-sizing: border-box; }

html { font-size: 10.5pt; }

body {
  margin: 0;
  color: var(--ink);
  background: var(--canvas);
  font-family: Inter, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.42;
}

.resume {
  width: min(8.5in, 100%);
  min-height: 11in;
  margin: 32px auto;
  padding: 0.62in 0.7in;
  background: var(--paper);
  box-shadow: 0 14px 40px rgba(23, 32, 51, 0.13);
}

.resume-header {
  padding-bottom: 18px;
  border-bottom: 3px solid var(--accent);
}

h1 {
  margin: 0;
  color: var(--ink);
  font-size: 26pt;
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.08;
}

.contact {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  margin: 9px 0 0;
  color: var(--muted);
  font-size: 9.5pt;
}

.contact a {
  color: inherit;
  text-decoration: none;
  overflow-wrap: anywhere;
}

section { margin-top: 20px; }

h2 {
  margin: 0 0 9px;
  padding-bottom: 4px;
  color: var(--accent);
  border-bottom: 1px solid var(--rule);
  font-size: 10.5pt;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

p { margin: 0; }

.summary { color: #273349; }
.summary-title { color: var(--ink); }

.skills-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.skills-list li {
  position: relative;
  padding-left: 10px;
}

.skills-list li::before {
  position: absolute;
  left: 0;
  color: var(--accent);
  content: "•";
}

.role { break-inside: avoid; }
.role + .role { margin-top: 15px; }

.role-heading {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: baseline;
}

h3 {
  margin: 0;
  font-size: 11.5pt;
  font-weight: 700;
}

.company {
  margin-top: 1px;
  color: var(--muted);
  font-weight: 600;
}

.company-location { font-weight: 400; }

.dates {
  color: var(--muted);
  font-size: 9.25pt;
  white-space: nowrap;
}

.details {
  margin: 7px 0 0;
  padding-left: 18px;
}

.details li { margin-top: 3px; }

.compact-list {
  margin: 0;
  padding-left: 18px;
}

.compact-list li + li { margin-top: 3px; }

.credential { break-inside: avoid; }
.credential + .credential { margin-top: 10px; }

.credential-meta {
  margin-top: 2px;
  color: var(--muted);
  font-size: 9.25pt;
}

.highlight-category { color: var(--accent); }

@page { size: Letter; margin: 0.5in 0.58in; }

@media print {
  html { font-size: 10pt; }
  body { background: #ffffff; }
  .resume {
    width: auto;
    min-height: auto;
    margin: 0;
    padding: 0;
    box-shadow: none;
  }
}

@media (max-width: 650px) {
  .resume { margin: 0; padding: 28px 24px; }
  .role-heading { grid-template-columns: 1fr; gap: 2px; }
  .dates { white-space: normal; }
}
""".strip()


class ResumeHTMLRenderer:
    def render(
        self,
        candidate: CandidateProfile,
        content: GeneratedResumeContent,
        *,
        target_title: str,
    ) -> str:
        resolved_title = target_title.strip()
        if not resolved_title:
            raise ValueError("target resume title must not be empty")
        sections = [
            self._section(
                "Professional Summary",
                '<p class="summary">'
                f'<strong class="summary-title">{escape(resolved_title)}</strong>'
                f" — {escape(content.professional_summary)}</p>",
            )
        ]
        if content.skills:
            skills = "".join(f"<li>{escape(skill)}</li>" for skill in content.skills)
            sections.append(
                self._section(
                    "Core Skills",
                    f'<ul class="skills-list">{skills}</ul>',
                )
            )
        if content.experience:
            roles = "".join(self._role(role) for role in content.experience)
            sections.append(self._section("Professional Experience", roles))
        if content.career_highlights:
            sections.append(
                self._section(
                    "Career Highlights",
                    self._highlights(content.career_highlights),
                )
            )
        if content.education:
            sections.append(
                self._section("Education", self._education(content.education))
            )
        if content.certifications:
            sections.append(
                self._section(
                    "Certifications",
                    self._certifications(content.certifications),
                )
            )

        contact = [
            f'<a href="mailto:{escape(candidate.email, quote=True)}">'
            f"{escape(candidate.email)}</a>"
        ]
        if candidate.phone:
            contact.append(f"<span>{escape(candidate.phone)}</span>")
        if candidate.location:
            contact.append(f"<span>{escape(candidate.location)}</span>")
        for url in (
            candidate.linkedin_url,
            candidate.github_url,
            candidate.website_url,
        ):
            if url:
                contact.append(
                    f'<a href="{escape(url, quote=True)}">'
                    f"{escape(self._display_url(url))}</a>"
                )
        return "\n".join(
            (
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8">',
                '  <meta name="viewport" content="width=device-width, initial-scale=1">',
                f"  <title>{escape(candidate.full_name)} — "
                f"{escape(resolved_title)} Resume</title>",
                "  <style>",
                RESUME_CSS,
                "  </style>",
                "</head>",
                "<body>",
                '  <main class="resume" data-document="tailored-resume">',
                '    <header class="resume-header">',
                f"      <h1>{escape(candidate.full_name)}</h1>",
                f'      <p class="contact">{"".join(contact)}</p>',
                "    </header>",
                *(f"    {section}" for section in sections),
                "  </main>",
                "</body>",
                "</html>",
                "",
            )
        )

    @staticmethod
    def _display_url(value: str) -> str:
        display = value
        for prefix in ("https://", "http://"):
            if display.casefold().startswith(prefix):
                display = display[len(prefix) :]
                break
        if display.casefold().startswith("www."):
            display = display[4:]
        return display.rstrip("/") or value

    @staticmethod
    def _section(title: str, body: str) -> str:
        return f'<section><h2>{escape(title)}</h2>{body}</section>'

    @staticmethod
    def _highlights(values: tuple[ResumeAchievement, ...]) -> str:
        items: list[str] = []
        for value in values:
            category = (
                f'<strong class="highlight-category">{escape(value.category)}:</strong> '
                if value.category
                else ""
            )
            items.append(f"<li>{category}{escape(value.description)}</li>")
        return f'<ul class="compact-list">{"".join(items)}</ul>'

    @staticmethod
    def _education(values: tuple[ResumeEducation, ...]) -> str:
        entries: list[str] = []
        for value in values:
            qualification = " in ".join(
                part for part in (value.degree, value.field) if part
            )
            heading = qualification or value.institution
            organization = (
                f'<p class="company">{escape(value.institution)}</p>'
                if qualification
                else ""
            )
            metadata = " • ".join(
                escape(part)
                for part in (value.location, value.status)
                if part
            )
            entries.append(
                '<article class="credential">'
                f"<h3>{escape(heading)}</h3>"
                f"{organization}"
                + (f'<p class="credential-meta">{metadata}</p>' if metadata else "")
                + "</article>"
            )
        return "".join(entries)

    @staticmethod
    def _certifications(values: tuple[ResumeCertification, ...]) -> str:
        entries: list[str] = []
        for value in values:
            metadata = " • ".join(
                escape(part)
                for part in (
                    (
                        f"Issued {format_month_year(value.issued)}"
                        if value.issued
                        else None
                    ),
                    value.status,
                )
                if part
            )
            entries.append(
                '<article class="credential">'
                f"<h3>{escape(value.name)}</h3>"
                + (f'<p class="credential-meta">{metadata}</p>' if metadata else "")
                + "</article>"
            )
        return "".join(entries)

    def _role(self, role: GeneratedResumeRole) -> str:
        dates = self._dates(role)
        responsibilities = (
            f'<ul class="details">'
            + "".join(
                f"<li>{escape(responsibility)}</li>"
                for responsibility in role.responsibilities
            )
            + "</ul>"
            if role.responsibilities
            else ""
        )
        location = (
            f' <span class="company-location">• {escape(role.location)}</span>'
            if role.location
            else ""
        )
        return (
            '<article class="role">'
            '<div class="role-heading">'
            "<div>"
            f"<h3>{escape(role.title)}</h3>"
            f'<p class="company">{escape(role.company)}{location}</p>'
            "</div>"
            + (f'<p class="dates">{escape(dates)}</p>' if dates else "")
            + "</div>"
            + responsibilities
            + "</article>"
        )

    @staticmethod
    def _dates(role: GeneratedResumeRole) -> str:
        if role.start_date and role.end_date:
            start = format_month_year(role.start_date)
            end = format_month_year(role.end_date, allow_present=True)
            return f"{start} – {end}"
        if role.start_date:
            return format_month_year(role.start_date)
        return format_month_year(role.end_date, allow_present=True)
