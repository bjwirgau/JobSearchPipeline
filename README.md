# Job Agent

Job Agent is a review-first Python pipeline for finding relevant roles, evaluating fit, preparing truthful application materials, and tracking application state.

Phase 3 adds criteria-based job discovery and normalized search results to the resume-aware foundation. Application submission remains disabled and review-first.

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

## Phase 3: Job Search Agent

The search agent discovers jobs by criteria rather than iterating over a list of target companies. It builds one query per role and location, requests enabled discovery providers concurrently, normalizes their results into `JobPosting`, enforces hard filters, deduplicates across providers, stores jobs in SQLite, and hands them to parsing and matching.

Search criteria include:

- one or more roles and locations
- required skills or other requirement keywords
- remote-only work
- remote-job country eligibility
- location radius
- accepted employment types
- minimum annual salary
- maximum posting age
- excluded keywords

| Discovery source | Coverage | Configuration |
| --- | --- | --- |
| Adzuna | Cross-company job index for a configured country | App ID, app key, and country code |
| Remotive | Remote jobs across companies | Enable flag; no credentials |
| USAJOBS | U.S. federal jobs | API key and registration email |
| LinkedIn via Apify | LinkedIn public job listings across companies | Apify API token; a compatible Actor ID is provided by default |

Existing Greenhouse, Lever, Workday, and company career-page adapters remain available as optional supplemental sources. They are not required for discovery and are useful only when a direct company feed needs to be added to the broader results. LinkedIn discovery is delegated to an Apify Store Actor; this project does not automate LinkedIn login or manage browser sessions.

Normalized jobs consistently include source identity, title, company, URL, location, description, detected skills, employment type, salary range, currency, remote status, and posting date. Missing source fields remain `None` or empty rather than being invented.

### Enable and Configure Job Searching

#### 1. Install the HTTP search dependencies

Discovery and supplemental sources use Requests; HTML career pages also use Beautiful Soup:

```bash
python3 -m pip install -e '.[search]'
```

#### 2. Create your local configuration

Copy the environment template from the project root. `.env` is ignored by Git.

```bash
cp .env.example .env
```

#### 3. Configure one or more sources

Defining an adapter in the code does not enable it. The source factory creates an adapter only when all of its required settings are present.

| CLI source name | Source type | Required configuration |
| --- | --- | --- |
| `adzuna` | Global discovery | `JOB_AGENT_ADZUNA_APP_ID` and `JOB_AGENT_ADZUNA_APP_KEY` |
| `remotive` | Global remote discovery | `JOB_AGENT_REMOTIVE_ENABLED=true` |
| `usajobs` | U.S. federal discovery | `JOB_AGENT_USAJOBS_EMAIL` and `JOB_AGENT_USAJOBS_API_KEY` |
| `greenhouse` | Supplemental company feed | At least one `Company=board_token` in `JOB_AGENT_GREENHOUSE_BOARDS` |
| `lever` | Supplemental company feed | At least one `Company=site_name` in `JOB_AGENT_LEVER_SITES` |
| `workday` | Supplemental company feed | At least one `Company=public_cxs_url` in `JOB_AGENT_WORKDAY_TENANTS` |
| `career_page` | Supplemental company page | At least one `Company=public_url` in `JOB_AGENT_CAREER_PAGES` |
| `linkedin` | Global discovery through Apify | `JOB_AGENT_APIFY_API_TOKEN`; the default compatible Actor ID can be overridden |

##### Adzuna

Register through the [Adzuna developer portal](https://developer.adzuna.com/) and copy the application ID and key into `.env`:

```env
JOB_AGENT_ADZUNA_APP_ID=your-app-id
JOB_AGENT_ADZUNA_APP_KEY=your-app-key
JOB_AGENT_ADZUNA_COUNTRY=us
```

Both credentials are required. `JOB_AGENT_ADZUNA_COUNTRY` defaults to `us` and selects the country index searched by Adzuna. Use a supported two-letter code such as `us`, `ca`, or `gb`.

##### Remotive

Remotive does not require credentials. Enable its public remote-jobs feed with:

```env
JOB_AGENT_REMOTIVE_ENABLED=true
```

The [Remotive public API](https://remotive.com/remote-jobs/api) is delayed by 24 hours. Preserve the normalized Remotive URL and source attribution, and avoid scheduling more than a few feed requests per day.

##### USAJOBS

Request a key from the [USAJOBS developer portal](https://developer.usajobs.gov/) and configure the key together with the email address used to request it:

```env
JOB_AGENT_USAJOBS_EMAIL=you@example.com
JOB_AGENT_USAJOBS_API_KEY=your-api-key
```

Both values are required. This provider searches U.S. federal job announcements only.

##### Greenhouse

Configure a company display name and its board token:

```env
JOB_AGENT_GREENHOUSE_BOARDS=Example Company=example
```

The board token is the path segment in `https://boards.greenhouse.io/{board_token}`. For multiple boards, separate entries with semicolons:

```env
JOB_AGENT_GREENHOUSE_BOARDS=Company One=companyone;Company Two=companytwo
```

##### Lever

Configure a company display name and its Lever site name:

```env
JOB_AGENT_LEVER_SITES=Example Company=example
```

The site name is the path segment in `https://jobs.lever.co/{site_name}`. Multiple `Company=site_name` entries use semicolon separators.

##### Workday

Configure the company display name and complete public CXS base URL:

```env
JOB_AGENT_WORKDAY_TENANTS=Example Company=https://example.wd1.myworkdayjobs.com/wday/cxs/example/Careers
```

The required value is the tenant-specific public CXS endpoint, not the visible careers-page URL. Workday response details can vary by tenant, so test each endpoint before scheduling it.

##### Company career pages

Configure a company display name and a public page containing Schema.org `JobPosting` JSON-LD:

```env
JOB_AGENT_CAREER_PAGES=Example Company=https://careers.example.com/jobs
```

Static JSON-LD pages need only the search dependencies. JavaScript-rendered pages may also require the optional browser fallback described below.

##### LinkedIn

Create an [Apify account](https://console.apify.com/) and copy the API token from the Console integration settings. Then configure:

```env
JOB_AGENT_APIFY_API_TOKEN=your-apify-api-token
JOB_AGENT_APIFY_LINKEDIN_ACTOR_ID=automation-lab/linkedin-jobs-scraper
JOB_AGENT_APIFY_TIMEOUT_SECONDS=120
```

The token alone enables the `linkedin` source; the Actor ID and timeout already have the defaults shown above. The integration uses the input and output contract of [`automation-lab/linkedin-jobs-scraper`](https://apify.com/automation-lab/linkedin-jobs-scraper): role and requirement terms become `searchQuery`, location or remote country becomes `location`, and supported employment, remote-only, result-count, and posting-age filters are sent to the Actor. Only override the Actor ID with an Actor that accepts the same fields and returns a compatible dataset.

The LinkedIn Actor workplace codes are represented by `LinkedInWorkplaceType`: `ON_SITE` (`1`), `REMOTE` (`2`), and `HYBRID` (`3`). This keeps raw numeric codes out of the source logic and makes future workplace filtering explicit.

The request uses Apify's synchronous Actor endpoint and sends the token in the `Authorization` header. `--limit` is sent as both the Actor's `maxJobs` limit and the API's `maxItems` request limit, capped at the Actor's 1,000-job maximum. Actor runs can consume Apify credits, so review the Actor's current pricing before enabling this source. You are responsible for using retrieved data in accordance with applicable laws and platform terms.

#### 4. Enable the search agent

After configuring at least one source, change the search flag in `.env`:

```env
JOB_AGENT_SEARCH_ENABLED=true
JOB_AGENT_REMOTE_COUNTRY=us
```

`JOB_AGENT_REMOTE_COUNTRY` is optional and uses a two-letter country code. When
set, remote listings must explicitly allow that country or be available
worldwide. Listings restricted to another country—or with no country eligibility
information—are excluded. The CLI can override it with `--remote-country`.

Recommended HTTP settings are included in `.env.example`:

```env
JOB_AGENT_BROWSER_FALLBACK=none
JOB_AGENT_HTTP_TIMEOUT_SECONDS=20
JOB_AGENT_HTTP_USER_AGENT=JobAgent/0.3 (+your-contact-information)
```

#### 5. Optionally enable a browser fallback

Dynamic career pages can fall back to Playwright or Selenium only when the initial HTTP response contains no job JSON-LD:

```bash
python3 -m pip install -e '.[browser]'
python3 -m playwright install chromium
```

Then select the browser in `.env`:

```env
JOB_AGENT_BROWSER_FALLBACK=playwright
```

Playwright is preferred. Use `selenium` only for a site that cannot be handled reliably with HTTP or Playwright. Browser fallback never performs login or CAPTCHA handling.

#### 6. Run a search

Run every enabled provider using the desired titles, locations, and resume knowledge from `data/candidate_profile.json`:

```bash
python3 app.py --search
```

Preview the exact Actor input without requiring an Apify token or sending any request:

```bash
python3 app.py --search \
  --source linkedin \
  --dry-run \
  --title "AI Engineer" \
  --remote \
  --remote-country us \
  --limit 25
```

Dry-run output includes the configured Actor ID and each JSON query that a live LinkedIn search would submit. It exits before source selection, network access, and job storage. The flag supports only the `linkedin` source; when `--source` is omitted, LinkedIn is implied for the preview.

Override the profile defaults and add explicit hard filters with CLI options:

```bash
python3 app.py --search \
  --title "Senior Software Engineer" \
  --requirement PHP \
  --requirement AWS \
  --location "Denver, CO" \
  --radius 50 \
  --remote-country us \
  --employment-type full-time \
  --minimum-salary 140000 \
  --max-age-days 14 \
  --exclude internship \
  --source adzuna \
  --limit 25
```

Repeat `--title`, `--requirement`, `--location`, `--employment-type`, or `--exclude` to provide multiple values. Add `--remote` to require an explicitly remote job. Required keywords are pushed to providers that support them and are checked again after normalization.

When remote-only search is active, profile and CLI locations (and their radius) are omitted from source queries. If `JOB_AGENT_REMOTE_COUNTRY` or `--remote-country` is configured, providers may still receive that country as the remote eligibility scope; otherwise LinkedIn's Apify request omits `location` entirely.

Discovery source names are `adzuna`, `remotive`, `usajobs`, and `linkedin`. Supplemental names are `greenhouse`, `lever`, `workday`, and `career_page`. Omitting `--source` searches every enabled source.

Results are normalized, filtered, deduplicated, scored, printed to the terminal, and stored in the configured SQLite database. If the application reports that no source supports the search, confirm that the search flag is enabled and at least one source is configured.

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

The local models, storage, and tests have no third-party runtime dependencies. Install the project in editable mode if desired:

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

The suite covers resume knowledge, parsing, matching, SQLite persistence, the search safety flag, and fixture-based normalization for every Phase 3 source without making network requests.

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

The next phase can add source health telemetry, pagination checkpoints, evidence links, match persistence, and a review interface. Live application automation should remain out of scope until validation, approval auditing, and platform-specific dry runs are reliable.
