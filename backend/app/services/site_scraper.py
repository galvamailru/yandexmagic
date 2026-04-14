import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


def fetch_page_text(url: str, timeout: float = 20.0) -> tuple[str, str]:
    if not url.startswith("http"):
        url = "https://" + url
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        title = (soup.title.string or "").strip() if soup.title else ""
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)[:8000]
        host = urlparse(url).netloc or url
        return title or host, text


def extract_internal_links(base_url: str, html: str, limit: int = 30) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or href.startswith("mailto:"):
            continue
        absu = urljoin(base_url, href)
        if absu not in out:
            out.append(absu)
        if len(out) >= limit:
            break
    return out
