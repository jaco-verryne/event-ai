"""Companies House tool: is a firm on the UK register, and is it active (CLAUDE.md 10.6)."""

import requests
from pydantic import BaseModel
from rapidfuzz import fuzz

from eventai.agent.checks import company_key
from eventai.agent.tools import TIMEOUT_SECONDS, ToolError, retrying

BASE_URL = "https://api.company-information.service.gov.uk"
MATCH_MIN = 90  # token_sort_ratio of the company keys (no suffix, no punctuation)
RETRY_STATUS = {429, 500, 502, 503, 504}


class CompanyCheck(BaseModel):
    found: bool
    number: str | None = None
    name: str | None = None
    status: str | None = None
    score: float = 0


class _RetryableStatus(Exception):
    pass


class CompaniesHouse:
    """Basic auth with the API key as the user name. Each response is cached for the run."""

    def __init__(self, api_key: str | None, session: requests.Session | None = None,
                 timeout: int = TIMEOUT_SECONDS):
        self.api_key = api_key
        self.session = session or requests.Session()
        self.timeout = timeout
        self.requests_sent = 0
        self._cache: dict[tuple, dict | None] = {}

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        if not self.api_key:
            raise ToolError("no Companies House API key (COMPANIES_HOUSE_API_KEY)")
        key = (path, tuple(sorted((params or {}).items())))
        if key in self._cache:
            return self._cache[key]

        def call():
            self.requests_sent += 1
            response = self.session.get(BASE_URL + path, params=params, auth=(self.api_key, ""), timeout=self.timeout)
            if response.status_code in RETRY_STATUS:
                raise _RetryableStatus(f"HTTP {response.status_code}")
            return response

        retryable = (_RetryableStatus, requests.Timeout, requests.ConnectionError)
        try:
            for attempt in retrying(lambda err: isinstance(err, retryable)):
                with attempt:
                    response = call()
        except (_RetryableStatus, requests.RequestException) as err:
            raise ToolError(f"Companies House {path} failed: {err}") from err
        if response.status_code == 404:
            data = None
        elif response.status_code >= 400:
            raise ToolError(f"Companies House {path} failed: HTTP {response.status_code}")
        else:
            data = response.json()
        self._cache[key] = data
        return data

    def search(self, name: str) -> list[dict]:
        return (self._get("/search/companies", {"q": name, "items_per_page": 10}) or {}).get("items", [])

    def profile(self, number: str) -> dict | None:
        return self._get(f"/company/{number}")

    def check(self, name: str) -> CompanyCheck:
        """The best search hit by name; found only when the names match closely."""
        target = company_key(name)
        best, score = None, 0.0
        for item in self.search(name):
            item_score = fuzz.token_sort_ratio(target, company_key(item.get("title", "")))
            if item_score > score:
                best, score = item, item_score
        if best is None or score < MATCH_MIN:
            return CompanyCheck(found=False, score=score)
        number = best["company_number"]
        profile = self.profile(number) or {}
        return CompanyCheck(found=True, number=number, name=profile.get("company_name", best.get("title")),
                            status=profile.get("company_status", best.get("company_status")), score=score)
