"""Boot-time regression: the app's import chain must not require CrewAI.

This module deliberately imports **no** CrewAI (directly or transitively) at
collection time, so it still runs on a runtime where CrewAI is uninstalled or
unimportable — exactly the Streamlit Cloud (Python 3.14) failure mode this
guards against. It spawns a fresh subprocess that blocks ``crewai`` and imports
``graph.build`` (ui/app -> app.run_analysis -> graph.build -> crew.run_deep_dive),
asserting the startup chain succeeds and degrades only at deep-dive time.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT = textwrap.dedent(
    """
    import importlib.abc
    import sys

    class _BlockCrewAI(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name == "crewai" or name.startswith("crewai."):
                raise ImportError("crewai blocked for boot test")
            return None

    sys.meta_path.insert(0, _BlockCrewAI())

    # Sanity: crewai must genuinely be unimportable in this process.
    try:
        import crewai  # noqa: F401
    except ImportError:
        pass
    else:
        raise SystemExit("crewai import was not blocked")

    import graph.build  # the real application startup import chain
    assert hasattr(graph.build, "build_graph"), "build_graph missing"
    print("BOOT_OK")
    """
)


def test_startup_import_chain_succeeds_without_crewai() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"boot failed without crewai:\n{result.stderr}"
    assert "BOOT_OK" in result.stdout, result.stdout + result.stderr
