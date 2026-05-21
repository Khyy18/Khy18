"""Root conftest: make this directory importable as 'kindergarten_accountant_bot' package."""
import sys
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent

# Add project root to sys.path
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Register this directory as 'kindergarten_accountant_bot' package
if "kindergarten_accountant_bot" not in sys.modules:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "kindergarten_accountant_bot",
        str(_PROJECT_ROOT / "__init__.py"),
        submodule_search_locations=[str(_PROJECT_ROOT)],
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__path__ = [str(_PROJECT_ROOT)]
    sys.modules["kindergarten_accountant_bot"] = mod
    spec.loader.exec_module(mod)
