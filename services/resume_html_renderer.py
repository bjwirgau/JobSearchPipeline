"""Render validated resume content as a standalone professional HTML document."""

from __future__ import annotations

from html import escape

from models import CandidateProfile, GeneratedResumeContent, GeneratedResumeRole


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
    ) -> str:
        sections = [
            self._section(
                "Professional Summary",
                f'<p class="summary">{escape(content.professional_summary)}</p>',
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
                    self._list(content.career_highlights),
                )
            )
        if content.education:
            sections.append(
                self._section("Education", self._list(content.education))
            )
        if content.certifications:
            sections.append(
                self._section(
                    "Certifications",
                    self._list(content.certifications),
                )
            )

        contact = [
            f'<a href="mailto:{escape(candidate.email, quote=True)}">'
            f"{escape(candidate.email)}</a>"
        ]
        if candidate.location:
            contact.append(f"<span>{escape(candidate.location)}</span>")
        return "\n".join(
            (
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8">',
                '  <meta name="viewport" content="width=device-width, initial-scale=1">',
                f"  <title>{escape(candidate.full_name)} — Resume</title>",
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
    def _section(title: str, body: str) -> str:
        return f'<section><h2>{escape(title)}</h2>{body}</section>'

    @staticmethod
    def _list(values: tuple[str, ...]) -> str:
        items = "".join(f"<li>{escape(value)}</li>" for value in values)
        return f'<ul class="compact-list">{items}</ul>'

    def _role(self, role: GeneratedResumeRole) -> str:
        dates = self._dates(role)
        achievements = (
            f'<ul class="details">'
            + "".join(
                f"<li>{escape(achievement)}</li>"
                for achievement in role.achievements
            )
            + "</ul>"
            if role.achievements
            else ""
        )
        return (
            '<article class="role">'
            '<div class="role-heading">'
            "<div>"
            f"<h3>{escape(role.title)}</h3>"
            f'<p class="company">{escape(role.company)}</p>'
            "</div>"
            + (f'<p class="dates">{escape(dates)}</p>' if dates else "")
            + "</div>"
            + achievements
            + "</article>"
        )

    @staticmethod
    def _dates(role: GeneratedResumeRole) -> str:
        if role.start_date and role.end_date:
            return f"{role.start_date} – {role.end_date}"
        return role.start_date or role.end_date or ""
