"""Compat-shim для импорта `strategy`.

Исторический торговый цикл v1 (main.py) обращается к именам
`evaluate_signal`, `compute_breakeven`, `compute_trailing_tp`,
`position_size` и помощникам индикаторов через `import strategy`.

FEAT-001: этот модуль временно переэкспортирует всё из strategy_v1.
FEAT-002: введёт новый strategy_v2 (Donchian-пробой + трендовый фильтр +
vol-targeting) и перецелит shim на `from strategy_v2 import *`.
До тех пор держим стрелку на v1, чтобы рабочее дерево компилировалось.
"""

from strategy_v1 import *  # noqa: F401,F403
