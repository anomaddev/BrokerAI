"""AI model registry stub for Researcher."""

from dataclasses import dataclass, field


@dataclass
class ModelEntry:
    name: str
    provider: str = "stub"
    enabled: bool = False


@dataclass
class ModelRegistry:
    models: list[ModelEntry] = field(default_factory=list)

    def list_enabled(self) -> list[ModelEntry]:
        return [m for m in self.models if m.enabled]


_registry = ModelRegistry()


def get_model_registry() -> ModelRegistry:
    return _registry
