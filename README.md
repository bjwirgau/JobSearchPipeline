# Job Agent

Job Agent is a review-first Python pipeline for finding relevant roles, evaluating fit, preparing truthful application materials, and tracking application state.

Phase 3 adds criteria-based job discovery and normalized search results to the
resume-aware foundation. Selenium can prepare a generated-resume application
for review, but application submission remains disabled.

## Pipeline

```text
Search → Normalize → Parse → Score → Review → Tailor → Apply → Track
```

- **Search:** build queries, select source adapters, combine results, and apply inexpensive filters.
- **Normalize:** source adapters convert vendor responses into shared `JobPosting` models.
- **Parse:** extract requirements, responsibilities, and recognized skills.
- **Score:** use structured, evidence-grounded LLM output to assess fit and qualification gaps.
- **Review:** require a person to select and approve an opportunity.
- **Tailor:** create local resume guidance and a cover-letter draft using known facts.
- **Apply:** populate an application for human review while keeping submission disabled.
- **Track:** persist scored job prospects and workflow events.

## Phase 1 Features

- Python 3.10+ configuration and core runtime
- Validated dataclass models for candidates, jobs, matches, applications, and workflows
- MySQL 8 schema with job-prospect, resume-knowledge, and workflow tables
- Focused relational job-prospect columns for review and reporting
- Repository classes that isolate persistence from agents
- Source-independent asynchronous search orchestration
- In-memory job source for local development and tests
- Deterministic job parser and structured, evidence-grounded LLM match scorer
- Explicit human-review and approval gates before tailoring or submission
- Local document-draft storage
- Browser-adapter and optional API boundaries with no live side effects
- Offline evaluator and prompt scaffolding

## Phase 2: Resume Knowledge Base

The resume knowledge base turns resume facts into validated JSON that matching code can query directly:

```json
{
  "candidate_id": "replace-me",
  "full_name": "Example Candidate",
  "email": "candidate@example.com",
  "phone": "",
  "linkedin_url": "https://www.linkedin.com/in/example-candidate",
  "github_url": "https://github.com/example-candidate",
  "website_url": "https://example.dev",
  "location": "Denver, CO",
  "country": "United States",
  "skills": ["Magento", "PHP", "Laravel", "React", "MySQL", "AWS"],
  "additional_keywords": ["Technical Leadership", "Cross-functional Collaboration"],
  "application_answers": {
    "Will you require employment sponsorship?": "No"
  },
  "years": {
    "PHP": 10,
    "Magento": 10,
    "React": 4,
    "Java": 2
  },
  "industries": ["Ecommerce", "Retail"],
  "roles": [
    {
      "company": "Example Company",
      "title": "Senior Software Engineer",
      "location": "Remote, US",
      "start_date": "2022-03",
      "end_date": "Present",
      "responsibilities": ["Built and supported scalable applications."]
    }
  ],
  "achievements": [
    {"category": "Performance", "description": "Improved application performance."}
  ],
  "certifications": [
    {"name": "Example Certification", "issued": "2025-01", "status": "Current"}
  ],
  "education": [
    {
      "institution": "Example University",
      "location": "Denver, CO",
      "degree": "Bachelor of Science",
      "field": "Computer Engineering",
      "status": null
    }
  ]
}
```

`ResumeKnowledgeBase` validates skill names and experience ranges while preserving
structured roles, achievements, certifications, and education as factual evidence.
Older profiles containing strings for achievements, certifications, or education
remain supported. A skill present only in `years` remains available to matching
through the combined `all_skills` view.

`additional_keywords` provides optional, candidate-approved terms for resume
generation. The model may include a configured term when it is relevant to the target
job, but it is instructed not to force every term into the resume. These keywords do
not change job-search or matching criteria.

`application_answers` contains candidate-approved facts for questions that must
not be guessed, such as work authorization, sponsorship, availability,
compensation expectations, voluntary demographic responses, consent, or a legal
signature. Use the application question as the key and the intended form answer
as the value. Leave the mapping empty until every configured answer has been
reviewed for accuracy.

The knowledge layer includes:

- `data/candidate_profile.json` as the single editable source for identity, preferences, and resume knowledge
- JSON loading, validation, and atomic saving through `ResumeKnowledgeService`
- MySQL persistence through `ResumeKnowledgeRepository`
- Schema version 2 and an incremental resume-knowledge migration
- Skill-specific years and industry alignment in match results
- A cautious extraction prompt for a future resume-ingestion provider

`CandidateProfile` and `ResumeKnowledgeBase` read separate validated views from this one JSON file. When resume knowledge is saved, identity and job-preference fields are preserved.

Set `phone`, `linkedin_url`, `github_url`, and `website_url` in
`data/candidate_profile.json` to include them in generated resume contact details.
Set `country` to select country controls on application forms. An empty value omits
that field. Candidate name, email, phone, location, and profile links are inserted
locally and are not sent to the resume-generation model.

Phase 2 does not extract a PDF automatically. Review and correct the structured JSON before using it for matching; this prevents unsupported experience claims from becoming part of an application.

## Phase 3: Job Search Agent

The search agent discovers jobs by criteria rather than iterating over a list of target companies. It builds one query per role and location, requests enabled discovery providers concurrently, normalizes their results into `JobPosting`, enforces hard filters, deduplicates across providers, parses them, and stores job prospects in MySQL. LLM matching runs independently against the stored queue.

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
| LinkedIn via Apify | LinkedIn public job listings across companies | Enable flag and Apify API token; a compatible Actor ID is provided by default |

Greenhouse searches use the board tokens accumulated by the company crawler in
`company_prospects`. Manually configured Greenhouse boards, Lever, Workday, and
company career-page adapters remain available as supplemental sources. LinkedIn
discovery is delegated to an Apify Store Actor; this project does not automate
LinkedIn login or manage browser sessions.

Normalized jobs consistently include source identity, title, company, URL, location, description, detected skills, employment type, salary range, currency, remote status, and posting date. Missing source fields remain `None` or empty rather than being invented.

MySQL stores the review-oriented projection in `job_prospects` with `job_id`,
`match`, `title`, `company`, `location`, `salary`, `source`, `url`, `posted_at`,
`job_data`, `resume_generation_checked`, `resume_generation_candidate`,
`resume_generation_model`, `resume_file_name`, `cover_letter_file_name`,
`created_at`, and `updated_at`
columns. `job_data`
retains the complete
normalized posting needed by the asynchronous matcher. The database assigns both UTC timestamps when a
prospect is first stored, preserves `created_at`, and refreshes `updated_at`
when the prospect, match score, or resume-generation state changes. The match
is nullable during search and updated to a score between `0` and `1` after the
scoring stage.
Candidate identity and preferences remain in `data/candidate_profile.json`;
application records are not persisted in the current schema.

Greenhouse company discovery is stored separately in `company_prospects` with
`company_id`, `company_name`, `board_token`, `company_url`,
`last_job_search_at`, `created_at`, and `updated_at`. The company URL is the
canonical public Greenhouse board URL. The search timestamp rotates limited
board batches across runs.

Page-level crawl history is stored in `crawl_pages`. Each row records the page
URL, source, page type, last outcome, last and next crawl times, and the most
recent error. This includes failed board URLs that never become company
prospects.

### LLM matching

The minute-based matching worker selects stored prospects whose match is null
and sends them through the Gemini Developer API. The model receives job evidence plus the candidate's summary,
preferences, and structured resume knowledge. The prompt deliberately omits the
candidate's name, email address, resume path, and source job payload. Requests
use schema-constrained JSON output, and the application validates every score
before persisting it.

The response contains a holistic score, separate skills/title/location/
experience/industry scores, matched qualifications, missing qualifications, and
an evidence-grounded rationale. The score is model-generated rather than a
fixed weighted formula. Review remains mandatory because model judgments can be
inconsistent and should not be treated as proof of eligibility.

Configure matching in `.env`:

```env
GEMINI_API_KEY=your-api-key
JOB_AGENT_GEMINI_MODEL=gemini-3.5-flash-lite
JOB_AGENT_GEMINI_TIMEOUT_SECONDS=60
JOB_AGENT_MATCHING_CONCURRENCY=1
JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN=15
JOB_AGENT_MATCHING_PROMPT=prompts/score_match.txt
JOB_AGENT_RESUME_CANDIDATE_THRESHOLD=0.85
JOB_AGENT_RESUME_GENERATION_MODEL=gpt-5.4
```

`gemini-3.5-flash-lite` is the default because it is optimized for high-volume
structured JSON and document extraction. The model remains configurable without
a code change. One API request is made for every distinct job being scored, so
result count directly affects quota usage and latency. Every matcher run is
hard-capped at 15 Gemini requests, and request starts are spaced four seconds
apart to enforce 15 RPM. The setting can be lowered but values above 15 are
rejected. Jobs beyond the batch remain stored with
`resume_generation_checked = FALSE` and are picked up by a later matcher run.
Search does not require a Gemini key; only
`--match-prospects` does. Create a key in
[Google AI Studio](https://aistudio.google.com/apikey), and see Google's
[structured output documentation](https://ai.google.dev/gemini-api/docs/structured-output).

The unpaid Gemini API tier may use submitted content to improve Google products
and may involve human review. Do not send sensitive or personally identifying
resume data through the unpaid tier; review the
[Gemini API terms](https://ai.google.dev/gemini-api/terms) before enabling the
scheduled search.

After Gemini matching, a score strictly greater than
`JOB_AGENT_RESUME_CANDIDATE_THRESHOLD` marks the stored job as a resume
generation candidate. The intended generation model is stored alongside the
job and defaults to the official `gpt-5.4` model ID. Schema migration 9 also
backfills existing matches above 85%. Matching only creates the durable queue;
it does not send candidate data to OpenAI. Resume and cover-letter packages can
be generated explicitly for one marked job or by the optional scheduled queue
worker. GPT-5.4 supports
text output through the
Responses API; see the
[official model documentation](https://developers.openai.com/api/docs/models/gpt-5.4).

### Generate resumes and cover letters

Configure the OpenAI API key and optional generation limits in `.env`:

```env
OPENAI_API_KEY=your-api-key
JOB_AGENT_RESUME_GENERATION_MODEL=gpt-5.4
JOB_AGENT_RESUME_GENERATION_TIMEOUT_SECONDS=120
JOB_AGENT_RESUME_GENERATION_MAX_OUTPUT_TOKENS=6000
JOB_AGENT_RESUME_GENERATION_PROMPT=prompts/generate_resume.txt
JOB_AGENT_COVER_LETTER_GENERATION_PROMPT=prompts/generate_cover_letter.txt
JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT=1
JOB_AGENT_RESUME_GENERATION_BATCH_FORMAT=docx
```

Keep the key in `.env`, which is ignored by Git, or inject it from the deployment
environment. Do not commit it. API keys are created from the
[OpenAI API key page](https://platform.openai.com/api-keys).

Find a job that has completed eligibility review and is marked as a generation
candidate:

```sql
SELECT job_id, `match`, title, company, resume_generation_model,
       resume_file_name, cover_letter_file_name
FROM job_prospects
WHERE resume_generation_checked = TRUE
  AND resume_generation_candidate = TRUE
  AND (resume_file_name IS NULL OR cover_letter_file_name IS NULL)
ORDER BY `match` DESC;
```

Generate exactly one resume and cover letter by the full `job_id`:

```bash
python3 app.py --generate-resume JOB_ID
```

HTML remains the default. Use `--resume-format` to generate an editable Microsoft
Word documents or both supported formats:

```bash
python3 app.py --generate-resume JOB_ID --resume-format docx
python3 app.py --generate-resume JOB_ID --resume-format both
```

The command rejects unknown jobs, unchecked jobs, and jobs that were checked but
did not pass the configured threshold. It uses the model stored on that job,
loads the normalized posting plus the reviewed candidate knowledge, and makes
one OpenAI Responses API request for the resume and one for the cover letter,
with response storage disabled for both. GPT returns schema-constrained content
rather than document markup. The application
validates selected responsibilities and structured factual records against the
reviewed candidate knowledge and renders a standalone, ATS-friendly HTML resume,
an editable DOCX resume, or both. The DOCX is created natively with professional
Word styles rather than converted from browser CSS. Candidate contact details are
added locally and are not included in the model request. The prompt also excludes
the raw scraper payload and local source-resume path.

The cover-letter prompt treats all supplied JSON as untrusted evidence and
requires every generated paragraph to cite stable evidence IDs. The application
rejects unknown IDs before writing the file. It instructs the model to connect
only supported experience to the company's stated priorities, prohibits invented
skills, achievements, motivations, hiring-manager details, and company
relationships, and limits the body to three or four paragraphs and 350 words.
Contact details, date, company address block, salutation, closing, and signature
are inserted locally. The fixed Letter-size HTML and DOCX layouts are designed to
keep the validated content to one page. Always review both documents before use.

The resume-generation LLM inspects the narrative summary inside the normalized job
description and returns `target_title` only when that summary explicitly declares a
title. The application verifies that the exact returned phrase occurs in the
description before using it. Otherwise, it falls back to the original normalized job
title, which itself falls back to `job_prospects.title` when missing. Candidate-profile
titles are not used. Resume role and certification dates must include month precision
using `YYYY-MM` or `Month YYYY`; both renderers display them consistently as
`Month YYYY`. `Present` is accepted for a role's end date. Bold lettering is reserved
for job titles in the Professional Experience section. In DOCX output, each experience
date range is right-aligned across from its job title.

Generated resume and cover-letter `.html` and `.docx` files are written to
`JOB_AGENT_GENERATED_DOCUMENTS` (default: `data/generated_documents`) and are
ignored by Git. Open HTML in a browser to review it or use the browser's
**Print → Save as PDF** function when a PDF is needed. DOCX files can be edited in
Microsoft Word, LibreOffice Writer, or another compatible editor. Running the
command again for the same candidate, job, and format replaces the existing file.
Always review the document before using it in an application.

After both documents are written, the application stores their basenames in
`job_prospects.resume_file_name` and `job_prospects.cover_letter_file_name` in
one database update. For `--resume-format both`, the DOCX filenames are stored.
If either filename is null, the package remains queued; failed attempts can be
retried. This also lets the scheduled worker create cover letters for eligible
rows that already have a resume from an earlier release.

### Prepare an application without submitting it

Install Selenium and ensure Google Chrome is available on the machine where the
interactive review will occur:

```bash
python3 -m pip install -e '.[browser]'
```

Configure the review-only browser and GPT-5.4 form-answer agent in `.env`:

```env
OPENAI_API_KEY=your-api-key
JOB_AGENT_APPLICATION_BROWSER_ENABLED=true
JOB_AGENT_APPLICATION_BROWSER_HEADLESS=false
JOB_AGENT_APPLICATION_BROWSER_TIMEOUT_SECONDS=30
JOB_AGENT_APPLICATION_ANSWER_MODEL=gpt-5.4
JOB_AGENT_APPLICATION_ANSWER_TIMEOUT_SECONDS=60
JOB_AGENT_APPLICATION_ANSWER_MAX_OUTPUT_TOKENS=1500
JOB_AGENT_APPLICATION_MAX_STEPS=10
JOB_AGENT_APPLICATION_PROMPT=prompts/fill_application.txt
```

`JOB_AGENT_APPLICATION_BROWSER_TIMEOUT_SECONDS` controls full page navigation.
Ordinary field discovery has no implicit Selenium delay; dynamic combobox options
wait for at most one second and navigation controls settle for at most 0.2 seconds.

Select a prospect that already has a generated resume:

```sql
SELECT job_id, title, company, url, resume_file_name
FROM job_prospects
WHERE resume_file_name IS NOT NULL
ORDER BY `match` DESC;
```

Open and prepare its application:

```bash
python3 app.py --prepare-application JOB_ID
```

The command opens the stored job URL in Chrome, follows a visible external
**Apply** link when needed, discovers native fields in the page and embedded
frames, fills contact details locally, asks GPT-5.4 for evidence-grounded answers
to remaining questions through a non-stored OpenAI Responses API request, and
uploads the exact file named by
`job_prospects.resume_file_name`. Safe **Next**, **Continue**, and review steps
are supported up to the configured limit. The stored application resume must be
a DOCX or PDF; regenerate an HTML-only resume with `--resume-format docx` first.

Protected demographic data, disability and veteran status, work authorization,
sponsorship, salary expectations, availability, consent, and signatures are
never inferred. Add reviewed values to `application_answers` when those fields
should be populated. Unsupported fields remain visible and are reported as
unresolved instead of being fabricated.

The workflow never calls the submission agent, never sends Enter keystrokes,
never clicks a final submit control, and disables recognized final submission
controls on every discovered step. In an interactive terminal, Chrome remains
open for review until Enter is pressed in the terminal; that Enter closes the
browser rather than submitting the form. CAPTCHA, login, shadow-DOM widgets,
and site-specific controls may require manual handling. No application status
is persisted yet, and job-board terms still apply.

Every generated or pre-existing form answer is emitted as a structured `INFO`
log event named `application_form_answer`, including the job ID, step, field ID,
label, answer source, fill status, and complete value. Resume uploads and
unresolved fields are logged as well. These records contain personal and
potentially sensitive application data, so restrict access to terminal, SSM,
CloudWatch, and redirected log output and configure an appropriate retention
period.

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
| `greenhouse` | Stored company feeds | At least one board token in `company_prospects`, or an optional `Company=board_token` in `JOB_AGENT_GREENHOUSE_BOARDS` |
| `lever` | Supplemental company feed | At least one `Company=site_name` in `JOB_AGENT_LEVER_SITES` |
| `workday` | Supplemental company feed | At least one `Company=public_cxs_url` in `JOB_AGENT_WORKDAY_TENANTS` |
| `career_page` | Supplemental company page | At least one `Company=public_url` in `JOB_AGENT_CAREER_PAGES` |
| `linkedin` | Global discovery through Apify | `JOB_AGENT_LINKEDIN_ENABLED=true` and `JOB_AGENT_APIFY_API_TOKEN`; the default compatible Actor ID can be overridden |

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

The normal search command loads a rotating batch of board tokens collected in
`company_prospects`. No company-specific environment configuration is required
for crawled boards. Configure the maximum number of boards fetched by one
search run; the default is 25:

```env
JOB_AGENT_GREENHOUSE_BOARD_LIMIT=25
JOB_AGENT_GREENHOUSE_SCRAPER_ENABLED=true
JOB_AGENT_GREENHOUSE_SCRAPER_CONCURRENCY=5
```

Greenhouse search first uses the public Job Board API to obtain each selected
board's openings. Jobs that match the current title and location query are then
enriched from their public detail pages using the JSON-LD technique adapted
from [MarcusKyung/greenhouse.io-scraper](https://github.com/MarcusKyung/greenhouse.io-scraper).
The scraper extracts Schema.org `JobPosting` data, including the original
`datePosted`, and stores it in the normalized payload and the queryable
`job_prospects.posted_at` column. Detail pages are cached for the search run,
and requests are limited by `JOB_AGENT_GREENHOUSE_SCRAPER_CONCURRENCY`.

The scraper is enabled by default. Set
`JOB_AGENT_GREENHOUSE_SCRAPER_ENABLED=false` to use only the board API. If a
detail page is unavailable or lacks valid JobPosting JSON-LD, the API result is
still retained and `posted_at` remains unknown instead of treating
Greenhouse's last-update timestamp as the publication date. Third-party license
attribution is recorded in `THIRD_PARTY_NOTICES.md`.

Unsearched boards are selected first, followed by the least recently searched
boards. To add a board that the crawler has not discovered, configure a company
display name and its board token:

```env
JOB_AGENT_GREENHOUSE_BOARDS=Example Company=example
```

The board token is the path segment in `https://boards.greenhouse.io/{board_token}`. For multiple boards, separate entries with semicolons:

```env
JOB_AGENT_GREENHOUSE_BOARDS=Company One=companyone;Company Two=companytwo
```

Manually configured boards take precedence when a stored entry uses the same
token and count toward the per-run limit. Each selected board feed is downloaded
once per search run, shared across all title queries, and filtered using the
normal search criteria. Board requests are also concurrency limited to avoid
opening an unbounded number of connections. Override the environment setting
for one command with `--greenhouse-board-limit`.

##### Crawl for Greenhouse companies

The company crawler queries the Internet Archive CDX index only for public US
Greenhouse board URLs. It stores the next page for each hostname in
`crawl_discovery_cursors`, so a fresh cron process continues from the prior
run instead of repeatedly requesting page zero. When the current archive page
contains no unseen boards, discovery supplements it with the latest Common
Crawl URL index, which has its own cursor scoped to that crawl collection. It
extracts and deduplicates board tokens, then validates each candidate through
Greenhouse's public Job Board API. Greenhouse returns the organization name for
a valid board; the crawler then inserts that company in `company_prospects`.
Successful known boards are excluded from future validation runs. Failed
validations use a separate retry queue and are retried after a shorter
configurable cooldown.

The crawler is disabled by default. Enable it in `.env`:

```env
JOB_AGENT_COMPANY_CRAWLER_ENABLED=true
JOB_AGENT_COMPANY_CRAWLER_SCAN_LIMIT=5000
JOB_AGENT_COMPANY_CRAWLER_LIMIT=100
JOB_AGENT_COMPANY_CRAWLER_CONCURRENCY=5
JOB_AGENT_COMPANY_CRAWLER_REQUEST_DELAY_SECONDS=1
JOB_AGENT_COMPANY_CRAWLER_FAILED_RETRY_HOURS=24
```

Run one crawl with:

```bash
python3 app.py --crawl-greenhouse-companies --crawl-limit 100
```

### Scheduled company crawler

The crawler can run every five minutes through the current user's crontab. The
installed schedule uses the project runner, which prevents overlapping crawls,
runs with a per-crawl limit of 100, and appends output to
`logs/greenhouse-crawler.log`:

```cron
*/5 * * * * /Users/brandonwirgau/Projects/JobSearchPipeline/scripts/run_greenhouse_crawler.sh
```

Inspect or remove the schedule with `crontab -l` or `crontab -e`. The `logs/`
directory is ignored by Git. Cron uses the project's `.venv` Python executable
and the application continues to load database and crawler settings from
`.env`.

### Scheduled Greenhouse prospect search, matching, and resume generation

The prospect-search runner reserves the next rotating batch of Greenhouse board
tokens from `company_prospects`, searches those boards using the candidate's
configured titles and requirements, and persists normalized postings in
`job_prospects`. It does not make Gemini requests.

The script prevents overlapping searches and appends output to
`logs/greenhouse-prospect-search.log`. It defaults to 100 results per title
query. Override that limit through the cron environment if needed:

```cron
JOB_AGENT_GREENHOUSE_SEARCH_LIMIT=100
JOB_AGENT_GREENHOUSE_BOARD_LIMIT=25
4 * * * * /opt/job-agent/scripts/run_greenhouse_prospect_search.sh
```

This schedule runs once per hour at four minutes past the hour. Adjust the
absolute project path when the deployment is not located at `/opt/job-agent`.
The separate matcher runs every minute, claims up to 15 stored prospects where
`resume_generation_checked` is false, spaces Gemini requests four seconds
apart, and writes successful scores back to the same rows:

```cron
JOB_AGENT_MATCHING_MAX_REQUESTS_PER_RUN=15
* * * * * /opt/job-agent/scripts/run_job_matcher.sh
```

The document generator also runs every minute by default. It selects the
least-recently-attempted candidates missing a resume or cover-letter filename,
uses match score as a tie-breaker, generates both documents in the configured
format, and stores their basenames only after both are written successfully:

```cron
JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT=1
JOB_AGENT_RESUME_GENERATION_BATCH_FORMAT=docx
* * * * * /opt/job-agent/scripts/run_resume_generator.sh
```

The conservative default processes one document package per minute to control OpenAI API
usage and instance load; raise the limit to at most 100 when appropriate. The
repeated cron runs eventually drain every eligible row. Each runner uses a lock
directory, so an overlapping invocation exits without starting another batch.
Before enabling them, configure these values in the project's `.env`:

```env
JOB_AGENT_SEARCH_ENABLED=true
JOB_AGENT_GREENHOUSE_BOARD_LIMIT=25
GEMINI_API_KEY=your-api-key
OPENAI_API_KEY=your-api-key
JOB_AGENT_RESUME_GENERATION_BATCH_LIMIT=1
JOB_AGENT_RESUME_GENERATION_BATCH_FORMAT=docx
```

Install all four project schedules (crawler, prospect search, matcher, and
resume generator) for the current user from the project root. The installer is
idempotent, replaces older entries for these scripts, and preserves unrelated
crontab entries:

```bash
./scripts/install_cron_jobs.sh
```

Override schedules only for the installer invocation when needed:

```bash
JOB_AGENT_PROSPECT_SEARCH_CRON_SCHEDULE='*/30 * * * *' \
JOB_AGENT_MATCHER_CRON_SCHEDULE='* * * * *' \
JOB_AGENT_RESUME_GENERATOR_CRON_SCHEDULE='* * * * *' \
  ./scripts/install_cron_jobs.sh
```

Alternatively, edit the schedule directly with `crontab -e`. Verify the jobs
with:

```bash
crontab -l
pgrep -af 'run_greenhouse_(crawler|prospect_search)|run_job_matcher|run_resume_generator'
tail -f /opt/job-agent/logs/greenhouse-prospect-search.log
tail -f /opt/job-agent/logs/job-matcher.log
tail -f /opt/job-agent/logs/resume-generator.log
```

Run the scheduled behavior manually without waiting for cron:

```bash
./scripts/run_greenhouse_prospect_search.sh
./scripts/run_job_matcher.sh
./scripts/run_resume_generator.sh
```

The equivalent application command is:

```bash
python3 app.py --search \
  --source greenhouse \
  --greenhouse-board-limit 25 \
  --limit 100

python3 app.py --match-prospects --match-limit 15
python3 app.py --generate-matched-resumes --resume-limit 1 --resume-format docx
```

Each successful search refreshes stored posting data without erasing an
existing score or eligibility-check flag. The matcher only selects prospects
where `resume_generation_checked` is false and `job_data` is available. This
includes legacy scores not graded by the current LLM workflow. A successful
evaluation marks the flag true whether or not the role qualifies; failed jobs
remain unchecked and are retried by a later minute-based run.

The document worker only selects rows marked as candidates with a non-null match,
generation model, and normalized `job_data`, where either `resume_file_name` or
`cover_letter_file_name` is null.
Each attempt refreshes `updated_at`, so a persistent failure moves behind other
pending work instead of blocking the queue. Failures are logged and remain
pending for a later run. Successful files are stored under
`JOB_AGENT_GENERATED_DOCUMENTS`; only their basenames are saved in MySQL.

`JOB_AGENT_COMPANY_CRAWLER_SCAN_LIMIT` is the maximum number of URL-index
records returned from the current archive page for each supported Greenhouse
hostname. `--crawl-limit` caps the number of unique boards validated in one
run. Previously unseen boards are always validated before failed retries, and
the persisted page cursors make subsequent runs scan different portions of the
indexes. Logs report the provider, hostname, and current page. The terminal
output distinguishes raw index candidates, new boards, known boards, ready and
deferred retries, checked boards, insertions, and failures. It prints every
successfully validated company in a grid.

The scheduled runner reads `JOB_AGENT_COMPANY_CRAWLER_LIMIT` for its
`--crawl-limit` value. This is separate from the larger archive scan limit.

`JOB_AGENT_COMPANY_CRAWLER_REQUEST_DELAY_SECONDS` sets the minimum idle interval
between every outbound crawler request. The interval applies globally to archive
discovery, retries, Common Crawl fallback, and individual Greenhouse board API
checks. Requests are serialized even though board-validation tasks may be queued
concurrently. The default is one second; increase it if a gateway starts
rejecting requests.

`JOB_AGENT_COMPANY_CRAWLER_FAILED_RETRY_HOURS` controls when an unsuccessful
board validation becomes eligible for retry. The default is `24` hours.
Successful boards are recorded as known and are never revisited by the
discovery crawler. Failed boards are retried from the stored queue even when
they are absent from the latest archive result or public index discovery is
temporarily unavailable. Existing failed rows are automatically rescheduled
from their last attempt when this setting changes. Archive indexes are still
polled each run because that discovery step is required to find newly listed
board URLs.

The former `JOB_AGENT_COMPANY_CRAWLER_REVISIT_INTERVAL_HOURS` setting is no
longer used. Replace it with `JOB_AGENT_COMPANY_CRAWLER_FAILED_RETRY_HOURS` when
upgrading an existing deployment.

The crawler reads URL indexes only; it does not download archived page content.
CDX requests are sequential and delayed because public indexes are rate-limited.
Archive requests use the smallest CDX page size and retry once after an HTTP
failure. Common Crawl requests are attempted up to three times; failure on one
hostname does not discard candidates from other hosts. If both public indexes
are temporarily unavailable, the crawler logs a warning and processes only
stored failed validations whose retry cooldown has expired. It does not revisit
successful companies. The run fails only when discovery is unavailable and
there is no stored company or crawl history from which to continue safely.
Keep the delay enabled, avoid concurrent crawler runs, and use Common Crawl's
bulk URL Index instead if this grows into a large-scale data collection
workload. Archive indexes can be incomplete or stale, so every token is verified
against Greenhouse before it is persisted.

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
JOB_AGENT_LINKEDIN_ENABLED=true
JOB_AGENT_APIFY_API_TOKEN=your-apify-api-token
JOB_AGENT_APIFY_LINKEDIN_ACTOR_ID=automation-lab/linkedin-jobs-scraper
JOB_AGENT_APIFY_TIMEOUT_SECONDS=120
```

Both `JOB_AGENT_LINKEDIN_ENABLED=true` and a token are required for live LinkedIn search. Set the flag to `false` to keep the token configured while excluding LinkedIn from searches. The Actor ID and timeout already have the defaults shown above. The integration uses the input and output contract of [`automation-lab/linkedin-jobs-scraper`](https://apify.com/automation-lab/linkedin-jobs-scraper): role and requirement terms become `searchQuery`, location or remote country becomes `location`, and supported employment, remote-only, result-count, and posting-age filters are sent to the Actor. Only override the Actor ID with an Actor that accepts the same fields and returns a compatible dataset.

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

Search only the Greenhouse boards stored in `company_prospects` (plus any
manually configured additions):

```bash
python3 app.py --search \
  --source greenhouse \
  --title "AI Engineer" \
  --remote \
  --remote-country us \
  --greenhouse-board-limit 25 \
  --limit 25
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

Search results are normalized, filtered, deduplicated, printed to the terminal, and stored in the configured MySQL `job_prospects` table. Matching is performed separately with `python3 app.py --match-prospects --match-limit 15`. If the application reports that no source supports the search, confirm that the search flag is enabled and at least one source is configured.

Live search is disabled by default:

```env
JOB_AGENT_SEARCH_ENABLED=false
```

Enabling the search flag alone does not enable the separate Selenium application
browser. Application preparation is opt-in and the current database does not
persist application state.

## Project Structure

```text
.
├── app.py                         # Composition root
├── config.py                      # Environment settings
├── docker-compose.yml            # Persistent MySQL development service
├── pyproject.toml                 # Packaging and optional dependencies
├── .env.example                   # Safe configuration template
├── agents/                        # Single-responsibility pipeline agents
├── models/                        # Shared domain and resume-knowledge models
├── services/                      # External capability boundaries
├── workflows/                     # Pipeline orchestration
├── repositories/                  # Persistence interfaces and MySQL implementations
├── database/                      # Connection, schema, and migration files
├── prompts/                       # Reusable LLM prompt templates
├── browser/                       # Selenium review filling and platform adapters
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

Install the project and MySQL Connector/Python in editable mode:

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

### Configure MySQL

MySQL 8.4 is recommended. The included Docker Compose service runs MySQL in the background, restarts it unless explicitly stopped, and persists its data in the `job-agent-mysql-data` named volume.

Configure distinct application and root passwords in `.env`:

```env
JOB_AGENT_MYSQL_HOST=127.0.0.1
JOB_AGENT_MYSQL_PORT=3306
JOB_AGENT_MYSQL_DATABASE=job_agent
JOB_AGENT_MYSQL_USER=job_agent
JOB_AGENT_MYSQL_PASSWORD=replace-with-a-strong-password
JOB_AGENT_MYSQL_ROOT_PASSWORD=replace-with-a-different-strong-password
JOB_AGENT_MYSQL_CONNECT_TIMEOUT=10
```

Start MySQL as a detached background service and check its health:

```bash
docker compose -f docker-compose.yml up --detach mysql
docker compose -f docker-compose.yml ps mysql
```

The service remains running after tests and across Docker restarts. Stop it explicitly with `docker compose -f docker-compose.yml stop mysql`; start it again with `docker compose -f docker-compose.yml start mysql`. `docker compose -f docker-compose.yml down` removes the container and network but retains the named database volume unless `--volumes` is also specified.

MySQL's initialization variables are applied only when the named volume is first created. Changing either password in `.env` later does not change an existing database account; update the account inside MySQL or deliberately create a new development volume.

To use an existing MySQL server instead of Docker, create the database and application account manually. Run the following statements as a MySQL administrator, replacing the example password and host as needed:

```sql
CREATE DATABASE job_agent
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

CREATE USER 'job_agent'@'127.0.0.1'
    IDENTIFIED BY 'replace-with-a-strong-password';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
    ON job_agent.*
    TO 'job_agent'@'127.0.0.1';
```

The Docker-only root password setting is unnecessary when using an existing server. The committed `.env.example` contains placeholders only, while `.env` is ignored by Git. Use a deployment secret manager instead of a file in hosted environments. The application never includes the application password in its startup log or the `MySQLConfig` representation.

The configured database must already exist. On startup, the application creates missing tables and records the current schema version:

```bash
python3 app.py
```

Existing SQLite files are not read or migrated automatically. Export any data that must be retained and import it into MySQL before removing an old database file.

### Copy the AWS database to local MySQL

The guarded database-copy command opens an AWS Systems Manager port-forwarding session, streams a consistent MySQL dump from EC2 into the local Docker database, and closes the tunnel afterward. It replaces the local database only when the explicit replacement flag is present and first writes a restorable backup under `data/database_backups/` (ignored by Git).

Prerequisites:

- AWS CLI v2 and the Session Manager plugin, authenticated to the account containing the EC2 instance
- `mysqldump` installed locally and available on `PATH`
- The EC2 instance online in Systems Manager with MySQL listening on its loopback port
- The remote application database username and password

On macOS, the MySQL client can be installed with Homebrew:

```bash
brew install mysql-client
export PATH="/opt/homebrew/opt/mysql-client/bin:$PATH"
```

Run the copy from the project root. The command securely prompts for the remote MySQL password when `JOB_AGENT_AWS_MYSQL_PASSWORD` is unset:

```bash
./scripts/copy_aws_database.sh \
  --instance-id i-031605ff346d95e2e \
  --region us-east-1 \
  --replace-local-database
```

Use `--profile PROFILE_NAME` when the required AWS session is stored in a named CLI profile. The remote database and user default to `job_agent`; override them with `--remote-database` and `--remote-user`. The remote and local database names must match so the dump can replace the local database exactly.

If the import fails after replacement begins, restore the timestamped backup printed by the command:

```bash
docker compose -f docker-compose.yml exec -T mysql \
  sh -c 'exec mysql --user=root --password="$MYSQL_ROOT_PASSWORD"' \
  < data/database_backups/LOCAL_BACKUP.sql
```

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

The suite covers resume knowledge, parsing, structured LLM matching, single-job
and queued resume generation, review-only application filling, MySQL
job-prospect persistence, the search safety flag, and fixture-based
normalization for every Phase 3 source without making network or live-database
requests. LLM, Selenium, and repository tests use injected fakes; use a
separate integration environment to validate API credentials, model access,
database credentials, and server permissions.

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

The next phase can add source health telemetry, pagination checkpoints, evidence
links, application audit persistence, platform-specific form adapters, and a
review interface. Final submission should remain out of scope until validation,
approval auditing, and site-specific dry runs are reliable.
