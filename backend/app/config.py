import os

# CrewAI routes "openrouter/<slug>" to its OpenAI-compatible client, which reads
# OPENROUTER_API_KEY from the environment. Slugs: https://openrouter.ai/models
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5").removeprefix("openrouter/")
LLM_MODEL = f"openrouter/{OPENROUTER_MODEL}"

# Optional: raises the PubMed E-utilities limit from 3 to 10 requests/second.
NCBI_API_KEY = os.environ.get("NCBI_API_KEY") or None

AGENT_MAX_ITER = int(os.environ.get("AGENT_MAX_ITER", "6"))
