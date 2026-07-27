from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup
from trafilatura import extract

from ..config import settings


@dataclass(frozen=True)
class CatalogueSource:
    slug: str
    name: str
    listing_urls: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    detail_path_patterns: tuple[str, ...]
    excluded_path_patterns: tuple[str, ...] = ()
    seed_urls: tuple[str, ...] = ()
    embedded_pages: tuple[tuple[str, str], ...] = ()
    max_listing_pages: int = 12


ARTS_COUNCIL_NLPG_HTML = """
<!doctype html>
<html lang="en">
<head><title>Arts Council National Lottery Project Grants</title></head>
<body>
<main>
<h1>Arts Council National Lottery Project Grants</h1>
<p>Funder: Arts Council England.</p>
<p>National Lottery Project Grants is an open access programme for arts, libraries and museums projects.</p>
<p>The programme supports individual practitioners, community organisations and cultural organisations delivering creative and cultural projects that benefit people living in England.</p>
<p>Grants are available from £1,000 upwards.</p>
<p>The National Lottery Project Grants application portal supports applications of £30,000 or less.</p>
<p>Applications are rolling and the programme is currently open.</p>
<p>Applicants must create an applicant profile, complete the eligibility questionnaire and submit project details through the official portal.</p>
<p>Application URL: https://nlpg.artscouncil.org.uk/en-US/</p>
<p>Official source: https://nlpg.artscouncil.org.uk/en-US/</p>
</main>
</body>
</html>
"""


SOURCES: tuple[CatalogueSource, ...] = (
    CatalogueSource(
        slug="ukri-opportunities",
        name="UKRI Funding Opportunities",
        listing_urls=tuple(f"https://www.ukri.org/opportunity/page/{page}/" for page in range(1, 13)),
        allowed_hosts=("www.ukri.org",),
        detail_path_patterns=(r"^/opportunity/[^/]+/?$",),
        excluded_path_patterns=(r"^/opportunity/?$",),
    ),
    CatalogueSource(
        slug="govuk-business-finance",
        name="GOV.UK Business Finance Support",
        listing_urls=("https://www.gov.uk/business-finance-support?types_of_support%5B%5D=grant",),
        allowed_hosts=("www.gov.uk",),
        detail_path_patterns=(r"^/business-finance-support/[^/]+/?$",),
    ),
    CatalogueSource(
        slug="fcdo-development-funding",
        name="FCDO International Development Funding",
        listing_urls=(
            "https://www.gov.uk/international-development-funding?fund_state%5B%5D=open",
            "https://www.gov.uk/international-development-funding",
        ),
        allowed_hosts=("www.gov.uk",),
        detail_path_patterns=(r"^/international-development-funding/[^/]+/?$",),
    ),
    CatalogueSource(
        slug="scotland-business-funding",
        name="Find Business Support Scotland",
        listing_urls=(
            "https://findbusinesssupport.gov.scot/sitemap",
            "https://findbusinesssupport.gov.scot/search?type=Funding",
        ),
        allowed_hosts=("findbusinesssupport.gov.scot",),
        detail_path_patterns=(r"^/service/funding/[^/]+/?$",),
    ),
    CatalogueSource(
        slug="national-lottery-community-fund",
        name="The National Lottery Community Fund",
        listing_urls=(
            "https://www.tnlcommunityfund.org.uk/funding/programmes",
            "https://www.tnlcommunityfund.org.uk/funding/funding-programmes",
        ),
        allowed_hosts=("www.tnlcommunityfund.org.uk",),
        detail_path_patterns=(r"^/funding/programmes/[^/]+/?$", r"^/funding/funding-programmes/[^/]+/?$"),
    ),
    CatalogueSource(
        slug="heritage-fund",
        name="National Lottery Heritage Fund",
        listing_urls=("https://www.heritagefund.org.uk/funding",),
        allowed_hosts=("www.heritagefund.org.uk",),
        detail_path_patterns=(r"^/funding/[^/]+/?$",),
        excluded_path_patterns=(r"^/funding/?$",),
    ),
    CatalogueSource(
        slug="arts-council-england",
        name="Arts Council England",
        listing_urls=(),
        allowed_hosts=("nlpg.artscouncil.org.uk",),
        detail_path_patterns=(r"^/en-US/?$",),
        embedded_pages=(("https://nlpg.artscouncil.org.uk/en-US", ARTS_COUNCIL_NLPG_HTML),),
    ),
    CatalogueSource(
        slug="sport-england-funds",
        name="Sport England Funds",
        listing_urls=("https://www.sportengland.org/funds-and-campaigns/our-funds",),
        allowed_hosts=("www.sportengland.org",),
        detail_path_patterns=(r"^/funds-and-campaigns/our-funds/[^/]+/?$", r"^/funding/[^/]+/?$"),
        excluded_path_patterns=(r"^/funds-and-campaigns/our-funds/?$",),
    ),
)


class CatalogueAdapter:
    def __init__(self, source: CatalogueSource) -> None:
        self.source = source
        self.embedded_pages = dict(source.embedded_pages)
        cfg = settings()
        self.delay = cfg.request_delay_seconds
        self.client = httpx.AsyncClient(
            timeout=40,
            follow_redirects=True,
            headers={
                "User-Agent": cfg.crawler_user_agent,
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml,text/xml",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch(self, url: str) -> tuple[int, str, str]:
        clean_url = url.rstrip("/")
        if clean_url in self.embedded_pages:
            return 200, clean_url, self.embedded_pages[clean_url]
        response = await self.client.get(url)
        response.raise_for_status()
        await asyncio.sleep(self.delay)
        return response.status_code, str(response.url), response.text

    def _is_detail_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host not in self.source.allowed_hosts:
            return False
        path = parsed.path.rstrip("/") or "/"
        if any(re.search(pattern, path, re.I) for pattern in self.source.excluded_path_patterns):
            return False
        return any(re.search(pattern, path, re.I) for pattern in self.source.detail_path_patterns)

    async def discover_detail_urls(self, max_pages: int | None = None) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()

        for embedded_url in self.embedded_pages:
            if self._is_detail_url(embedded_url) and embedded_url not in seen:
                seen.add(embedded_url)
                found.append(embedded_url)

        for seed_url in self.source.seed_urls:
            clean_seed, _ = urldefrag(seed_url)
            parsed_seed = urlparse(clean_seed)
            clean_seed = f"{parsed_seed.scheme}://{parsed_seed.netloc}{parsed_seed.path.rstrip('/')}"
            if self._is_detail_url(clean_seed) and clean_seed not in seen:
                seen.add(clean_seed)
                found.append(clean_seed)

        listings = self.source.listing_urls[: max_pages or self.source.max_listing_pages]
        for listing_url in listings:
            try:
                _, final_listing_url, html = await self.fetch(listing_url)
            except Exception as exc:
                print(f"Listing fetch failed for {listing_url}: {exc}")
                continue

            soup = BeautifulSoup(html, "html.parser")
            candidates: list[str] = []
            for anchor in soup.select("a[href]"):
                candidates.append(urljoin(final_listing_url, anchor.get("href", "")))
            for loc in soup.select("loc"):
                candidates.append(loc.get_text(" ", strip=True))

            for candidate in candidates:
                absolute, _ = urldefrag(candidate)
                parsed = urlparse(absolute)
                clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
                if self._is_detail_url(clean) and clean not in seen:
                    seen.add(clean)
                    found.append(clean)
        return found

    def clean_page(self, html: str, url: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.select_one("h1")
        title = h1.get_text(" ", strip=True) if h1 else (soup.title.get_text(" ", strip=True) if soup.title else "")
        for selector in [
            "nav",
            "footer",
            "script",
            "style",
            "noscript",
            ".govuk-cookie-banner",
            "[aria-label='cookie banner']",
            ".cookie-banner",
        ]:
            for node in soup.select(selector):
                node.decompose()
        clean = extract(str(soup), url=url, include_links=True, include_tables=True, output_format="txt")
        if not clean:
            main = soup.select_one("main") or soup.body or soup
            clean = main.get_text("\n", strip=True)
        clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
        return title, clean
