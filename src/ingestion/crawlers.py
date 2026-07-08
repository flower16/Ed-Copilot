"""Live crawlers for Frisco ISD and Plano ISD course catalogs.

Ported and adapted from flower16/copilot-for-families/backend/app/ingestion/crawlers.py

Fetch strategy per district:
  Frisco ISD: Playwright headless Chromium (JS-rendered catalog app)
              → falls back to httpx static fetch if Playwright not installed
  Plano ISD:  httpx static fetch (server-rendered HTML catalog)

parse_courses() splits a catalog page into per-course documents.
Everything is best-effort — never raises, always returns a (possibly empty) list.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

_PREREQ_RE = re.compile(r"prerequisite[s]?\s*[:\-]?\s*(.+?)(?:\.|$)", re.I)
_HEADINGS = ["h2", "h3", "h4"]

_COURSE_HINT = re.compile(
    r"algebra|geometry|precalculus|pre-calculus|calculus|statistics|trigonometry|"
    r"math\s*models|quantitative|financial|discrete|semester\s*\d", re.I
)
_NOISE = re.compile(
    r"log into|register|skyward|family access|counselor|how to|to register|"
    r"contact|department|navigation|search|print", re.I
)


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _render_playwright(url: str) -> Optional[str]:
    """Render a JS-heavy page with Playwright. Returns HTML or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="EdCopilot/1.0")
            page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
            browser.close()
            return html
    except Exception as exc:
        print(f"[crawl] playwright failed for {url}: {type(exc).__name__}: {exc}")
        return None


def _fetch_static(url: str) -> str:
    with httpx.Client(
        timeout=25, follow_redirects=True,
        headers={"User-Agent": "EdCopilot/1.0"}
    ) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def _get_html(url: str) -> str:
    return _render_playwright(url) or _fetch_static(url)


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _clean(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    return soup


def _text_after_heading(heading, all_headings: list) -> str:
    """Collect body text following a heading until the next heading."""
    parts = []
    for el in heading.next_elements:
        if getattr(el, "name", None) in _HEADINGS and el is not heading:
            break
        if isinstance(el, str) and el.strip() and heading not in el.parents:
            parts.append(el.strip())
    return " ".join(" ".join(parts).split())


def parse_courses(
    html: str,
    source_url: str,
    district_id: str,
    district_name: str,
    doc_type: str = "course_catalog",
    subject: str = "math",
) -> list[dict]:
    """Parse a catalog HTML page into per-course documents.

    Falls back to one page-level document if no individual courses are found.
    """
    soup = _clean(html)
    docs: list[dict] = []
    seen: set[str] = set()

    for h in soup.find_all(_HEADINGS):
        title = " ".join(h.get_text().split())
        if not (3 < len(title) < 90):
            continue
        if _NOISE.search(title) or not _COURSE_HINT.search(title):
            continue

        body = _text_after_heading(h, soup.find_all(_HEADINGS))
        if len(body) < 40 and not re.search(r"credit|prerequisite|grade", body, re.I):
            continue

        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        prereq = _PREREQ_RE.search(body)
        prereq_suffix = ""
        if prereq and "prerequisite" not in body.lower():
            prereq_suffix = f" Prerequisite: {prereq.group(1).strip()}."

        docs.append({
            "district": district_id,
            "doc_type": doc_type,
            "subject": subject,
            "school_level": "high_school",
            "course": title,
            "course_number": "",
            "grade": [9, 10, 11, 12],
            "field": "description",
            "source_url": source_url + "#" + re.sub(r"\W+", "-", key).strip("-"),
            "doc_title": f"{district_name} Course Catalog",
            "text": f"{title}. {body}{prereq_suffix}"[:2000],
        })

    if docs:
        return docs

    # Fallback: whole page as one document
    text = " ".join(soup.get_text(separator=" ").split())
    if len(text) < 200:
        print(f"[crawl] {source_url} yielded very little text — may be JS-only shell.")
        return []
    return [{
        "district": district_id,
        "doc_type": doc_type,
        "subject": subject,
        "school_level": "high_school",
        "course": None,
        "course_number": "",
        "grade": [9, 10, 11, 12],
        "field": "page",
        "source_url": source_url,
        "doc_title": f"{district_name} Course Catalog",
        "text": text[:6000],
    }]


# ---------------------------------------------------------------------------
# Apptegy / Google Apps Script API (Frisco ISD)
# ---------------------------------------------------------------------------

def _grades_to_list(grade_str: str) -> list[int]:
    return [int(g) for g in re.findall(r"\d+", grade_str or "")] or [9, 10, 11, 12]


def crawl_apptegy_api(
    api_url: str,
    page_url: str,
    district_id: str,
    district_name: str,
    department_filter: str = "math",
    doc_type: str = "course_catalog",
    subject: str = "math",
) -> list[dict]:
    """Pull structured course data from an Apptegy spreadsheet-app JSON endpoint."""
    r = httpx.get(
        api_url, timeout=60, follow_redirects=True,
        headers={"User-Agent": "EdCopilot/1.0"}
    )
    r.raise_for_status()
    programs = r.json().get("data", {}).get("programs", [])

    docs = []
    for c in programs:
        dept = c.get("department", "").lower()
        if department_filter and department_filter.lower() not in dept:
            continue
        name = (c.get("courseName") or "").strip()
        if not name:
            continue

        desc_html = c.get("longDescription") or c.get("courseDescription") or ""
        desc = " ".join(BeautifulSoup(desc_html, "html.parser").get_text(" ").split())
        prereq  = (c.get("prerequisites") or "").strip()
        credit  = (c.get("credit") or "").strip()
        grade_s = (c.get("grade") or "").strip()
        code    = c.get("courseCode", "")

        text = (
            f"{name} ({code}). {desc}"
            + (f" Prerequisite: {prereq}." if prereq else "")
            + (f" Credit: {credit}." if credit else "")
            + (f" Grade(s): {grade_s}." if grade_s else "")
        ).strip()

        docs.append({
            "district": district_id,
            "doc_type": doc_type,
            "subject": subject,
            "school_level": "high_school",
            "course": name,
            "course_number": code,
            "grade": _grades_to_list(grade_s),
            "field": "description",
            "source_url": f"{page_url}#{code}",
            "doc_title": f"{district_name} HS Course Catalog",
            "text": text[:2200],
        })
    return docs


# ---------------------------------------------------------------------------
# District-specific crawl entry points
# ---------------------------------------------------------------------------

FRISCO_CATALOG_URL = "https://www.friscoisd.org/academics/course-catalog"
PLANO_CATALOG_URL  = "https://www.pisd.edu/students-families-a6/eschool/catalog/mathematics"


def crawl_frisco(subject: str = "math") -> list[dict]:
    """Crawl Frisco ISD course catalog. Playwright → httpx fallback."""
    print(f"[crawl] Frisco ISD: fetching {FRISCO_CATALOG_URL}")
    try:
        html = _get_html(FRISCO_CATALOG_URL)
        docs = parse_courses(
            html,
            source_url=FRISCO_CATALOG_URL,
            district_id="frisco_isd_tx",
            district_name="Frisco ISD",
            subject=subject,
        )
        print(f"[crawl] Frisco ISD: {len(docs)} course doc(s) parsed")
        return docs
    except Exception as exc:
        print(f"[crawl] Frisco ISD crawl failed: {type(exc).__name__}: {exc}")
        return []


def crawl_plano(subject: str = "math") -> list[dict]:
    """Crawl Plano ISD course catalog (static HTML fetch)."""
    print(f"[crawl] Plano ISD: fetching {PLANO_CATALOG_URL}")
    try:
        html = _fetch_static(PLANO_CATALOG_URL)
        docs = parse_courses(
            html,
            source_url=PLANO_CATALOG_URL,
            district_id="plano_isd_tx",
            district_name="Plano ISD",
            subject=subject,
        )
        print(f"[crawl] Plano ISD: {len(docs)} course doc(s) parsed")
        return docs
    except Exception as exc:
        print(f"[crawl] Plano ISD crawl failed: {type(exc).__name__}: {exc}")
        return []
