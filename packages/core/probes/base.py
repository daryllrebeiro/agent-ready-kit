"""Abstract base class for LLM citation probers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from packages.core.schemas import ProbeResult


class BaseProbe(ABC):
    """Base interface for all LLM citation probes."""

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: float = 15.0):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Machine-readable provider name."""
        pass

    @abstractmethod
    def probe(self, prompt: str, dry_run: bool = False) -> ProbeResult:
        """Execute query against provider and return structured ProbeResult."""
        pass
