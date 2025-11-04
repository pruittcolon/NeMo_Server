import pathlib
import pytest


@pytest.mark.security
def test_gitignore_has_secret_rules():
    gi = pathlib.Path(__file__).parents[2] / ".gitignore"
    content = gi.read_text().splitlines()
    # Ensure docker/secrets is ignored, with exceptions allowed for .gitkeep and README.md
    assert any(line.strip() == "docker/secrets/*" for line in content)
    assert any(line.strip() == "!docker/secrets/.gitkeep" for line in content)
    assert any(line.strip() == "!docker/secrets/README.md" for line in content)
