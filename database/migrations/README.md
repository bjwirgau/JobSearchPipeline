# Database migrations

The complete MySQL schema for new databases is defined in `database/schema.py`. Ordered migration files capture incremental changes for existing MySQL databases; migrations should be forward-only and safe to run more than once.

- `002_resume_knowledge.sql` adds structured resume knowledge persistence.
- `003_job_prospects.sql` removes candidate, job, and application tables and adds
  the focused job-prospect projection.
- `004_job_prospect_timestamps.sql` adds database-managed creation and update
  timestamps to job prospects.
- `005_company_prospects.sql` adds Greenhouse company discovery persistence.
- `006_crawl_pages.sql` adds page-level crawl history and revisit eligibility.
- `007_job_prospect_payload.sql` stores normalized job evidence for asynchronous
  LLM matching.
- `008_company_prospect_job_search.sql` tracks rotating Greenhouse board-search
  batches.
