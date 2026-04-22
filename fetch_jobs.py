#!/usr/bin/env python3
"""
Amazon Applied Scientist Job Fetcher
Run this locally: python3 fetch_jobs.py

Dependencies: pip install requests beautifulsoup4 lxml
"""

import requests
import json
import re
import time
from bs4 import BeautifulSoup

JOBS = [
    {
        "id": "10381672",
        "title": "Applied Scientist, Amazon Search",
        "priority": "#1 - YOUR INTERVIEWERS' TEAM (Vijay Huddar, Atul Saroop, Ankit Gandhi)",
        "url_slug": "applied-scientist-amazon-search",
    },
    {
        "id": "3089323",
        "title": "Applied Scientist, India Machine Learning",
        "priority": "#2 - Strong fit (AS I, India consumer ML)",
        "url_slug": "applied-scientist-india-machine-learning",
    },
    {
        "id": "3164218",
        "title": "Applied Scientist, International Machine Learning",
        "priority": "#3 - Strong fit (AS I, same team as above)",
        "url_slug": "applied-scientist-international-machine-learning",
    },
    {
        "id": "3104970",
        "title": "Applied Scientist, Central Machine Learning",
        "priority": "#4 - Strong fit (AS I, LLM/NLP focus)",
        "url_slug": "applied-scientist-central-machine-learning",
    },
    {
        "id": "2720385",
        "title": "Applied Scientist, Amazon",
        "priority": "#5 - Good fit (AS I, general ML India)",
        "url_slug": "applied-scientist-amazon",
    },
    {
        "id": "3202426",
        "title": "Applied Scientist II, Alexa AI (GenAI)",
        "priority": "STRETCH - AS II but GenAI/LLM is perfect fit",
        "url_slug": "applied-scientist-ii-alexa-ai",
    },
    {
        "id": "3195389",
        "title": "Applied Scientist II, Central Machine Learning",
        "priority": "STRETCH - AS II level (4-9 yrs typically)",
        "url_slug": "applied-scientist-ii-central-machine-learning",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
}

JSON_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.amazon.jobs/en/search",
}


def build_url(job: dict) -> str:
    return f"https://www.amazon.jobs/en/jobs/{job['id']}/{job['url_slug']}"


def extract_json_ld(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def find_section(soup: BeautifulSoup, keywords: list[str]) -> str:
    """Find a block of text following a heading that matches one of the keywords."""
    for heading in soup.find_all(["h2", "h3", "h4", "b", "strong", "p"]):
        text = heading.get_text(" ", strip=True).lower()
        if any(kw in text for kw in keywords):
            buf = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ("h2", "h3", "h4"):
                    break
                content = sibling.get_text("\n", strip=True)
                if content:
                    buf.append(content)
            result = "\n".join(buf).strip()
            if result:
                return result
    return ""


def truncate(text: str, n: int = 900) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:n] + "\n…(truncated)" if len(text) > n else text


def fetch_job(session: requests.Session, job: dict) -> dict:
    url = build_url(job)
    out = {**job, "url": url, "location": "", "basic_quals": "",
           "preferred_quals": "", "responsibilities": "", "description": "", "error": ""}

    # Try HTML page
    try:
        resp = session.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        out["error"] = f"HTTP {exc.response.status_code}"
        # Fallback: try the JSON endpoint
        try:
            jr = session.get(
                f"https://www.amazon.jobs/en/jobs/{job['id']}.json",
                headers=JSON_HEADERS, timeout=15
            )
            jr.raise_for_status()
            data = jr.json()
            out["description"] = truncate(BeautifulSoup(data.get("description", ""), "lxml").get_text("\n"))
            out["location"] = data.get("city", "") or data.get("normalized_location", "")
            out["error"] = ""
        except Exception:
            pass
        return out
    except requests.RequestException as exc:
        out["error"] = str(exc)
        return out

    soup = BeautifulSoup(resp.text, "lxml")

    # 1. JSON-LD (richest structured source)
    ld = extract_json_ld(soup)
    if ld:
        loc = ld.get("jobLocation", {})
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        out["location"] = loc.get("address", {}).get("addressLocality", "")
        raw_desc = BeautifulSoup(ld.get("description", ""), "lxml").get_text("\n")
        out["description"] = truncate(raw_desc)

    # 2. Location fallback
    if not out["location"]:
        for cls in ["location", "job-location", "city"]:
            tag = soup.find(class_=re.compile(cls, re.I))
            if tag:
                out["location"] = tag.get_text(strip=True)
                break

    # 3. Structured sections
    out["responsibilities"] = truncate(find_section(soup, [
        "key job responsibilities", "responsibilities", "what you'll do"
    ]))
    out["basic_quals"] = truncate(find_section(soup, [
        "basic qualifications", "minimum qualifications", "required qualifications"
    ]))
    out["preferred_quals"] = truncate(find_section(soup, [
        "preferred qualifications", "preferred experience", "nice to have"
    ]))

    # 4. Fallback to main content if nothing parsed
    if not out["basic_quals"] and not out["description"]:
        main = soup.find("main") or soup.find(id=re.compile(r"content|main", re.I))
        if main:
            out["description"] = truncate(main.get_text("\n"), 1400)

    return out


def print_job(r: dict):
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  {r['priority']}")
    print(f"  {r['title']}  [Job ID: {r['id']}]")
    print(f"  {r['url']}")
    if r["error"]:
        print(f"\n  ⚠  Could not fetch: {r['error']}")
        return
    if r["location"]:
        print(f"  Location: {r['location']}")
    if r["responsibilities"]:
        print(f"\n  KEY RESPONSIBILITIES:\n{r['responsibilities']}")
    if r["basic_quals"]:
        print(f"\n  BASIC QUALIFICATIONS:\n{r['basic_quals']}")
    if r["preferred_quals"]:
        print(f"\n  PREFERRED QUALIFICATIONS:\n{r['preferred_quals']}")
    if r["description"] and not r["basic_quals"]:
        print(f"\n  DESCRIPTION:\n{r['description']}")


def main():
    session = requests.Session()

    # Warm up: visit main page to get cookies
    print("Warming up session...")
    try:
        session.get("https://www.amazon.jobs/en", headers=HEADERS, timeout=12)
        time.sleep(1)
        session.get("https://www.amazon.jobs/en/search?base_query=Applied+Scientist&loc_query=India",
                    headers=HEADERS, timeout=12)
        time.sleep(1)
    except requests.RequestException:
        pass

    print(f"\nFetching {len(JOBS)} Amazon Applied Scientist jobs...\n")
    results = []

    for job in JOBS:
        print(f"  [{job['id']}] {job['title']}...")
        r = fetch_job(session, job)
        results.append(r)
        print_job(r)
        time.sleep(2)

    # Summary
    ok = [r for r in results if not r["error"]]
    fail = [r for r in results if r["error"]]
    print(f"\n\n{'='*72}")
    print(f"Done: {len(ok)}/{len(JOBS)} fetched successfully.")
    if fail:
        print("Failed (run manually or open in browser):")
        for r in fail:
            print(f"  [{r['id']}] {r['title']}: {r['error']}")
            print(f"        {r['url']}")

    with open("jobs_result.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\nFull results saved → jobs_result.json")


if __name__ == "__main__":
    main()
