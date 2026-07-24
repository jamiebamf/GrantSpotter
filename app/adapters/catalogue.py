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
    max_listing_pages: int = 12


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
            "https://findbusinesssupport.gov.scot/search?type=Funding",
            "https://findbusinesssupport.gov.scot/service/funding",
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
        listing_urls=("https://www.artscouncil.org.uk/our-open-funds",),
        allowed_hosts=("www.artscouncil.org.uk",),
        detail_path_patterns=(r"^/[^/]*fund[^/]*/?.*$", r"^/our-open-funds/[^/]+/?$"),
        excluded_path_patterns=(r"^/our-open-funds/?$",),
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
        cfg = settings()
        self.delay = cfg.request_delay_seconds
        self.client = httpx.AsyncClient(
            timeout=40,
            follow_redirects=True,
            headers={
                "User-Agent": cfg.crawler_user_agent,
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch(self, url: str) -> tuple[int, str, str]:
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
        listings = self.source.listing_urls[: max_pages or self.source.max_listing_pages]
        for listing_url in listings:
            try:
                _, final_listing_url, html = await self.fetch(listing_url)
            except Exception as exc:
                print(f"Listing fetch failed for {listing_url}: {exc}")
                continue
            soup = BeautifulSoup(html, "html.parser")
            for anchor in soup.select("a[href]"):
                absolute = urljoin(final_listing_url, anchor.get("href", ""))
                absolute, _ = urldefrag(absolute)
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
