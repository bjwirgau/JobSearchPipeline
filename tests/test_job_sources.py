"""Fixture-driven normalization tests for Phase 3 job sources."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, Mapping

from config import Settings
from models import SearchQuery
from services import HttpResponse, JobNormalizer, build_job_sources
from services.job_sources import (
    AdzunaCredentials,
    AdzunaJobSource,
    CareerPage,
    CareerPageJobSource,
    GreenhouseBoard,
    GreenhouseJobSource,
    LeverJobSource,
    LeverSite,
    LinkedInJobSource,
    RemotiveJobSource,
    USAJobsCredentials,
    USAJobsJobSource,
    WorkdayJobSource,
    WorkdayTenant,
)


FIXTURES = Path(__file__).parent / "fixtures" / "job_sources"


class FakeHttpClient:
    def __init__(self) -> None:
        self.responses: dict[tuple[str, str], HttpResponse] = {}
        self.calls: list[tuple[str, str, object]] = []
        self.headers: list[Mapping[str, str] | None] = []

    def add(self, method: str, url: str, fixture: str, content_type: str) -> None:
        self.responses[(method, url)] = HttpResponse(
            status_code=200,
            url=url,
            text=(FIXTURES / fixture).read_text(encoding="utf-8"),
            headers={"Content-Type": content_type},
        )

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        self.calls.append(("GET", url, params))
        self.headers.append(headers)
        return self.responses[("GET", url)]

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        self.calls.append(("POST", url, payload))
        self.headers.append(headers)
        return self.responses[("POST", url)]


class FakeLinkedInClient:
    async def search_jobs(
        self,
        query: SearchQuery,
        *,
        limit: int,
    ) -> tuple[Mapping[str, Any], ...]:
        return (
            {
                "jobPostingId": "linkedin-501",
                "title": "Senior Software Engineer",
                "companyName": "Authorized Example",
                "jobPostingUrl": "https://www.linkedin.com/jobs/view/linkedin-501",
                "location": "Remote - United States",
                "description": "Build Java and AWS services.",
                "skills": ["Java", "AWS"],
                "salaryMin": 150000,
                "salaryMax": 200000,
                "salaryCurrency": "USD",
                "isRemote": True,
                "datePosted": "2026-08-01",
            },
        )


class FakePageLoader:
    def __init__(self, html: str) -> None:
        self.html = html
        self.urls: list[str] = []

    async def load(self, url: str) -> str:
        self.urls.append(url)
        return self.html


class JobSourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.http = FakeHttpClient()
        self.normalizer = JobNormalizer()
        self.query = SearchQuery(
            text="Software Engineer remote",
            title="Software Engineer",
            required_keywords=("PHP", "AWS"),
            location="Denver, CO",
            location_radius_miles=25,
            remote_only=True,
            remote_country="us",
            employment_types=("full-time",),
            minimum_salary=140000,
            excluded_keywords=("intern",),
            max_age_days=14,
        )

    async def test_adzuna_pushes_criteria_into_global_search(self) -> None:
        url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
        self.http.add("GET", url, "adzuna.json", "application/json")
        source = AdzunaJobSource(
            AdzunaCredentials("app-id", "app-key", "us"),
            http=self.http,
            normalizer=self.normalizer,
        )

        jobs = await source.search(self.query, limit=20)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.company, "Criteria Search Inc")
        self.assertEqual(job.industries, ("IT Jobs",))
        self.assertEqual(job.salary_currency, "USD")
        self.assertEqual(job.remote_country_codes, ("us",))
        params = self.http.calls[0][2]
        self.assertEqual(params["what"], "Software Engineer remote")
        self.assertEqual(params["what_and"], "PHP AWS")
        self.assertEqual(params["where"], "Denver, CO")
        self.assertEqual(params["distance"], 40)
        self.assertEqual(params["salary_min"], 140000)
        self.assertEqual(params["max_days_old"], 14)
        self.assertEqual(params["full_time"], "1")

    async def test_remotive_discovers_remote_jobs_without_company_configuration(self) -> None:
        self.http.add("GET", RemotiveJobSource.API_URL, "remotive.json", "application/json")
        source = RemotiveJobSource(http=self.http, normalizer=self.normalizer)

        jobs = await source.search(self.query, limit=10)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.source, "remotive")
        self.assertTrue(job.is_remote)
        self.assertEqual(job.remote_country_codes, ("us",))
        self.assertEqual(job.skills, ("PHP", "AWS"))
        self.assertEqual((job.salary_min, job.salary_max), (145000, 180000))
        self.assertIsNone(self.http.calls[0][2])

        await source.search(self.query, limit=5)
        self.assertEqual(len(self.http.calls), 1)

    async def test_usajobs_pushes_criteria_and_normalizes_full_results(self) -> None:
        self.http.add("GET", USAJobsJobSource.API_URL, "usajobs.json", "application/json")
        source = USAJobsJobSource(
            USAJobsCredentials("developer@example.com", "api-key"),
            http=self.http,
            normalizer=self.normalizer,
        )

        jobs = await source.search(self.query, limit=25)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.external_id, "FED-801")
        self.assertEqual(job.company, "Example Federal Agency")
        self.assertEqual(
            job.requirements[-2:],
            (
                "Experience building PHP and AWS services is required.",
                "Must be eligible to work for the federal government.",
            ),
        )
        self.assertEqual((job.salary_min, job.salary_max), (150000, 185000))
        self.assertEqual(job.remote_country_codes, ("us",))
        params = self.http.calls[0][2]
        self.assertEqual(params["PositionTitle"], "Software Engineer")
        self.assertEqual(params["Keyword"], "PHP AWS")
        self.assertEqual(params["LocationName"], "Denver, CO")
        self.assertEqual(params["Radius"], 25)
        self.assertEqual(params["RemoteIndicator"], "True")
        self.assertEqual(self.http.headers[0]["Authorization-Key"], "api-key")

    async def test_greenhouse_normalizes_and_filters_jobs(self) -> None:
        url = "https://boards-api.greenhouse.io/v1/boards/example/jobs"
        self.http.add("GET", url, "greenhouse.json", "application/json")
        source = GreenhouseJobSource(
            (GreenhouseBoard("Example Company", "example"),),
            http=self.http,
            normalizer=self.normalizer,
        )

        jobs = await source.search(self.query, limit=10)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.source, "greenhouse")
        self.assertEqual(job.title, "Senior Software Engineer")
        self.assertEqual(job.company, "Example Company")
        self.assertEqual(job.skills, ("PHP", "React", "AWS"))
        self.assertEqual((job.salary_min, job.salary_max), (140000, 180000))
        self.assertTrue(job.is_remote)

    async def test_lever_normalizes_structured_salary_and_employment(self) -> None:
        url = "https://api.lever.co/v0/postings/example"
        self.http.add("GET", url, "lever.json", "application/json")
        source = LeverJobSource(
            (LeverSite("Example Company", "example"),),
            http=self.http,
            normalizer=self.normalizer,
        )

        jobs = await source.search(self.query, limit=10)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.external_id, "lever-201")
        self.assertEqual(job.employment_type, "Full-time")
        self.assertEqual(job.skills, ("Laravel", "MySQL", "Docker"))
        self.assertEqual((job.salary_min, job.salary_max), (130000, 170000))

    async def test_workday_enriches_listing_with_job_detail(self) -> None:
        base = "https://example.wd1.myworkdayjobs.com/wday/cxs/example/Careers"
        path = "/job/Remote/Senior-Software-Engineer_R301"
        self.http.add("POST", f"{base}/jobs", "workday_list.json", "application/json")
        self.http.add("GET", f"{base}{path}", "workday_detail.json", "application/json")
        source = WorkdayJobSource(
            (WorkdayTenant("Example Company", base),),
            http=self.http,
            normalizer=self.normalizer,
        )

        jobs = await source.search(self.query, limit=10)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.external_id, "R301")
        self.assertEqual(job.source, "workday")
        self.assertEqual(job.skills, ("Magento", "PHP", "MySQL", "AWS"))
        self.assertEqual((job.salary_min, job.salary_max), (150000, 190000))
        self.assertEqual(job.employment_type, "Full time")

    async def test_company_page_normalizes_schema_org_json_ld(self) -> None:
        url = "https://careers.example.com/jobs"
        self.http.add("GET", url, "career_page.html", "text/html")
        source = CareerPageJobSource(
            (CareerPage("Fallback Company", url),),
            http=self.http,
            normalizer=self.normalizer,
        )

        jobs = await source.search(self.query, limit=10)

        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.external_id, "career-401")
        self.assertEqual(job.company, "Example Company")
        self.assertEqual(job.location, "Denver, CO, US")
        self.assertEqual(job.skills, ("Python", "React", "GraphQL"))
        self.assertEqual((job.salary_min, job.salary_max), (145000, 185000))
        self.assertTrue(job.is_remote)

    async def test_company_page_uses_browser_only_when_http_has_no_jobs(self) -> None:
        url = "https://careers.example.com/dynamic"
        self.http.responses[("GET", url)] = HttpResponse(
            status_code=200,
            url=url,
            text="<html><body>JavaScript required</body></html>",
            headers={"Content-Type": "text/html"},
        )
        loader = FakePageLoader(
            (FIXTURES / "career_page.html").read_text(encoding="utf-8")
        )
        source = CareerPageJobSource(
            (CareerPage("Fallback Company", url),),
            http=self.http,
            normalizer=self.normalizer,
            browser_loader=loader,
        )

        jobs = await source.search(self.query, limit=10)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(loader.urls, [url])

    async def test_linkedin_requires_an_authorized_client_boundary(self) -> None:
        source = LinkedInJobSource(
            FakeLinkedInClient(),
            normalizer=self.normalizer,
        )

        jobs = await source.search(self.query, limit=10)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source, "linkedin")
        self.assertEqual(jobs[0].company, "Authorized Example")
        self.assertEqual(jobs[0].skills, ("Java", "AWS"))

    def test_source_factory_builds_only_configured_sources(self) -> None:
        settings = Settings.from_env(
            {
                "JOB_AGENT_ADZUNA_APP_ID": "app-id",
                "JOB_AGENT_ADZUNA_APP_KEY": "app-key",
                "JOB_AGENT_REMOTIVE_ENABLED": "true",
                "JOB_AGENT_USAJOBS_EMAIL": "developer@example.com",
                "JOB_AGENT_USAJOBS_API_KEY": "api-key",
                "JOB_AGENT_GREENHOUSE_BOARDS": "Example=example",
                "JOB_AGENT_LEVER_SITES": "Example=example",
                "JOB_AGENT_WORKDAY_TENANTS": (
                    "Example=https://example.wd1.myworkdayjobs.com/wday/cxs/example/Careers"
                ),
                "JOB_AGENT_CAREER_PAGES": "Example=https://careers.example.com/jobs",
                "JOB_AGENT_BROWSER_FALLBACK": "none",
            }
        )

        sources = build_job_sources(settings)

        self.assertEqual(
            tuple(source.name for source in sources),
            (
                "adzuna",
                "remotive",
                "usajobs",
                "greenhouse",
                "lever",
                "workday",
                "career_page",
            ),
        )


if __name__ == "__main__":
    unittest.main()
