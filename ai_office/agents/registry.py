"""Реестр агентов AI Office."""

from ai_office.agents.base import AgentConfig


class AgentRegistry:
    """Singleton registry for all agent configurations."""

    _instance = None
    _agents: dict[str, AgentConfig] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._agents = {}
        return cls._instance

    def register(self, config: AgentConfig) -> None:
        """Register an agent configuration."""
        self._agents[config.name.lower()] = config

    def unregister(self, name: str) -> None:
        """Unregister an agent by name.

        Args:
            name: Name of the agent to remove (case-insensitive)
        """
        key = name.lower()
        if key in self._agents:
            del self._agents[key]

    def get(self, name: str) -> AgentConfig | None:
        """Get agent config by name (case-insensitive)."""
        return self._agents.get(name.lower())

    def get_all(self) -> list[AgentConfig]:
        """Get all registered agent configs."""
        return list(self._agents.values())

    def get_names(self) -> list[str]:
        """Get all registered agent names."""
        return list(self._agents.keys())


# Global registry instance
registry = AgentRegistry()
