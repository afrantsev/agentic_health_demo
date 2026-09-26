import re
from dataclasses import dataclass
from typing import Literal

from app.schemas import BriefingResponse

from .cases import EvalCase

NCT_RE = re.compile(r"NCT\d{8}")
REFUSAL_PHRASES = (
    "as an ai",
    "i cannot provide",
    "i can't provide",
    "i'm unable",
    "i am unable",
    "unable to access",
    "request failed",
)
ORG_SUFFIXES = {
    "inc", "llc", "ltd", "co", "corp", "corporation", "ag", "sa", "gmbh", "plc", "limited",
    "pharmaceuticals", "pharmaceutical", "pharma", "usa", "the",
}
MIN_SUMMARY_CHARS = 150
MAX_SECONDS = 300


@dataclass
class CheckResult:
    name: str
    severity: Literal["FAIL", "WARN"]
    passed: bool
    detail: str


def _norm_org(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return " ".join(w for w in words if w not in ORG_SUFFIXES)


def _org_matches(a: str, b: str) -> bool:
    a, b = _norm_org(a), _norm_org(b)
    if not a or not b:
        return False
    short, long_ = sorted((a, b), key=len)
    return short == long_ or (len(short) >= 4 and short in long_)


AGENT_SOURCE_TYPE = {
    "condition_overview": "pubmed",
    "standard_of_care": "pubmed",
    "emerging_treatments": "trial",
    "companies_institutions": "sponsor",
}


def _sections(b: BriefingResponse) -> dict:
    return {name: getattr(b, name) for name in AGENT_SOURCE_TYPE}


def _all_text(b: BriefingResponse) -> str:
    return " ".join(s.model_dump_json() for s in _sections(b).values())


def _retrieved(b: BriefingResponse, agent: str, type_: str) -> set[str]:
    return {s.id for s in b.sources if s.agent == agent and s.type == type_}


def check_structure(b: BriefingResponse) -> CheckResult:
    problems = []
    for name, section in _sections(b).items():
        if len(section.summary) < MIN_SUMMARY_CHARS:
            problems.append(f"{name}.summary < {MIN_SUMMARY_CHARS} chars")
    if not b.condition_overview.key_facts:
        problems.append("no key_facts")
    if not b.standard_of_care.treatment_approach:
        problems.append("no treatment_approach entries")
    if not b.emerging_treatments.therapies:
        problems.append("no emerging therapies")
    if not b.companies_institutions.companies:
        problems.append("no companies")
    if not b.companies_institutions.institutions:
        problems.append("no institutions")
    return CheckResult("sections_complete", "FAIL", not problems, "; ".join(problems) or "all sections populated")


def check_no_refusal(b: BriefingResponse) -> CheckResult:
    text = _all_text(b).lower()
    hits = [p for p in REFUSAL_PHRASES if p in text]
    return CheckResult("no_refusal_or_error_text", "FAIL", not hits, f"found {hits}" if hits else "clean")


def check_tools_used(b: BriefingResponse) -> CheckResult:
    counts = {agent: len(_retrieved(b, agent, type_)) for agent, type_ in AGENT_SOURCE_TYPE.items()}
    missing = [agent for agent, n in counts.items() if n == 0]
    return CheckResult("tools_used", "FAIL", not missing, f"sources per agent {counts}")


def check_pmids_grounded(b: BriefingResponse) -> CheckResult:
    # Each agent may only cite PMIDs its own tool returned (the agents run independently).
    cited = {
        "condition_overview": [f.pmid for f in b.condition_overview.key_facts if f.pmid],
        "standard_of_care": [g.pmid for g in b.standard_of_care.key_guidelines],
    }
    invented = [
        f"{agent}:{p}" for agent, pmids in cited.items() for p in pmids if p not in _retrieved(b, agent, "pubmed")
    ]
    total = sum(len(p) for p in cited.values())
    return CheckResult(
        "pmids_grounded", "FAIL", not invented,
        f"{total} cited, not retrieved: {invented}" if invented else f"{total} cited, all retrieved",
    )


def check_overview_facts_cited(b: BriefingResponse) -> CheckResult:
    facts = b.condition_overview.key_facts
    cited = sum(1 for f in facts if f.pmid)
    return CheckResult("overview_facts_cited", "WARN", cited >= 1, f"{cited}/{len(facts)} key facts cite a PMID")


def check_overview_facts_quantified(b: BriefingResponse) -> CheckResult:
    facts = b.condition_overview.key_facts
    vague = [f.label for f in facts if not re.search(r"\d", f.value)]
    return CheckResult(
        "overview_facts_quantified", "WARN", not vague,
        f"facts without a number: {vague}" if vague else f"all {len(facts)} facts are quantified",
    )


def check_guidelines_cited(b: BriefingResponse) -> CheckResult:
    n = len(b.standard_of_care.key_guidelines)
    return CheckResult("guidelines_cited", "WARN", n >= 1, f"{n} guideline(s) cited")


def check_nct_ids_grounded(b: BriefingResponse) -> CheckResult:
    retrieved = {s.id for s in b.sources if s.type == "trial"}
    retrieved |= {nct for s in b.sources if s.type == "sponsor" for nct in s.meta.get("nct_ids", [])}
    # Scan the whole briefing, so IDs mentioned in free text are held to the same standard.
    mentioned = set(NCT_RE.findall(_all_text(b)))
    malformed = [n for t in b.emerging_treatments.therapies for n in t.nct_ids if not NCT_RE.fullmatch(n)]
    invented = sorted(mentioned - retrieved)
    ok = not invented and not malformed
    detail = f"{len(mentioned)} NCT IDs mentioned"
    if invented:
        detail += f", not retrieved: {invented}"
    if malformed:
        detail += f", malformed: {malformed}"
    return CheckResult("nct_ids_grounded", "FAIL", ok, detail)


def check_therapies_have_trials(b: BriefingResponse) -> CheckResult:
    missing = [t.name for t in b.emerging_treatments.therapies if not t.nct_ids]
    return CheckResult("therapies_have_trials", "WARN", not missing, f"without NCT IDs: {missing}" if missing else "all linked")


def check_sponsors_grounded(b: BriefingResponse) -> list[CheckResult]:
    sponsors = [s for s in b.sources if s.type == "sponsor"]
    orgs = b.companies_institutions.companies + b.companies_institutions.institutions
    matched, false_claims, count_mismatch = [], [], []
    for org in orgs:
        source = next((s for s in sponsors if _org_matches(org.name, s.id)), None)
        if source:
            matched.append(org.name)
            if org.active_trial_count is not None and org.active_trial_count != source.meta.get("trial_count"):
                count_mismatch.append(f"{org.name}: {org.active_trial_count} vs {source.meta.get('trial_count')}")
        elif org.active_trial_count is not None:
            false_claims.append(org.name)
    return [
        CheckResult(
            "sponsor_counts_grounded", "FAIL", not false_claims,
            f"trial counts claimed without tool data: {false_claims}" if false_claims else "all claimed counts backed by tool",
        ),
        CheckResult("sponsors_matched", "FAIL", len(matched) >= 1, f"{len(matched)}/{len(orgs)} orgs match tool sponsors"),
        CheckResult("sponsors_matched_3plus", "WARN", len(matched) >= 3, f"{len(matched)} matched"),
        CheckResult(
            "sponsor_counts_accurate", "WARN", not count_mismatch,
            f"mismatches: {count_mismatch}" if count_mismatch else "counts match tool",
        ),
    ]


def check_soc_keywords(case: EvalCase, b: BriefingResponse) -> CheckResult:
    text = b.standard_of_care.model_dump_json().lower()
    hits = [k for k in case.soc_keywords if k.lower() in text]
    return CheckResult("soc_expected_keywords", "FAIL", bool(hits), f"found {hits} of {list(case.soc_keywords)}")


def check_latency(b: BriefingResponse) -> CheckResult:
    return CheckResult("latency", "WARN", b.duration_seconds < MAX_SECONDS, f"{b.duration_seconds}s (limit {MAX_SECONDS}s)")


def run_checks(case: EvalCase, b: BriefingResponse) -> list[CheckResult]:
    return [
        check_structure(b),
        check_no_refusal(b),
        check_tools_used(b),
        check_pmids_grounded(b),
        check_overview_facts_cited(b),
        check_overview_facts_quantified(b),
        check_guidelines_cited(b),
        check_nct_ids_grounded(b),
        check_therapies_have_trials(b),
        *check_sponsors_grounded(b),
        check_soc_keywords(case, b),
        check_latency(b),
    ]
