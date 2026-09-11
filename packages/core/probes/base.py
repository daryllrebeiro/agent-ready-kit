"""Abstract base class for LLM citation probers."""

from abc import ABC, abstractmethod

from packages.core.schemas import ProbeResult


class BaseProbe(ABC):
    """Base interface for all LLM citation probes."""

    def __init__(self, api_key: str | None = None, timeout_seconds: float = 15.0):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Machine-readable provider name."""

    @property
    def model_name(self) -> str:
        """Provider model identifier; override per provider. Used to populate
        ProbeResult.model_name so stored probe runs are self-describing."""
        return "unknown"

    @abstractmethod
    def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
        """Execute query against provider and return structured ProbeResult."""
