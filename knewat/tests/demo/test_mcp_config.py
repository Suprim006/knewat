"""``knewat mcp-config`` and the committed ``knewat.mcp.json`` template (no database needed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knewat.cli import main
from knewat.demo.orchestrator import build_http_mcp_config

ROOT = Path(__file__).resolve().parents[3]


def _run(*argv: str) -> int:
    with pytest.raises(SystemExit) as e:
        main(list(argv))
    return e.value.code


def _out(capsys, *argv: str) -> dict:
    assert _run("mcp-config", *argv) == 0
    return json.loads(capsys.readouterr().out)


def test_stdio_config_points_at_this_checkouts_venv_script(capsys, monkeypatch):
    monkeypatch.setenv("FALKORDB_HOST", "127.0.0.1")
    monkeypatch.setenv("FALKORDB_PORT", "6367")
    cfg = _out(capsys)
    srv = cfg["mcpServers"]["knewat"]
    assert srv["args"] == ["--transport", "stdio", "--tenant", "demo"]
    assert Path(srv["command"]).name in ("knewat-mcp", "knewat-mcp.exe")
    assert srv["env"] == {"FALKORDB_HOST": "127.0.0.1", "FALKORDB_PORT": "6367"}
    # the script the config names really is the one next to this interpreter's environment
    assert Path(srv["command"]).exists()


def test_tenant_and_command_flags(capsys):
    srv = _out(capsys, "--tenant", "acme_2", "--mcp-command", "/opt/knewat-mcp")["mcpServers"]["knewat"]
    assert srv["args"][-1] == "acme_2" and srv["command"] == "/opt/knewat-mcp"


def test_invalid_tenant_is_rejected(capsys):
    with pytest.raises(ValueError, match="invalid tenant"):
        main(["mcp-config", "--tenant", "Bad Tenant"])


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://127.0.0.1:8765", "http://127.0.0.1:8765/mcp/t/acme"),
        ("http://127.0.0.1:8765/", "http://127.0.0.1:8765/mcp/t/acme"),
        ("https://knewat.example.org/mcp", "https://knewat.example.org/mcp/t/acme"),
        ("http://h:1/mcp/t/other", "http://h:1/mcp/t/other"),
    ],
)
def test_http_config_pins_the_tenant_in_the_path(capsys, url, expected):
    cfg = _out(capsys, "--http", url, "--tenant", "acme")
    assert cfg == {"mcpServers": {"knewat": {"type": "http", "url": expected}}}


def test_http_needs_an_http_url(capsys):
    with pytest.raises(SystemExit, match="http"):
        main(["mcp-config", "--http", "127.0.0.1:8765"])
    with pytest.raises(ValueError):
        build_http_mcp_config("ftp://x", "demo")


def test_out_writes_a_file(tmp_path, capsys):
    target = tmp_path / "mcp.json"
    assert _run("mcp-config", "--tenant", "demo", "--out", str(target)) == 0
    assert capsys.readouterr().out == ""
    assert json.loads(target.read_text(encoding="utf-8"))["mcpServers"]["knewat"]["args"][-1] == "demo"


def test_the_committed_template_is_portable():
    """knewat.mcp.json must not carry a path from the owner's machine; it works from the repo root."""
    text = (ROOT / "knewat.mcp.json").read_text(encoding="utf-8")
    cfg = json.loads(text)
    srv = cfg["mcpServers"]["knewat"]
    flat = [srv["command"], *srv["args"]]
    for part in flat:
        assert not Path(part).is_absolute() and ":" not in part and "\\" not in part, part
    assert "Change_folder" not in text and "ACER" not in text
    assert srv["command"] == "uv" and srv["args"][:3] == ["run", "--directory", "knewat"]
    assert srv["args"][-2:] == ["--tenant", "demo"]
    assert (
        ROOT / srv["args"][2] / "pyproject.toml"
    ).is_file()  # --directory knewat exists relative to the root
