"""Модуль агентов: конфигурации и реестр."""

from ai_office.agents.registry import registry
from ai_office.agents.alice import alice_config
from ai_office.agents.sam import sam_config
from ai_office.agents.max import max_config
from ai_office.agents.eva import eva_config
from ai_office.agents.leo import leo_config
from ai_office.agents.nova import nova_config
from ai_office.agents.marketing import iris_config
from ai_office.agents.finance import oscar_config
from ai_office.agents.outbound_sales import outbound_sales_config

# Register all agents
registry.register(alice_config)
registry.register(sam_config)
registry.register(max_config)
registry.register(eva_config)
registry.register(leo_config)
registry.register(nova_config)
registry.register(iris_config)
registry.register(oscar_config)
registry.register(outbound_sales_config)
