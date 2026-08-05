from __future__ import annotations

from types import SimpleNamespace


def test_product_research_script_cli_prints_report(monkeypatch, capsys):
    from scripts import product_research_script

    class FakeWorkflow:
        def run(self, intent):
            assert intent.owner_user_id == "42"
            return SimpleNamespace(to_report=lambda: "Run ID: run-1\nStatus: completed\n")

    monkeypatch.setattr(product_research_script, "build_workflow", lambda: FakeWorkflow())

    assert product_research_script.main(
        ["--owner", "42", "--message", "crawl ngành bàn phím, giá 200k-500k"]
    ) == 0
    assert "Status: completed" in capsys.readouterr().out