"""Pure preflight checks; these do not claim Windows/OBS capture acceptance."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "record-hosted-review.py"
spec = importlib.util.spec_from_file_location("hosted_recording", SCRIPT)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8081",
        "http://localhost:8081",
        "http://example.org:8081",
        "http://127.0.0.1:8081@evil.org",
        "http://127.0.0.1:8081/?token=x",
        "http://127.0.0.1:8081/#x",
        "http://127.0.0.1:8081/other",
        "http://127.0.0.1",
    ],
)
def test_only_explicit_loopback_root(url):
    with pytest.raises(ValueError):
        launcher.local_url(url)


def test_loopback_url():
    assert launcher.local_url("http://127.0.0.1:8081/") == "http://127.0.0.1:8081"


def page_fixture(label="Authored demonstration", ident="demo-one", counts=None):
    code = SimpleNamespace(inner_text=lambda: ident)
    identity = SimpleNamespace(
        inner_text=lambda: label,
        locator=lambda _: SimpleNamespace(first=code),
    )
    metrics = SimpleNamespace(all_text_contents=lambda: counts or ["1", "0", "0"])
    return SimpleNamespace(
        locator=lambda selector: identity if selector == ".case-identity" else metrics
    )


def test_exact_identity_and_counts():
    assert launcher.assert_case(page_fixture(), ["1", "0", "0"]) == "demo-one"
    with pytest.raises(RuntimeError):
        launcher.assert_case(page_fixture(), ["0", "1", "1"])
    with pytest.raises(RuntimeError):
        launcher.assert_case(page_fixture(), ["1", "0", "0"], "demo-other")


@pytest.mark.parametrize(
    "label,ident",
    [
        ("Qwen result", "qwen-one"),
        ("Authored demonstration", "qwen-one"),
    ],
)
def test_refuses_non_authored_case(label, ident):
    with pytest.raises(RuntimeError):
        launcher.assert_case(page_fixture(label, ident), ["1", "0", "0"])


def test_windows_only_before_browser_or_obs(monkeypatch):
    monkeypatch.setattr("sys.argv", [str(SCRIPT)])
    if launcher.os.name == "nt":
        return
    with pytest.raises(RuntimeError, match="Windows laptop"):
        launcher.main()
