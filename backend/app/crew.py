import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from crewai import LLM, Agent, Crew, Process, Task

from .config import AGENT_MAX_ITER, LLM_MODEL, OPENROUTER_MODEL
from .schemas import BriefingResponse, CompaniesInstitutions, ConditionOverview, EmergingTreatments, StandardOfCare
from .sources import SourceCollector
from .tools.clinicaltrials import make_sponsors_tool, make_trials_tool
from .tools.pubmed import make_condition_reviews_tool, make_guidelines_tool

STYLE = (
    "Write for a health system strategy team (executives, not clinicians): concise, factual, "
    "no marketing language, no patient-specific medical advice."
)


class BriefingError(RuntimeError):
    pass


def _agent(role: str, goal: str, backstory: str, tools: list) -> Agent:
    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        tools=tools,
        # One LLM instance per agent: CrewAI sets per-agent state (e.g. stop words) on it,
        # so sharing one across concurrently running agents is unsafe.
        llm=LLM(model=LLM_MODEL, temperature=0.2),
        max_iter=AGENT_MAX_ITER,
        allow_delegation=False,
        verbose=False,
    )


def build_tasks(collector: SourceCollector) -> dict[str, Task]:
    overview_agent = _agent(
        role="Condition Overview Analyst",
        goal="Explain what {condition} is, who it affects, and why it matters to a health system.",
        backstory=(
            "You are a clinical epidemiologist who briefs health system executives. You anchor headline "
            "figures in recent peer-reviewed reviews and say plainly when a figure comes from general knowledge."
        ),
        tools=[make_condition_reviews_tool(collector)],
    )
    soc_agent = _agent(
        role="Standard of Care Analyst",
        goal="Summarize how {condition} is treated today, grounded in current clinical practice guidelines.",
        backstory=(
            "You are a clinical evidence analyst who turns society guidelines into clear briefings. "
            "You only describe care that is established today, and you cite guidelines you have verified on PubMed."
        ),
        tools=[make_guidelines_tool(collector)],
    )
    emerging_agent = _agent(
        role="Emerging Treatments Analyst",
        goal="Identify the most strategically significant investigational therapies for {condition}.",
        backstory=(
            "You are a biopharma pipeline analyst. You ground every claim in live ClinicalTrials.gov data "
            "and cite NCT IDs so each claim can be verified."
        ),
        tools=[make_trials_tool(collector)],
    )
    companies_agent = _agent(
        role="Industry & Institutions Analyst",
        goal="Map the companies and institutions that matter most in {condition} care and research.",
        backstory=(
            "You are a competitive-landscape analyst for health system leadership. You combine trial-sponsor "
            "data with your knowledge of market leaders to show who to watch or partner with."
        ),
        tools=[make_sponsors_tool(collector)],
    )

    return {
        "condition_overview": Task(
            description=(
                "Produce the 'Condition Overview' section of a briefing on {condition}.\n"
                "1. Call search_condition_reviews with condition '{condition}'.\n"
                "2. Describe what {condition} is, its main subtypes or stages, typical presentation, and how it "
                "is diagnosed.\n"
                "3. key_facts: 4-6 headline figures (prevalence, incidence, typical age of onset, mortality, "
                "annual cost). Every value MUST contain a specific number, in forms like 'about X million people "
                "worldwide (year)', 'X-Y years', or 'about $X per patient per year'. Always include prevalence. "
                "If a tool abstract states the number, set pmid to that article's PMID, copied exactly. If the "
                "abstracts only describe a trend or omit the number, give the widely cited estimate from your own "
                "knowledge and set pmid to null: a specific uncited number is better than a vague cited statement. "
                "Never invent a PMID or attach one to a number that article does not state.\n"
                "4. Explain the impact on a health system: utilization, cost, and care settings involved.\n" + STYLE
            ),
            expected_output=(
                "ConditionOverview JSON: summary, definition, key_facts (tool PMIDs or null), subtypes, "
                "presentation_and_diagnosis, health_system_impact."
            ),
            agent=overview_agent,
            output_pydantic=ConditionOverview,
        ),
        "standard_of_care": Task(
            description=(
                "Produce the 'Current Standard of Care' section of a briefing on {condition}.\n"
                "1. Call search_guidelines with condition '{condition}'. You may call it once more with a `focus` "
                "(e.g. a treatment class) if the results are thin or off-topic.\n"
                "2. Using those guidelines plus your clinical knowledge, describe the treatment settings or lines "
                "of therapy and the main interventions in each.\n"
                "3. key_guidelines: include only tool results that are actually about {condition}, with the PMID "
                "copied exactly. Never invent a PMID; return an empty list if none are relevant.\n"
                "4. List the main unmet needs.\n" + STYLE
            ),
            expected_output="StandardOfCare JSON: summary, treatment_approach, key_guidelines (tool PMIDs only), unmet_needs.",
            agent=soc_agent,
            output_pydantic=StandardOfCare,
        ),
        "emerging_treatments": Task(
            description=(
                "Produce the 'Emerging Treatments in Development' section of a briefing on {condition}.\n"
                "1. Call search_clinical_trials with condition '{condition}'.\n"
                "2. Pick the 4-8 most strategically significant investigational therapies (favor phase 3, novel "
                "mechanisms, and industry programs). Group multiple trials of the same therapy into one entry.\n"
                "3. nct_ids must be copied exactly from the tool results. Never invent an NCT ID. Skip therapies "
                "that are already standard of care unless they are being tested for a new use.\n"
                "4. Summarize the key pipeline trends.\n" + STYLE
            ),
            expected_output="EmergingTreatments JSON: summary, therapies (tool NCT IDs only), key_trends.",
            agent=emerging_agent,
            output_pydantic=EmergingTreatments,
        ),
        "companies_institutions": Task(
            description=(
                "Produce the 'Key Companies & Institutions' section of a briefing on {condition}.\n"
                "1. Call search_trial_sponsors with condition '{condition}'.\n"
                "2. Select the 5-8 most important companies and 4-6 most important institutions (academic medical "
                "centers, government bodies, research networks, foundations). Use the tool's trial counts and "
                "phases as evidence, plus your knowledge of approved-product market leaders.\n"
                "3. For organizations in the tool results, use the tool's exact name spelling and set "
                "active_trial_count to its trial_count. For organizations added from your own knowledge, set "
                "active_trial_count to null.\n"
                "4. Add strategic notes on partnership, trial-site, or competitive implications for a health "
                "system.\n" + STYLE
            ),
            expected_output="CompaniesInstitutions JSON: summary, companies, institutions, strategic_notes.",
            agent=companies_agent,
            output_pydantic=CompaniesInstitutions,
        ),
    }


def _run_task(task: Task, condition: str):
    crew = Crew(agents=[task.agent], tasks=[task], process=Process.sequential, verbose=False)
    return crew.kickoff(inputs={"condition": condition}).pydantic


def run_briefing(condition: str) -> BriefingResponse:
    start = time.monotonic()
    collector = SourceCollector()
    tasks = build_tasks(collector)

    # The agents are independent, so each runs as its own single-agent crew in parallel.
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {name: pool.submit(_run_task, task, condition) for name, task in tasks.items()}
        sections = {name: future.result() for name, future in futures.items()}

    for name, parsed in sections.items():
        if parsed is None:
            raise BriefingError(f"The {name} agent did not return valid structured JSON.")

    return BriefingResponse(
        condition=condition,
        **sections,
        sources=collector.all(),
        model=OPENROUTER_MODEL,
        generated_at=datetime.now(timezone.utc).isoformat(),
        duration_seconds=round(time.monotonic() - start, 1),
    )
