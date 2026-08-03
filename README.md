# Job Agent

Job Agent is a review-first Python pipeline for finding relevant roles, evaluating fit, preparing truthful application materials, and tracking application state.

Phase 2 adds a structured resume knowledge base to the Phase 1 application foundation. The project still does **not** connect to live job boards, run a browser, or submit applications.

## Pipeline

```text
Search → Normalize → Parse → Score → Review → Tailor → Apply → Track
```

- **Search:** build queries, select source adapters, combine results, and apply inexpensive filters.
- **Normalize:** source adapters convert vendor responses into shared `JobPosting` models.
- **Parse:** extract requirements, responsibilities, and recognized skills.
- **Score:** produce a transparent candidate/job score and qualification gaps.
- **Review:** require a person to select and approve an opportunity.
- **Tailor:** create local resume guidance and a cover-letter draft using known facts.
- **Apply:** validate the application and hand it to a configured submission gateway.
- **Track:** persist jobs, applications, statuses, and workflow events.

## Phase 1 Features

- Dependency-free configuration and core runtime on Python 3.10+
- Validated dataclass models for candidates, jobs, matches, applications, and workflows
- SQLite schema with candidate, job, application, and workflow tables
- Repository classes that isolate persistence from agents
- Source-independent asynchronous search orchestration
- In-memory job source for local development and tests
- Deterministic job parser and explainable baseline match scorer
- Explicit human-review and approval gates before tailoring or submission
- Local document-draft storage
- Browser-adapter and optional API boundaries with no live side effects
- Offline evaluator and prompt scaffolding

## Phase 2: Resume Knowledge Base

The resume knowledge base turns resume facts into validated JSON that matching code can query directly:

```json
{
  "candidate_id": "replace-me",
  "skills": ["Magento", "PHP", "Laravel", "React", "MySQL", "AWS"],
  "years": {
    "PHP": 10,
    "Magento": 10,
    "React": 4,
    "Java": 2
  },
  "industries": ["Ecommerce", "Retail"]
}
```

`ResumeKnowledgeBase` validates skill names and experience ranges while retaining optional roles, achievements, certifications, and education as factual evidence. A skill present only in `years` remains available to matching through the combined `all_skills` view.

The knowledge layer includes:

- `data/candidate_profile.json` as the single editable source for identity, preferences, and resume knowledge
- JSON loading, validation, and atomic saving through `ResumeKnowledgeService`
- SQLite persistence through `ResumeKnowledgeRepository`
- Schema version 2 and an incremental resume-knowledge migration
- Skill-specific years and industry alignment in match results
- A cautious extraction prompt for a future resume-ingestion provider

`CandidateProfile` and `ResumeKnowledgeBase` read separate validated views from this one JSON file. When resume knowledge is saved, identity and job-preference fields are preserved.

Phase 2 does not extract a PDF automatically. Review and correct the structured JSON before using it for matching; this prevents unsupported experience claims from becoming part of an application.

Live search and application submission are disabled by default:

```env
JOB_AGENT_SEARCH_ENABLED=false
JOB_AGENT_APPLICATION_SUBMISSION_ENABLED=false
```

Enabling a flag alone does not configure an external source, browser runtime, or application gateway.

## Project Structure

```text
.
├── app.py                         # Composition root
├── config.py                      # Environment settings
├── pyproject.toml                 # Packaging and optional dependencies
├── .env.example                   # Safe configuration template
├── agents/                        # Single-responsibility pipeline agents
├── models/                        # Shared domain and resume-knowledge models
├── services/                      # External capability boundaries
├── workflows/                     # Pipeline orchestration
├── repositories/                  # Persistence interfaces and SQLite implementations
├── database/                      # Connection, schema, and migration files
├── prompts/                       # Reusable LLM prompt templates
├── browser/                       # Guarded form planning and platform adapters
├── evaluations/                   # Offline quality metrics and datasets
├── api/                           # Optional HTTP API
├── utils/                         # Date, text, hashing, and logging helpers
├── tests/                         # Unit and integration tests
└── data/                          # Local profile, resume knowledge, fixtures, and documents
```

## Getting Started

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

The Phase 2 core has no third-party runtime dependencies. Install the project in editable mode if desired:

```bash
python3 -m pip install -e .
```

Create local settings and edit the sample candidate profile:

```bash
cp .env.example .env
```

- Configuration: `.env`
- Unified candidate profile and resume knowledge: `data/candidate_profile.json`
- Sample job: `data/sample_jobs/sample_job.json`

Initialize the SQLite database and application container:

```bash
python3 app.py
```

By default this creates `data/job_agent.sqlite3`, which is ignored by Git.

## Tests

Run the standard-library test suite:

```bash
python3 tests/run_tests.py
```

The terminal displays a compact progress bar. Detailed per-test output is written to `test-results/unit-tests.log`; the entire `test-results/` directory is ignored by Git. Set `JOB_AGENT_TEST_REPORT` to use a different report path.

To run Python's built-in test discovery directly with verbose console output, use:

```bash
python3 -m unittest discover -s ./tests -p 'test_*.py' -v
```

The suite covers resume knowledge, parsing, matching, SQLite persistence, the search safety flag, and a network-free in-memory search.

## Optional API

The API uses a lazy FastAPI import so the core stays dependency-free. Install its dependencies with:

```bash
python3 -m pip install -e '.[api]'
```

`api.main.create_app(...)` accepts repository dependencies explicitly. An ASGI server entry point can be added when the API becomes part of the active runtime.

## Design Rules

- Agents own one pipeline decision; workflows own sequencing.
- Services hide external providers and browser systems.
- Repositories own persistence and SQL.
- Source adapters must return normalized shared models.
- Generated claims must remain grounded in the candidate profile and reviewed resume knowledge.
- Every application requires explicit user approval.
- Search, browser automation, and submission stay off until their dependencies are configured and tested.

## Next Phase

The next phase can add evidence links from each structured resume fact back to a role or source passage, plus one concrete job source, match persistence, and a review interface. Live application automation should remain out of scope until validation, approval auditing, and platform-specific dry runs are reliable.
