from pathlib import Path
import re


def test_runtime_code_avoids_python310_only_optional_union_annotations():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    pattern = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])?\s*\|\s*None\b|\bNone\s*\|\s*[A-Za-z_]")
    for package in ("rca_app", "rca_server"):
        for path in (root / package).glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if pattern.search(text):
                offenders.append(f"{package}/{path.name}")
    assert offenders == []
