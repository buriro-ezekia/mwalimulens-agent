"""Offline readiness gates: no external services are called in these tests."""
from __future__ import annotations

import json
import types
from pathlib import Path

from mwalimulens.nairobi_preflight import (
    check_prerequisites, inspect_mcp_case, run_preflight,
)


class State:
    def __init__(self, reviewed=False):
        self.reviewed=reviewed
    def tool_calls(self):
        return [
            {'tool_name':'get_competency_evidence','status':'success'},
            {'tool_name':'read_text_file','status':'success'},
            {'tool_name':'flag_pattern_for_review','status':'success'},
        ]
    def pending_reviews(self):
        return [] if self.reviewed else [{'status':'pending_teacher_review'}]
    def teacher_reviews(self):
        return [{'decision':'approve'}] if self.reviewed else []
    def profile_updates(self):
        return [{'claim':'x'}] if self.reviewed else []


def test_inspect_mcp_requires_real_calls_and_untouched_human_gate():
    case=types.SimpleNamespace(state=State(),report={'status':'pass'})
    assert all(inspect_mcp_case(case).values())
    case.state=State(reviewed=True)
    checks=inspect_mcp_case(case)
    assert not checks['pending_candidate']
    assert not checks['no_teacher_decision']
    assert not checks['no_profile_update']


def test_prerequisite_checks_detect_missing_files_and_node(tmp_path):
    checks=check_prerequisites(tmp_path,which=lambda _:None)
    assert checks['python_3_11_or_newer']
    assert not checks['node_available']
    assert not checks['synthetic_fixtures']
    assert not checks['borrowed_filesystem_mcp_installed']
    assert not checks['node_20_or_newer']


def test_skipped_checks_cannot_be_reported_as_pass(tmp_path,monkeypatch):
    import mwalimulens.nairobi_preflight as mod
    monkeypatch.setattr(mod,'check_prerequisites',lambda:{'all_present':True})
    result=run_preflight(output_root=tmp_path,run_mcp=False,check_model=False)
    assert result['status']=='incomplete_or_failed'
    assert result['mcp']['status']=='not_run'
    assert result['model']['status']=='not_checked'
    assert not result['manual_offline_connectivity_verified']
    assert Path(result['report_path']).exists()


def test_automated_mcp_checks_can_pass_without_offline_claim(tmp_path,monkeypatch):
    import mwalimulens.nairobi_preflight as mod
    import mwalimulens.teacher_portal as portal
    monkeypatch.setattr(mod,'check_prerequisites',lambda:{'all_present':True})
    monkeypatch.setattr(portal,'create_case',lambda root,mode:types.SimpleNamespace(
        state=State(),report={'status':'pass'},run_dir=root/'case-1'))
    result=run_preflight(output_root=tmp_path,run_mcp=True,check_model=False)
    assert result['status']=='automated_pass'
    assert result['mcp']['status']=='pass'
    assert not result['manual_offline_connectivity_verified']
    saved=json.loads(Path(result['report_path']).read_text())
    assert saved['mcp']['checks']['borrowed_filesystem_read']


def test_failed_mcp_keeps_report_and_does_not_claim_pass(tmp_path,monkeypatch):
    import mwalimulens.nairobi_preflight as mod
    import mwalimulens.teacher_portal as portal
    monkeypatch.setattr(mod,'check_prerequisites',lambda:{'all_present':True})
    def fail(_root,_mode):
        raise RuntimeError('MCP unavailable')
    monkeypatch.setattr(portal,'create_case',fail)
    result=run_preflight(output_root=tmp_path,run_mcp=True)
    assert result['status']=='incomplete_or_failed'
    assert result['mcp']['status']=='fail'
    assert Path(result['report_path']).exists()
