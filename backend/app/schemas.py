from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["condition_overview", "standard_of_care", "emerging_treatments", "companies_institutions"]


# --- Agent 0: Condition Overview -----------------------------------------------------

class KeyFact(BaseModel):
    label: str = Field(description="Short label, e.g. 'US prevalence', 'Typical age of onset'.")
    value: str = Field(description="The figure or fact, e.g. '~1 million adults (2019)'.")
    pmid: str | None = Field(
        description="PMID from search_condition_reviews that supports this fact; null if from general knowledge."
    )


class ConditionOverview(BaseModel):
    summary: str = Field(description="3-5 sentence executive overview of the condition.")
    definition: str = Field(description="Plain-language description of what the condition is.")
    key_facts: list[KeyFact] = Field(description="4-6 headline figures: prevalence, incidence, demographics, burden.")
    subtypes: list[str] = Field(description="Main subtypes, stages, or classifications.")
    presentation_and_diagnosis: str = Field(description="Typical symptoms and how the condition is diagnosed.")
    health_system_impact: str = Field(description="Why it matters to a health system: utilization, cost, care settings.")


# --- Agent 1: Standard of Care -------------------------------------------------------

class TreatmentLine(BaseModel):
    setting: str = Field(description="Line of therapy or patient segment, e.g. 'First-line', 'Relapsing MS', 'Stage III'.")
    interventions: list[str] = Field(description="Drugs, procedures, or therapies used in this setting.")
    notes: str = Field(description="One or two sentences on when this is used and key considerations.")


class GuidelineCitation(BaseModel):
    pmid: str = Field(description="PubMed ID exactly as returned by the search_guidelines tool.")
    title: str
    issuing_body: str | None = Field(description="Society or organization that issued it, if known.")
    year: int | None


class StandardOfCare(BaseModel):
    summary: str = Field(description="3-5 sentence executive summary of how the condition is treated today.")
    treatment_approach: list[TreatmentLine]
    key_guidelines: list[GuidelineCitation]
    unmet_needs: list[str] = Field(description="Gaps or limitations in current care.")


# --- Agent 2: Emerging Treatments ----------------------------------------------------

class EmergingTherapy(BaseModel):
    name: str = Field(description="Investigational drug, device, or approach.")
    mechanism: str = Field(description="Mechanism of action or modality, in plain language.")
    phase: str = Field(description="Most advanced phase seen in the trial data, e.g. 'Phase 3'.")
    sponsor: str
    nct_ids: list[str] = Field(description="NCT IDs exactly as returned by the search_clinical_trials tool.")
    potential_impact: str = Field(description="Why this matters versus the current standard of care.")


class EmergingTreatments(BaseModel):
    summary: str = Field(description="3-5 sentence executive summary of the development pipeline.")
    therapies: list[EmergingTherapy]
    key_trends: list[str]


# --- Agent 3: Companies & Institutions -----------------------------------------------

class Organization(BaseModel):
    name: str = Field(description="Organization name; use the exact tool spelling when it appears in tool results.")
    category: Literal["industry", "academic", "government", "nonprofit"]
    focus: str = Field(description="What the organization is doing in this condition.")
    active_trial_count: int | None = Field(
        description="Trial count from the search_trial_sponsors tool; null if the organization was not in the tool results."
    )
    notable_programs: list[str]


class CompaniesInstitutions(BaseModel):
    summary: str = Field(description="3-5 sentence executive summary of the landscape.")
    companies: list[Organization]
    institutions: list[Organization]
    strategic_notes: list[str] = Field(description="Partnership or competitive implications for a health system.")


# --- API -----------------------------------------------------------------------------

class Source(BaseModel):
    type: Literal["pubmed", "trial", "sponsor"]
    id: str
    title: str
    url: str
    agent: AgentName
    meta: dict[str, Any] = Field(default_factory=dict)


class BriefingRequest(BaseModel):
    condition: str = Field(..., min_length=2, max_length=200, examples=["Multiple Sclerosis"])


class BriefingResponse(BaseModel):
    condition: str
    condition_overview: ConditionOverview
    standard_of_care: StandardOfCare
    emerging_treatments: EmergingTreatments
    companies_institutions: CompaniesInstitutions
    sources: list[Source]
    model: str
    generated_at: str
    duration_seconds: float
