# Database migrations

The complete MySQL schema for new databases is defined in `database/schema.py`. Ordered migration files capture incremental changes for existing MySQL databases; migrations should be forward-only and safe to run more than once.

- `002_resume_knowledge.sql` adds structured resume knowledge persistence.
