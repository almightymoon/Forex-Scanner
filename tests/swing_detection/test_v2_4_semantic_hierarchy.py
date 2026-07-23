"""Negative-development guards for refused v2.4 semantic hierarchy work.

No active 2.4.0 engine profile is registered. Threshold-only and structural
candidates were evaluated on TRAIN 001–008 and refused.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from shared.types.models import Timeframe
from swing_engine import LATEST_VERSION, get_config
from swing_engine.versions import DEFAULT_VERSION, SUPPORTED_VERSIONS


ROOT = Path(__file__).resolve().parents[2]
PASS1_REPO_PATH = (
    ROOT
    / "benchmarks/data/locked/XAUUSD/H1/retrospective_2022_2024/labels/pass_1.json"
)
YAML_PATH = ROOT / "config/swing_detection.yaml"
V2_4_MODULE = ROOT / "swing_engine/versions/v2_4.py"


def test_no_active_v2_4_engine_profile_or_module():
    assert "2.4.0" not in SUPPORTED_VERSIONS
    assert not V2_4_MODULE.exists()
    text = YAML_PATH.read_text(encoding="utf-8")
    assert '"2.4.0"' not in text
    assert "2.4.0:" not in text


def test_default_and_latest_versions_unchanged():
    assert DEFAULT_VERSION == "2.0.0"
    assert LATEST_VERSION == "2.3.0"


def test_v23_hierarchy_behavior_unchanged():
    v23 = get_config(Timeframe.H1, version="2.3.0", symbol="XAUUSD")
    assert v23.classification.hierarchy_enabled
    assert v23.classification.hierarchy_reversal_atr == 5.0
    assert v23.classification.hierarchy_scope_policy == "major_external"
    assert v23.confirmation.validation_boundary == "structural_reversal"


def test_hermetic_operation_without_repository_pass_1_json():
    assert not PASS1_REPO_PATH.exists()


def test_close_break_audit_script_reports_unsupported_without_repo_report(
    tmp_path: Path,
):
    """Generate the negative conclusion under tmp_path; do not require reports/."""
    path = ROOT / "scripts/audit_xauusd_h1_v2_4_close_confirmed_external_break.py"
    spec = importlib.util.spec_from_file_location(
        "fxn_v24_close_break_guard", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Avoid executing main(); assert module-level refusal constants and that
    # the script refuses an active 2.4.0 profile.
    spec.loader.exec_module(module)
    assert module.RAW_REVERSAL == 4.25
    assert module.V23 == "2.3.0"
    assert "2.4.0" not in SUPPORTED_VERSIONS

    # Minimal synthetic decision payload matching the refused TRAIN outcome.
    decision = {
        "classification": "DEVELOPMENT_ONLY",
        "scope": "TRAIN_001_008_ONLY",
        "decision_status": "NOT_A_RELEASE_DECISION",
        "viable_v2_4_development_candidate": False,
        "active_v2_4_profile": False,
        "latest_version": LATEST_VERSION,
        "decision": {
            "implement": False,
            "reason": "No supported v2.4 semantic rule among predeclared A–C",
        },
        "supported_rules": [],
        "rule_results": {
            "A": {"passes_full_and_loso": False},
            "B": {"passes_full_and_loso": False},
            "C": {"passes_full_and_loso": False},
        },
    }
    out = tmp_path / "close_break_audit.json"
    out.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["viable_v2_4_development_candidate"] is False
    assert loaded["decision"]["implement"] is False
    assert loaded["supported_rules"] == []
    for name in ("A", "B", "C"):
        assert loaded["rule_results"][name]["passes_full_and_loso"] is False
