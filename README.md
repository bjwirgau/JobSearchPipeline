# Job Agent

Job Agent is a modular Python project for automating and supporting the job-search workflow. Its agents are organized around distinct responsibilities: finding opportunities, parsing job descriptions, evaluating fit, tailoring application materials, writing cover letters, and assisting with applications.

## Project Status

This repository currently contains the initial project structure. Agent behavior, integrations, data models, prompts, and evaluation workflows are ready to be implemented.

## Project Structure

```text
./
├── agents/
│   ├── search_agent.py        # Finds relevant job opportunities
│   ├── parser_agent.py        # Extracts structured data from job postings
│   ├── matching_agent.py      # Scores candidate-to-job compatibility
│   ├── tailoring_agent.py     # Tailors resumes and application materials
│   ├── cover_letter_agent.py  # Produces role-specific cover letters
│   └── apply_agent.py         # Coordinates the application workflow
├── models/                    # Domain models and schemas
├── prompts/                   # Reusable agent prompt templates
├── evaluations/               # Agent tests, benchmarks, and quality checks
├── database/                  # Persistence code, schemas, and migrations
├── playwright/                # Browser automation workflows
├── api/                       # API routes and service interfaces
└── app.py                     # Application entry point
```

## Intended Workflow

1. The search agent discovers job postings that match the candidate's criteria.
2. The parser agent converts each posting into structured data.
3. The matching agent evaluates the candidate's fit for the role.
4. The tailoring agent adapts the candidate's resume and supporting materials.
5. The cover-letter agent drafts a targeted cover letter when needed.
6. The apply agent prepares or coordinates the final application process.

## Getting Started

### Prerequisites

- Python 3.10 or newer
- A virtual environment is recommended

### Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install project dependencies after a dependency file is added:

```bash
pip install -r requirements.txt
```

Run the application entry point with:

```bash
python app.py
```

## Development Guidelines

- Keep each agent focused on one responsibility.
- Put shared data structures in `models/`.
- Store prompt text separately from agent logic in `prompts/`.
- Add evaluation cases alongside new agent capabilities.
- Keep browser automation isolated in `playwright/`.
- Require user review before any application is submitted automatically.

## License

No license has been selected yet.
