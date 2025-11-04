import importlib
import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "module_name",
    [
        "shared.config",
        "shared.security.service_auth",
        "shared.crypto.key_management",
        "shared.crypto.db_encryption",
    ],
)
def test_modules_import(module_name):
    importlib.import_module(module_name)
