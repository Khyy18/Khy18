"""Root conftest for zenith_crypto_trading tests."""
import sys
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PROJECT_ROOT.parent
_ARB_DIR = _REPO_ROOT / "02_sports_betting_arbitrage"

# Change working directory to project root so test_deploy_scripts.py relative paths work
os.chdir(str(_PROJECT_ROOT))

# Add arbitrage project to sys.path
if str(_ARB_DIR) not in sys.path:
    sys.path.insert(0, str(_ARB_DIR))

# Register 02_sports_betting_arbitrage as 'arbitrage' package
if "arbitrage" not in sys.modules:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "arbitrage",
        str(_ARB_DIR / "__init__.py"),
        submodule_search_locations=[str(_ARB_DIR)],
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__path__ = [str(_ARB_DIR)]
    sys.modules["arbitrage"] = mod
    spec.loader.exec_module(mod)
