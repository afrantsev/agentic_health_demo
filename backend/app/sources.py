import threading

from .schemas import Source


class SourceCollector:
    """Request-scoped record of every item a tool returned to an agent.

    The API exposes this as `sources`, and the eval uses it to check that agents only
    cite IDs they actually retrieved.
    """

    def __init__(self) -> None:
        self._sources: dict[tuple[str, str, str], Source] = {}
        # CrewAI may execute parallel tool calls from one LLM turn concurrently.
        self._lock = threading.Lock()

    def add(self, source: Source) -> None:
        with self._lock:
            self._sources.setdefault((source.agent, source.type, source.id), source)

    def all(self) -> list[Source]:
        with self._lock:
            return list(self._sources.values())
