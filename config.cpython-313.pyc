import hashlib
import re
from datetime import date
from urllib.parse import urlparse
from rapidfuzz.fuzz import ratio


def normalise_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def fingerprint(title: str, funder: str, deadline: date | None, amount: float | None, url: str) -> str:
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    material = "|".join([
        normalise_text(title),
        normalise_text(funder),
        deadline.isoformat() if deadline else "rolling",
        str(int(amount or 0)),
        domain,
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def title_similarity(a: str, b: str) -> int:
    return int(ratio(normalise_text(a), normalise_text(b)))
