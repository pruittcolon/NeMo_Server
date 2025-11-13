"""Optional Gemma service submodules."""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

OPTIONAL_MODULES = ("email",)
__all__: list[str] = []


def _try_import(module_name: str) -> None:
    """Attempt to import a sibling module, logging if it is missing."""
    try:
        importlib.import_module(f".{module_name}", __name__)
    except ModuleNotFoundError as exc:
        # Only suppress the error when the missing module is the direct target.
        if exc.name and exc.name.endswith(module_name):
            logger.info("[modules] optional module '%s' not present", module_name)
            return
        raise
    __all__.append(module_name)


for _name in OPTIONAL_MODULES:
    _try_import(_name)
