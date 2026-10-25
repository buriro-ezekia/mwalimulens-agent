"""Repeatability aggregation tests; never call Ollama or real MCP servers."""
from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from mwalimulens.nairobi_reliability import (
    attempt_record, main, run_campaign, summarise,
)


def _attempt(index, status, duration, *, gate=False, failure=None):
    return {
        'attempt':index, 'status':status, 'duration_seconds':duration,
        'candidate_count':1 if status=='pass' else 0,
        'tool_failures':0 if status=='pass' else 1,
        'recovery_attempted':False, 'gate_violation':gate, 'failure':failure,
    }


def test_summary_counts_failures_and_does_not_hide_outliers():
    result=summarise([
        _attempt(1,'pass',10), _attempt(2,'fail',30,gate=True),
        _attempt(3,'pass',20),
    ],'qwen2.5:3b')
    assert result['status']=='complete'
    assert result['attempt_count']==3
    assert result['pass_count']==2
    assert result['fail_count']==1
    assert result['pass_rate']==0.6667
    assert result['human_gate_violation_count']==1
    assert result['duration_seconds_p50']==20
    assert result['duration_seconds_p95']==30
    assert len(result['attempts'])==3


def test_empty_summary_does_not_claim_success():
    result=summarise([],'qwen2.5:3b')
    assert result['status']=='not_run'
    assert result['pass_rate'] is None
    assert result['duration_seconds_p95'] is None


def test_attempt_record_detects_forbidden_teacher_review():
    report={
        'status':'fail','model':'qwen2.5:3b','pending_review_count':1,
        'teacher_review_count':1,'profile_update_count':1,
        'audited_tool_names':['record_teacher_review'],
        'tool_call_summary':[{'status':'error'}],
        'completion_recovery':{'attempted':True},
        'error':{'message':'Forbidden action'},
    }
    result=attempt_record(1,11.2,report,2,None)
    assert result['status']=='fail'
    assert result['gate_violation']
    assert result['tool_failures']==1
    assert result['recovery_attempted']
    assert result['failure']=='Forbidden action'


def test_timeout_attempt_is_retained():
    result=attempt_record(2,600,None,None,'Local model task exceeded 600 seconds')
    assert result['status']=='fail'
    assert result['failure'].startswith('Local model task exceeded')


@pytest.fixture
def stub_dependencies(monkeypatch):
    # This unit test environment does not contain PydanticAI or Ollama.
    agent=types.ModuleType('mwalimulens.agent')
    agent.__path__=[]
    ollama=types.ModuleType('mwalimulens.agent.ollama')
    challenge=types.ModuleType('mwalimulens.challenge_run')
    class Settings:
        def __init__(self,model_name):
            self.model_name=model_name
    ollama.OllamaSettings=Settings
    challenge.preflight_ollama=lambda settings: {'status':'pass','model':settings.model_name}
    monkeypatch.setitem(sys.modules,'mwalimulens.agent',agent)
    monkeypatch.setitem(sys.modules,'mwalimulens.agent.ollama',ollama)
    monkeypatch.setitem(sys.modules,'mwalimulens.challenge_run',challenge)


def test_blocked_preflight_preserves_summary_without_runs(tmp_path,stub_dependencies):
    def never(*_args,**_kwargs):
        pytest.fail('Should not run Qwen when preflight fails')
    result=run_campaign(runs=2,timeout=600,model='qwen2.5:3b',
                        output_root=tmp_path,
                        preflight=lambda _: {'status':'fail','error':'model absent'},
                        runner=never)
    assert result['status']=='blocked'
    assert result['attempt_count']==0
    saved=json.loads(Path(result['summary_path']).read_text())
    assert saved['preflight']['error']=='model absent'


def test_campaign_keeps_each_real_model_attempt_separate(tmp_path,stub_dependencies):
    paths=[]
    def runner(command,**kwargs):
        report_path=Path(command[command.index('--report')+1])
        state_path=Path(command[command.index('--state')+1])
        paths.append((report_path,state_path))
        passed=len(paths)!=2
        report={
            'status':'pass' if passed else 'fail',
            'model':'qwen2.5:3b',
            'pending_review_count':1 if passed else 0,
            'audited_tool_names':['get_competency_evidence'],
            'tool_call_summary':[{'status':'success'}],
            'teacher_review_count':0,'profile_update_count':0,
        }
        report_path.write_text(json.dumps(report))
        state_path.write_text('{}')
        return subprocess.CompletedProcess(command,0 if passed else 2,'done','')
    result=run_campaign(runs=3,timeout=600,model='qwen2.5:3b',
                        output_root=tmp_path,runner=runner)
    assert result['status']=='complete'
    assert result['pass_count']==2
    assert result['fail_count']==1
    assert len(set(p[0] for p in paths))==3
    assert len(set(p[1] for p in paths))==3
    assert Path(result['summary_path']).exists()
    assert result['attempts'][1]['status']=='fail'


def test_timeout_creates_failure_record(tmp_path,stub_dependencies):
    def timeout(*_args,**_kwargs):
        raise subprocess.TimeoutExpired(['python'],600)
    result=run_campaign(runs=1,timeout=600,model='qwen2.5:3b',
                        output_root=tmp_path,runner=timeout)
    assert result['fail_count']==1
    assert 'exceeded' in result['attempts'][0]['failure']
    assert Path(result['summary_path']).exists()


def test_dry_run_does_not_import_or_call_model(capsys):
    assert main(['--dry-run','--runs','2'])==0
    out=capsys.readouterr().out
    assert 'no Qwen calls' in out
    assert '2 isolated attempts' in out


@pytest.mark.parametrize('runs,timeout',[(0,600),(21,600),(1,10),(1,3601)])
def test_invalid_campaign_configuration_rejected(tmp_path,stub_dependencies,runs,timeout):
    with pytest.raises(ValueError):
        run_campaign(runs=runs,timeout=timeout,model='qwen2.5:3b',output_root=tmp_path)
