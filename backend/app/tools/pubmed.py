"""PubMed E-utilities access for guidelines and condition reviews (no API key required)."""

import xml.etree.ElementTree as ET

import requests
from crewai.tools import tool

from ..config import NCBI_API_KEY
from ..schemas import AgentName, Source
from ..sources import SourceCollector
from . import http

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GUIDELINE_TYPES = "(guideline[pt] OR practice guideline[pt] OR consensus development conference[pt])"
SYSTEMATIC_REVIEW_TYPES = "(systematic review[pt] OR meta-analysis[pt])"
ANY_REVIEW_TYPES = "(review[pt] OR systematic review[pt] OR meta-analysis[pt])"
EPIDEMIOLOGY = "(epidemiology[sh] OR prevalence[Title] OR incidence[Title] OR burden[Title])"
ABSTRACT_CHARS = 1500

# NCBI allows 3 req/s without a key and 10 req/s with one.
_limiter = http.RateLimiter(0.11 if NCBI_API_KEY else 0.35)


def _params(**kwargs) -> dict:
    params = {"db": "pubmed", **kwargs}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    return params


def _esearch(term: str, retmax: int, years: int) -> list[str]:
    resp = http.get(
        f"{EUTILS}/esearch.fcgi",
        _params(term=term, retmode="json", retmax=retmax, sort="relevance", datetype="pdat", reldate=years * 365),
        limiter=_limiter,
    )
    return resp.json()["esearchresult"]["idlist"]


def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _parse_article(article: ET.Element) -> dict:
    pmid = article.findtext(".//MedlineCitation/PMID", "")
    title = _text(article.find(".//ArticleTitle")) or _text(article.find(".//VernacularTitle"))
    year = (
        article.findtext(".//JournalIssue/PubDate/Year")
        or (article.findtext(".//JournalIssue/PubDate/MedlineDate") or "")[:4]
        or article.findtext(".//ArticleDate/Year")
    )
    abstract_parts = []
    for part in article.findall(".//Abstract/AbstractText"):
        label = part.get("Label")
        abstract_parts.append(f"{label}: {_text(part)}" if label else _text(part))
    return {
        "pmid": pmid,
        "title": title or "Untitled",
        "journal": article.findtext(".//Journal/ISOAbbreviation") or article.findtext(".//Journal/Title") or "",
        "year": int(year) if year and year.isdigit() else None,
        "publication_types": [p.text for p in article.findall(".//PublicationTypeList/PublicationType") if p.text],
        "abstract": " ".join(abstract_parts)[:ABSTRACT_CHARS],
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def _efetch(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    resp = http.get(f"{EUTILS}/efetch.fcgi", _params(id=",".join(pmids), retmode="xml"), limiter=_limiter)
    by_id = {a["pmid"]: a for a in map(_parse_article, ET.fromstring(resp.content).findall(".//PubmedArticle"))}
    return [by_id[p] for p in pmids if p in by_id]


def _condition_clause(condition: str, focus: str = "") -> str:
    """Require the condition in the title or as a major MeSH topic; loose matching returns off-topic papers."""
    cond = condition.replace('"', "").strip()
    clause = f'("{cond}"[Title] OR "{cond}"[MeSH Major Topic])'
    if focus.strip():
        clause += f" AND ({focus.strip()})"
    return clause


def search_guidelines(condition: str, focus: str = "", max_results: int = 8, years: int = 5) -> list[dict]:
    """Recent guidelines about the condition.

    Falls back to systematic reviews / meta-analyses when fewer than 3 guidelines exist.
    """
    clause = _condition_clause(condition, focus)
    pmids = _esearch(f"{clause} AND {GUIDELINE_TYPES}", max_results, years)
    if len(pmids) < 3:
        extra = _esearch(f"{clause} AND {SYSTEMATIC_REVIEW_TYPES}", max_results, years)
        pmids += [p for p in extra if p not in pmids][: max_results - len(pmids)]
    return _efetch(pmids)


def search_condition_reviews(condition: str, max_results: int = 6, years: int = 5) -> list[dict]:
    """Recent reviews covering the condition's epidemiology, burden, and background."""
    clause = _condition_clause(condition)
    return _efetch(_esearch(f"{clause} AND {EPIDEMIOLOGY} AND {ANY_REVIEW_TYPES}", max_results, years))


def _format_for_agent(articles: list[dict]) -> str:
    if not articles:
        return "No matching articles found on PubMed for this query."
    blocks = []
    for a in articles:
        blocks.append(
            f"[PMID {a['pmid']}] {a['title']} ({a['journal']}, {a['year']})\n"
            f"Types: {', '.join(a['publication_types'])}\n"
            f"Abstract: {a['abstract'] or 'n/a'}"
        )
    return "\n\n".join(blocks)


def make_guidelines_tool(collector: SourceCollector):
    @tool("search_guidelines")
    def search_guidelines_tool(condition: str, focus: str = "") -> str:
        """Search PubMed for clinical practice guidelines and consensus statements from the last 5 years
        about a medical condition. `condition` is the plain condition name (e.g. "multiple sclerosis").
        `focus` optionally narrows the search with extra keywords (e.g. "disease-modifying therapy").
        Returns PMID, title, journal, year, and abstract for each result. Only cite PMIDs returned here."""
        try:
            articles = search_guidelines(condition, focus)
        except (requests.RequestException, ET.ParseError) as exc:
            return f"ERROR: PubMed request failed ({exc}). Proceed without guideline citations."
        _record(collector, articles, "standard_of_care")
        return _format_for_agent(articles)

    return search_guidelines_tool


def make_condition_reviews_tool(collector: SourceCollector):
    @tool("search_condition_reviews")
    def search_condition_reviews_tool(condition: str) -> str:
        """Search PubMed for review articles from the last 5 years on a medical condition's epidemiology,
        burden, and background (e.g. "multiple sclerosis"). Returns PMID, title, journal, year, and abstract
        for each result. Only cite PMIDs returned here."""
        try:
            articles = search_condition_reviews(condition)
        except (requests.RequestException, ET.ParseError) as exc:
            return f"ERROR: PubMed request failed ({exc}). Proceed without citations."
        _record(collector, articles, "condition_overview")
        return _format_for_agent(articles)

    return search_condition_reviews_tool


def _record(collector: SourceCollector, articles: list[dict], agent: AgentName) -> None:
    for a in articles:
        collector.add(
            Source(
                type="pubmed",
                id=a["pmid"],
                title=a["title"],
                url=a["url"],
                agent=agent,
                meta={"journal": a["journal"], "year": a["year"], "publication_types": a["publication_types"]},
            )
        )
