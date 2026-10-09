import os
import shutil
from pathlib import Path

import pytest

from timemachine.core import Engine, atomic


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        fixture = item.funcargs.get("rustic_engine")
        if fixture:
            report.sections.append(("rustic test protocol", fixture[0].logs("test")))


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-base"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state-base"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    config = tmp_path / "configuration with spaces"
    state = tmp_path / "state"
    source = tmp_path / "source space"
    source.mkdir()
    (source / "file.txt").write_text("first version\n")
    (source / "subdir").mkdir()
    (source / "subdir" / "üñïcode 🕒.txt").write_text("nested\n")
    repo = tmp_path / "repository"
    atomic(
        config / "config.json",
        {"source": str(source), "destinations": [{"name": "test", "repository": str(repo)}]},
    )
    engine = Engine(config, state)
    engine.set_key("test", "test-only-password")
    return engine, source, repo


@pytest.fixture
def rustic_engine(configured):
    engine, source, repo = configured
    binary = os.environ.get("RUSTIC_TEST_BINARY") or shutil.which("rustic")
    if not binary:
        pytest.skip("Set RUSTIC_TEST_BINARY or install rustic for integration tests")
    engine.config["rustic_binary"] = str(Path(binary).absolute())
    engine.initialize("test")
    return engine, source, repo
