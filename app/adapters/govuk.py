from __future__ import annotations
import asyncio
import re
from urllib.parse import urljoin, urlparse, parse_qs
import httpx
from bs4 import BeautifulSoup
from trafilatura import extract
from ..config import settings


class GovUkFindAGrantAdapter:
    slug = "govuk-find-a-grant"
    base_url = "https://www.find-government-grants.service.gov.uk"
    listing_url = f"{base_url}/grants"

    def __init__(self) -> None:
        cfg = settings()
        self.delay = cfg.request_delay_seconds
        self.client = httpx.AsyncClient(
            timeout=35,
            follow_redirects=True,
            headers={"User-Agent": cfg.crawler_user_agent, "Accept-Language": "en-GB,en;q=0.9"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch(self, url: str) -> tuple[int, str, str]:
        response = await self.client.get(url)
        response.raise_for_status()
        await asyncio.sleep(self.delay)
        return response.status_code, str(response.url), response.text

    async def discover_detail_urls(self, max_pages: int = 20) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            url = f"{self.listing_url}?limit=10&page={page}&skip={(page-1)*10}"
            _, _, html = await self.fetch(url)
            soup = BeautifulSoup(html, "html.parser")
            page_links: list[str] = []
            for anchor in soup.select("a[href]"):
                href = urljoin(self.base_url, anchor.get("href", ""))
                parsed = urlparse(href)
                if parsed.netloc != urlparse(self.base_url).netloc:
                    continue
                path = parsed.path.rstrip("/")
                if not path.startswith("/grants/") or path == "/grants":
                    continue
                clean = f"{parsed.scheme}://{parsed.netloc}{path}"
                if clean not in seen:
                    seen.add(clean)
                    page_links.append(clean)
                    found.append(clean)
            if not page_links:
                break
        return found

    def clean_page(self, html: str, url: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        for selector in ["nav", "footer", "script", "style", "noscript", ".govuk-cookie-banner"]:
            for node in soup.select(selector):
                node.decompose()
        clean = extract(str(soup), url=url, include_links=True, include_tables=True, output_format="txt")
        if not clean:
            main = soup.select_one("main") or soup.body or soup
            clean = main.get_text("\n", strip=True)
        clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
        return title, clean
