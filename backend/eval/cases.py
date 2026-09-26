from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    condition: str
    # The standard-of-care section must mention at least one of these (case-insensitive).
    soc_keywords: tuple[str, ...]


CASES = [
    EvalCase("Type 2 Diabetes", ("metformin", "SGLT2", "GLP-1")),
    EvalCase("Multiple Sclerosis", ("disease-modifying", "ocrelizumab", "interferon")),
    EvalCase("Non-Small Cell Lung Cancer", ("osimertinib", "pembrolizumab", "immunotherapy", "chemotherapy")),
    EvalCase("Rheumatoid Arthritis", ("methotrexate",)),
]
