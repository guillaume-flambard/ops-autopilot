"""CLI entrypoint tests (construction-order steps 1 + 7).

Run the argparse entrypoint headlessly: it must drive the graph through the
app/ use-case layer and print a final report.
"""

from __future__ import annotations

import os
import tempfile


def _cli(argv: list[str]) -> tuple[int, str]:
    from graph.cli import main

    rc = main(argv)
    return rc


def test_cli_run_preset_non_interactive(capsys) -> None:
    db = os.path.join(tempfile.mkdtemp(), "checkpoints.db")
    rc = _cli(["run", "--preset", "lumea", "--non-interactive", "--checkpoint-db", db])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Analyse 'Lumea'" in out
    assert "RAPPORT FINAL" in out
    assert "Priorite 1" in out


def test_cli_run_custom_brand(capsys) -> None:
    db = os.path.join(tempfile.mkdtemp(), "checkpoints.db")
    rc = _cli(
        [
            "run",
            "--name",
            "Acme",
            "--sector",
            "D2C",
            "--free-text",
            "Instagram DMs: ~50/day, 2 min each, highly repetitive.",
            "--non-interactive",
            "--checkpoint-db",
            db,
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "Analyse 'Acme'" in out
