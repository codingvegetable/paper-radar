#!/usr/bin/env python3
"""Fetch recent robotics papers from arXiv and write a static JSON feed.

The script is dependency-free so it can run in GitHub Actions or a local cron job.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

ARXIV_APIS = ("https://export.arxiv.org/api/query", "http://export.arxiv.org/api/query")
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


@dataclass(frozen=True)
class CategoryConfig:
    label: str
    query_terms: Tuple[str, ...]
    keywords: Tuple[str, ...]
    color: str


CATEGORIES: Dict[str, CategoryConfig] = {
    "manipulation": CategoryConfig(
        label="Manipulation",
        query_terms=(
            "robot manipulation",
            "dexterous manipulation",
            "grasping",
            "contact-rich manipulation",
            "mobile manipulation",
            "bimanual manipulation",
        ),
        keywords=(
            "manipulation",
            "dexterous",
            "grasping",
            "gripper",
            "in-hand",
            "bimanual",
            "contact-rich",
            "tactile",
            "affordance",
        ),
        color="#e56f3d",
    ),
    "vla": CategoryConfig(
        label="Vision-Language-Action",
        query_terms=(
            "vision language action",
            "vision-language-action",
            "VLA model",
            "robot foundation model",
            "language conditioned policy",
            "multimodal robot policy",
        ),
        keywords=(
            "vision-language-action",
            "vla",
            "vision language",
            "language-conditioned",
            "multimodal",
            "foundation model",
            "large language model",
            "robot policy",
            "imitation learning",
        ),
        color="#256d85",
    ),
    "uav": CategoryConfig(
        label="UAV",
        query_terms=(
            "UAV",
            "unmanned aerial vehicle",
            "aerial robot",
            "drone navigation",
            "quadrotor",
            "aerial manipulation",
        ),
        keywords=(
            "uav",
            "drone",
            "quadrotor",
            "aerial",
            "flight",
            "navigation",
            "slam",
            "trajectory planning",
            "swarm",
        ),
        color="#4f8f3a",
    ),
    "humanoid": CategoryConfig(
        label="Humanoid",
        query_terms=(
            "humanoid robot",
            "bipedal locomotion",
            "whole-body control",
            "legged humanoid",
            "humanoid manipulation",
            "humanoid navigation",
        ),
        keywords=(
            "humanoid",
            "bipedal",
            "whole-body",
            "locomotion",
            "gait",
            "legged",
            "balance",
            "motion retargeting",
            "teleoperation",
        ),
        color="#8e5a2f",
    ),
}

COMMON_KEYWORDS = (
    "reinforcement learning",
    "imitation learning",
    "diffusion policy",
    "world model",
    "sim-to-real",
    "embodied ai",
    "robot learning",
    "planning",
    "control",
    "perception",
    "semantic mapping",
    "3d reconstruction",
    "visual servoing",
    "transformer",
    "dataset",
    "benchmark",
)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def parse_arxiv_date(value: str) -> Optional[dt.datetime]:
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def build_query(terms: Iterable[str]) -> str:
    term_query = " OR ".join(f'all:"{term}"' for term in terms)
    category_query = " OR ".join(("cat:cs.RO", "cat:cs.AI", "cat:cs.CV", "cat:cs.LG", "cat:eess.SY"))
    return f"({term_query}) AND ({category_query})"


def fetch_category(category_key: str, config: CategoryConfig, per_category: int, retries: int) -> List[dict]:
    params = {
        "search_query": build_query(config.query_terms),
        "start": "0",
        "max_results": str(per_category),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    last_error: Optional[BaseException] = None
    for api_url in ARXIV_APIS:
        url = f"{api_url}?{urllib.parse.urlencode(params)}"
        for attempt in range(1, retries + 1):
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "paper-radar/1.0 (daily arxiv digest; contact: local-user)",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    xml_data = response.read()

                root = ET.fromstring(xml_data)
                return [parse_entry(entry, category_key) for entry in root.findall("atom:entry", ATOM_NS)]
            except (OSError, TimeoutError, ET.ParseError) as error:
                last_error = error
                if attempt < retries:
                    time.sleep(min(6 * attempt, 18))

    raise RuntimeError(f"failed to fetch {config.label}: {last_error}")


def parse_entry(entry: ET.Element, source_category: str) -> dict:
    entry_id = normalize_space(entry.findtext("atom:id", default="", namespaces=ATOM_NS))
    arxiv_id = entry_id.rstrip("/").split("/")[-1]
    title = normalize_space(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
    abstract = normalize_space(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
    published = normalize_space(entry.findtext("atom:published", default="", namespaces=ATOM_NS))
    updated = normalize_space(entry.findtext("atom:updated", default="", namespaces=ATOM_NS))
    authors = [normalize_space(author.findtext("atom:name", default="", namespaces=ATOM_NS)) for author in entry.findall("atom:author", ATOM_NS)]
    arxiv_categories = [cat.attrib.get("term", "") for cat in entry.findall("atom:category", ATOM_NS) if cat.attrib.get("term")]

    pdf_url = ""
    abstract_url = entry_id
    for link in entry.findall("atom:link", ATOM_NS):
        rel = link.attrib.get("rel", "")
        title_attr = link.attrib.get("title", "")
        href = link.attrib.get("href", "")
        if title_attr == "pdf" or rel == "related":
            pdf_url = href
        elif rel == "alternate" and href:
            abstract_url = href

    return {
        "id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "published": published,
        "updated": updated,
        "arxiv_categories": arxiv_categories,
        "source_categories": [source_category],
        "links": {"abstract": abstract_url, "pdf": pdf_url},
    }


def score_categories(paper: dict) -> Dict[str, int]:
    text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
    scores: Dict[str, int] = {}
    for key, config in CATEGORIES.items():
        score = 0
        if key in paper.get("source_categories", []):
            score += 3
        for term in (*config.query_terms, *config.keywords):
            if term.lower() in text:
                score += 2 if len(term) > 5 else 1
        if score:
            scores[key] = score
    return scores


def generate_keywords(paper: dict, category_keys: List[str]) -> List[str]:
    text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
    candidates: List[str] = []
    for key in category_keys:
        candidates.extend(CATEGORIES[key].keywords)
    candidates.extend(COMMON_KEYWORDS)

    found: List[str] = []
    seen = set()
    for term in candidates:
        if term.lower() in text and term.lower() not in seen:
            found.append(term)
            seen.add(term.lower())
        if len(found) >= 8:
            break

    for cat in paper.get("arxiv_categories", []):
        if len(found) >= 8:
            break
        if cat not in seen:
            found.append(cat)
            seen.add(cat)
    return found


def merge_papers(existing: Dict[str, dict], incoming: List[dict]) -> None:
    for paper in incoming:
        paper_id = paper["id"]
        if paper_id in existing:
            known = set(existing[paper_id].setdefault("source_categories", []))
            known.update(paper.get("source_categories", []))
            existing[paper_id]["source_categories"] = sorted(known)
        else:
            existing[paper_id] = paper


def enrich_papers(papers: List[dict]) -> List[dict]:
    enriched = []
    for paper in papers:
        scores = score_categories(paper)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        category_keys = [key for key, _ in ranked[:3]] or ["manipulation"]
        primary = category_keys[0]
        paper["primary_category"] = primary
        paper["categories"] = [CATEGORIES[key].label for key in category_keys]
        paper["category_keys"] = category_keys
        paper["category_color"] = CATEGORIES[primary].color
        paper["keywords"] = generate_keywords(paper, category_keys)
        enriched.append(paper)
    return enriched


def filter_recent(papers: List[dict], days: int) -> List[dict]:
    if days <= 0:
        return papers
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    recent = []
    for paper in papers:
        published = parse_arxiv_date(paper.get("published", ""))
        if published is None or published >= cutoff:
            recent.append(paper)
    return recent


def sort_key(paper: dict) -> str:
    return paper.get("published") or paper.get("updated") or ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch categorized robotics papers from arXiv.")
    parser.add_argument("--output", default="data/papers.json", help="JSON file to write")
    parser.add_argument("--per-category", type=int, default=40, help="arXiv records to fetch for each category")
    parser.add_argument("--days", type=int, default=14, help="Keep papers published in the last N days; 0 keeps all fetched papers")
    parser.add_argument("--limit", type=int, default=120, help="Maximum papers to keep in the output")
    parser.add_argument("--sleep", type=float, default=3.1, help="Seconds between arXiv API requests")
    parser.add_argument("--retries", type=int, default=2, help="Retries per arXiv endpoint")
    args = parser.parse_args()

    output = Path(args.output)
    papers_by_id: Dict[str, dict] = {}

    for index, (key, config) in enumerate(CATEGORIES.items()):
        print(f"Fetching {config.label}...", flush=True)
        try:
            incoming = fetch_category(key, config, args.per_category, args.retries)
        except RuntimeError as error:
            print(error, flush=True)
            continue
        merge_papers(papers_by_id, incoming)
        if index < len(CATEGORIES) - 1:
            time.sleep(args.sleep)

    if not papers_by_id:
        raise SystemExit("No papers were fetched. Check network access or arXiv API availability.")

    papers = enrich_papers(list(papers_by_id.values()))
    papers = filter_recent(papers, args.days)
    papers = sorted(papers, key=sort_key, reverse=True)[: args.limit]

    payload = {
        "updated_at": utc_now_iso(),
        "source": "arXiv API",
        "category_labels": {key: cfg.label for key, cfg in CATEGORIES.items()},
        "papers": papers,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(papers)} papers to {output}", flush=True)


if __name__ == "__main__":
    main()
