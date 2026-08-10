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
- `009_job_resume_candidates.sql` marks matches above the resume-generation
  threshold and records the configured generation model.
- `010_job_prospect_posted_at.sql` stores the publication timestamp extracted
  from job-source records and Greenhouse job-page JSON-LD.
- `011_crawl_discovery_cursors.sql` persists archive-index pagination so each
  scheduled company crawl advances beyond the pages scanned by earlier runs.
- `012_resume_generation_checked.sql` tracks which jobs completed resume
  generation grading and leaves existing prospects unchecked for one-time
  LLM evaluation.
- `013_resume_file_name.sql` records generated resume filenames and indexes the
  pending resume-generation queue.
