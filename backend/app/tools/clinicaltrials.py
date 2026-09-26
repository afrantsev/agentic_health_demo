"""ClinicalTrials.gov API v2 access (no API key required)."""

from collections import Counter, defaultdict
from urllib.parse import urlencode

import requests
from crewai.tools import tool

from ..schemas import Source
from ..sources import SourceCollector
from . import http

CTGOV = "https://clinicaltrials.gov/api/v2/studies"
ACTIVE_STATUSES = "RECRUITING,ACTIVE_NOT_RECRUITING,NOT_YET_RECRUITING,ENROLLING_BY_INVITATION"
SPONSOR_CATEGORY = {
    "INDUSTRY": "industry",
    "NIH": "government",
    "FED": "government",
    "OTHER_GOV": "government",
    "OTHER": "academic/other",
    "NETWORK": "network",
}

_limiter = http.RateLimiter(0.2)


def _fetch(params: dict) -> dict:
    return http.get(CTGOV, params, limiter=_limiter).json()


def _phase_label(phases: list[str]) -> str:
    labels = [p.replace("PHASE", "Phase ") for p in phases if p.startswith("PHASE")]
    return "/".join(labels) or "N/A"


def search_clinical_trials(condition: str, max_results: int = 15) -> list[dict]:
    """Active phase 2/3 interventional trials, ranked phase 3 first, then industry-sponsored."""
    data = _fetch(
        {
            "query.cond": condition,
            "filter.overallStatus": ACTIVE_STATUSES,
            "filter.advanced": "AREA[StudyType]INTERVENTIONAL AND (AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)",
            "pageSize": 60,
            "fields": "NCTId,BriefTitle,OverallStatus,Phase,LeadSponsorName,LeadSponsorClass,"
            "InterventionName,BriefSummary,StartDate",
        }
    )
    trials = []
    for study in data.get("studies", []):
        p = study.get("protocolSection", {})
        nct_id = p.get("identificationModule", {}).get("nctId")
        if not nct_id:
            continue
        sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
        phases = p.get("designModule", {}).get("phases") or []
        interventions = list(dict.fromkeys(
            i["name"]
            for i in p.get("armsInterventionsModule", {}).get("interventions", [])
            if i.get("name") and "placebo" not in i["name"].lower()
        ))
        trials.append(
            {
                "nct_id": nct_id,
                "title": p.get("identificationModule", {}).get("briefTitle", ""),
                "status": p.get("statusModule", {}).get("overallStatus", ""),
                "start_date": p.get("statusModule", {}).get("startDateStruct", {}).get("date"),
                "phase": _phase_label(phases),
                "sponsor": sponsor.get("name", "Unknown"),
                "sponsor_class": sponsor.get("class", "UNKNOWN"),
                "interventions": interventions,
                "summary": (p.get("descriptionModule", {}).get("briefSummary") or "").strip()[:400],
                "url": f"https://clinicaltrials.gov/study/{nct_id}",
            }
        )
    trials.sort(key=lambda t: ("Phase 3" not in t["phase"], t["sponsor_class"] != "INDUSTRY"))
    return trials[:max_results]


def search_trial_sponsors(condition: str, top_n: int = 12) -> dict:
    """Aggregate lead sponsors and collaborators across active interventional trials."""
    data = _fetch(
        {
            "query.cond": condition,
            "filter.overallStatus": ACTIVE_STATUSES,
            "filter.advanced": "AREA[StudyType]INTERVENTIONAL",
            "pageSize": 1000,
            "countTotal": "true",
            "fields": "NCTId,Phase,LeadSponsorName,LeadSponsorClass,CollaboratorName,CollaboratorClass",
        }
    )
    studies = data.get("studies", [])
    orgs: dict[str, dict] = defaultdict(
        lambda: {"class": "UNKNOWN", "lead": 0, "collaborator": 0, "nct_ids": [], "phases": Counter()}
    )
    for study in studies:
        p = study.get("protocolSection", {})
        nct_id = p.get("identificationModule", {}).get("nctId", "")
        phases = p.get("designModule", {}).get("phases") or ["NA"]
        module = p.get("sponsorCollaboratorsModule", {})
        roles = [("lead", module.get("leadSponsor", {}))] + [("collaborator", c) for c in module.get("collaborators", [])]
        for role, org in roles:
            name = (org.get("name") or "").strip()
            if not name:
                continue
            entry = orgs[name]
            entry["class"] = org.get("class", entry["class"])
            entry[role] += 1
            # Count distinct trials: an org can be listed more than once on the same trial.
            if nct_id not in entry["nct_ids"]:
                entry["nct_ids"].append(nct_id)
                entry["phases"].update(phases)

    ranked = sorted(orgs.items(), key=lambda kv: len(kv[1]["nct_ids"]), reverse=True)

    def summarize(items):
        return [
            {
                "name": name,
                "sponsor_class": o["class"],
                "category": SPONSOR_CATEGORY.get(o["class"], "other"),
                "trial_count": len(o["nct_ids"]),
                "lead_count": o["lead"],
                "collaborator_count": o["collaborator"],
                "phases": dict(o["phases"].most_common()),
                "nct_ids": o["nct_ids"],
            }
            for name, o in items[:top_n]
        ]

    return {
        "total_trials": data.get("totalCount", len(studies)),
        "analyzed_trials": len(studies),
        "industry": summarize([kv for kv in ranked if kv[1]["class"] == "INDUSTRY"]),
        "non_industry": summarize([kv for kv in ranked if kv[1]["class"] != "INDUSTRY"]),
    }


def _format_trials(trials: list[dict]) -> str:
    if not trials:
        return "No active phase 2/3 interventional trials found on ClinicalTrials.gov for this condition."
    return "\n\n".join(
        f"[{t['nct_id']}] {t['title']}\n"
        f"Phase: {t['phase']} | Status: {t['status']} | Start: {t['start_date']} | "
        f"Sponsor: {t['sponsor']} ({t['sponsor_class']})\n"
        f"Interventions: {', '.join(t['interventions']) or 'n/a'}\n"
        f"Summary: {t['summary']}"
        for t in trials
    )


def _format_sponsors(result: dict) -> str:
    def lines(orgs):
        return "\n".join(
            f"- {o['name']} [{o['sponsor_class']}]: {o['trial_count']} active trials "
            f"(lead {o['lead_count']}, collaborator {o['collaborator_count']}); "
            f"phases {o['phases']}; e.g. {', '.join(o['nct_ids'][:3])}"
            for o in orgs
        ) or "- none"

    return (
        f"Analyzed {result['analyzed_trials']} of {result['total_trials']} active interventional trials.\n\n"
        f"INDUSTRY (companies):\n{lines(result['industry'])}\n\n"
        f"NON-INDUSTRY (academic, government, networks):\n{lines(result['non_industry'])}"
    )


def make_trials_tool(collector: SourceCollector):
    @tool("search_clinical_trials")
    def search_clinical_trials_tool(condition: str) -> str:
        """Search ClinicalTrials.gov for active phase 2 and phase 3 interventional trials for a medical
        condition (e.g. "multiple sclerosis"). Returns NCT ID, title, phase, status, lead sponsor,
        interventions, and a summary for each trial. Only cite NCT IDs returned here."""
        try:
            trials = search_clinical_trials(condition)
        except requests.RequestException as exc:
            return f"ERROR: ClinicalTrials.gov request failed ({exc}). Proceed without trial citations."
        for t in trials:
            collector.add(
                Source(
                    type="trial",
                    id=t["nct_id"],
                    title=t["title"],
                    url=t["url"],
                    agent="emerging_treatments",
                    meta={
                        "phase": t["phase"],
                        "status": t["status"],
                        "sponsor": t["sponsor"],
                        "interventions": t["interventions"],
                    },
                )
            )
        return _format_trials(trials)

    return search_clinical_trials_tool


def make_sponsors_tool(collector: SourceCollector):
    @tool("search_trial_sponsors")
    def search_trial_sponsors_tool(condition: str) -> str:
        """Rank the companies and institutions running active interventional trials for a medical condition
        on ClinicalTrials.gov (e.g. "multiple sclerosis"), counting both lead-sponsor and collaborator roles.
        Returns industry and non-industry organizations with trial counts, phases, and example NCT IDs."""
        try:
            result = search_trial_sponsors(condition)
        except requests.RequestException as exc:
            return f"ERROR: ClinicalTrials.gov request failed ({exc}). Proceed using general knowledge only."
        for org in result["industry"] + result["non_industry"]:
            collector.add(
                Source(
                    type="sponsor",
                    id=org["name"],
                    title=org["name"],
                    # A search box holding only NCT IDs makes ClinicalTrials.gov list exactly those trials,
                    # so the link shows precisely what was counted (a name search also matches affiliates).
                    url="https://clinicaltrials.gov/search?" + urlencode({"term": ",".join(org["nct_ids"])}),
                    agent="companies_institutions",
                    meta={
                        **{k: org[k] for k in ("sponsor_class", "category", "trial_count", "lead_count", "collaborator_count", "nct_ids")},
                        "analyzed_trials": result["analyzed_trials"],
                        "total_trials": result["total_trials"],
                    },
                )
            )
        return _format_sponsors(result)

    return search_trial_sponsors_tool
