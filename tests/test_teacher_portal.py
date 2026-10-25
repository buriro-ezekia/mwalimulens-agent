"""HTTP and browser-contract tests for the local MwalimuLens teacher portal."""
from __future__ import annotations

import http.client
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import pytest

from mwalimulens.teacher_portal import Case, TeacherPortal, make_handler, render_portal


class FakeState:
    def __init__(self):
        self.candidate = {
            'review_id': 'r1', 'status': 'pending_teacher_review',
            'claim': 'Improving fractions with mixed explanation',
            'supporting_evidence_ids': ['EV-004'],
            'counter_evidence_ids': ['EV-008'],
            'uncertainty': 'Open-ended explanation remains mixed.',
            'suggested_teacher_question': 'Can they explain an unfamiliar task?',
        }
        self.reviews = []
        self.updates = []
        self.calls = [{'tool_name':'flag_pattern_for_review','status':'success',
                       'timestamp':'2026-10-25T00:00:00+00:00'}]

    def review_candidate(self, review_id):
        assert review_id == 'r1'
        return dict(self.candidate)

    def pending_reviews(self):
        return (self.candidate,) if self.candidate['status'] == 'pending_teacher_review' else ()

    def teacher_reviews(self):
        return tuple(self.reviews)

    def profile_updates(self):
        return tuple(self.updates)

    def tool_calls(self):
        return tuple(self.calls)


class FakeService:
    def __init__(self, state):
        self.state = state

    def record_teacher_review(self, *, review_id, reviewer_id, decision, reason,
                              edited_claim=None):
        assert review_id == 'r1'
        assert reviewer_id == 'simulated-teacher-not-authenticated'
        if self.state.candidate['status'] != 'pending_teacher_review':
            raise ValueError('already resolved')
        self.state.candidate['status'] = {
            'approve':'approved_by_teacher',
            'edit':'edited_by_teacher',
            'reject':'rejected_by_teacher',
        }[decision]
        self.state.reviews.append({'decision':decision, 'reason':reason,
                                   'final_claim':edited_claim if decision=='edit' else
                                   None if decision=='reject' else self.state.candidate['claim']})
        if decision != 'reject':
            self.state.updates.append({'claim':edited_claim or self.state.candidate['claim']})
        self.state.calls.append({'tool_name':'record_teacher_review','status':'success',
                                 'timestamp':'2026-10-25T00:01:00+00:00'})


@pytest.fixture
def server(tmp_path):
    state = FakeState()
    evidence = [
        {'evidence_id':'EV-004','term_id':'2025-T2','evidence_type':'assessment',
         'score':0.78,'observation':None},
        {'evidence_id':'EV-008','term_id':'2025-T3','evidence_type':'observation',
         'score':None,'observation':'Needs independent explanation.'},
    ]
    case = Case(state, FakeService(state), state.candidate, evidence, tmp_path, 'seeded')
    portal = TeacherPortal(tmp_path, case)
    httpd = ThreadingHTTPServer(('127.0.0.1',0), make_handler(portal))
    thread = threading.Thread(target=httpd.serve_forever,daemon=True)
    thread.start()
    yield portal, httpd.server_port
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=3)


def request(port, method='GET', path='/', fields=None, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1',port,timeout=4)
    hdr = {'Host':f'127.0.0.1:{port}'}
    if headers:
        hdr.update(headers)
    body = None
    if fields is not None:
        body = urlencode(fields)
        hdr['Content-Type'] = 'application/x-www-form-urlencoded'
    conn.request(method,path,body=body,headers=hdr)
    resp = conn.getresponse()
    status = resp.status
    text = resp.read().decode('utf-8')
    result_headers = dict(resp.getheaders())
    conn.close()
    return status,text,result_headers


def preview(port, token, decision, reason='Supported by evidence', edited=''):
    return request(port,'POST','/review/preview',{
        'csrf':token,'decision':decision,'reason':reason,'edited_claim':edited,
    })


def nonce(html):
    import re
    m = re.search(r'name="nonce" value="([^"]+)"',html)
    assert m
    return m.group(1)


def test_teacher_facing_page_has_evidence_and_controls(server):
    portal,port=server
    status,html,headers=request(port)
    assert status==200
    assert 'Learner Progress Review' in html
    assert 'Awaiting teacher review' in html
    assert 'Counter-evidence' in html
    assert 'EV-008' in html
    assert 'Approve' in html and 'Revise' in html and 'Reject' in html
    assert 'Technical evidence and audit trail' in html
    assert 'not authenticated' in html
    assert 'no MCP client or model inference' in html
    assert headers['Cache-Control']=='no-store'
    assert 'form-action' in headers['Content-Security-Policy']
    assert 'frame-ancestors' in headers['Content-Security-Policy']


@pytest.mark.parametrize('decision,expected_updates',[
    ('approve',1),('edit',1),('reject',0)
])
def test_full_browser_decision_flow(server,decision,expected_updates):
    portal,port=server
    status,html,_=preview(port,portal.token,decision,
                          'Because EV-008 requires caution.',
                          'A revised provisional finding.' if decision=='edit' else '')
    assert status==200 and 'Confirm your decision' in html
    assert not portal.case.state.reviews
    token=nonce(html)
    status,html,_=request(port,'POST','/review/submit',{'csrf':portal.token,'nonce':token})
    assert status==200
    assert len(portal.case.state.reviews)==1
    assert len(portal.case.state.updates)==expected_updates
    assert 'Review recorded' in html
    assert 'Teacher' in html
    assert 'record_teacher_review' in html
    status,_,_=request(port,'POST','/review/submit',{'csrf':portal.token,'nonce':token})
    assert status==409
    assert len(portal.case.state.reviews)==1


def test_missing_csrf_rejected(server):
    portal,port=server
    status,_,_=request(port,'POST','/review/preview',{'decision':'approve','reason':'x'})
    assert status==403
    assert not portal.case.state.reviews


def test_host_and_origin_validation(server):
    portal,port=server
    status,_,_=request(port,headers={'Host':'evil.example'})
    assert status==403
    status,_,_=request(port,'POST','/review/preview',
                       {'csrf':portal.token,'decision':'approve','reason':'x'},
                       headers={'Origin':'https://evil.example'})
    assert status==403
    assert not portal.case.state.reviews


def test_invalid_edit_is_not_saved(server):
    portal,port=server
    status,_,_=preview(port,portal.token,'edit',edited='')
    assert status==400
    assert not portal.case.state.reviews


def test_blank_reason_is_not_saved(server):
    portal,port=server
    status,_,_=preview(port,portal.token,'approve',reason='   ')
    assert status==400
    assert not portal.case.state.reviews


def test_unconfirmed_review_does_not_mutate(server):
    portal,port=server
    status,html,_=preview(port,portal.token,'approve')
    assert status==200
    status,_,_=request(port)
    assert status==200
    assert len(portal.case.state.pending_reviews())==1
    assert not portal.case.state.reviews


def test_confirmation_content_is_escaped(server):
    portal,port=server
    status,html,_=preview(port,portal.token,'edit',
                          reason='<script>alert(1)</script>',
                          edited='<img src=x onerror=alert(1)>')
    assert status==200
    assert '&lt;script&gt;' in html
    assert '&lt;img src=x' in html
    assert '<script>alert' not in html
    assert '<img src=x' not in html


def test_reviewer_note_is_escaped_on_final_page(server):
    portal,port=server
    _,html,_=preview(port,portal.token,'approve',reason='<script>alert(1)</script>')
    _,final,_=request(port,'POST','/review/submit',
                      {'csrf':portal.token,'nonce':nonce(html)})
    assert '&lt;script&gt;' in final
    assert '<script>alert' not in final


def test_nonexistent_route_does_not_mutate(server):
    portal,port=server
    status,_,_=request(port,'POST','/anything',{'csrf':portal.token})
    assert status==404
    assert not portal.case.state.reviews


def test_case_start_rejects_unknown_mode(server):
    portal,port=server
    status,_,_=request(port,'POST','/case/start',{'csrf':portal.token,'mode':'real'})
    assert status==400
    assert portal.case.mode=='seeded'


def test_mcp_mode_is_labelled_truthfully(server):
    portal,port=server
    portal.case.mode='mcp'
    html=render_portal(portal.case,portal.token)
    assert 'Live MCP calls with a deterministic model; no Qwen inference' in html


def test_duplicate_form_field_rejected(server):
    portal,port=server
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=4)
    body=f'csrf={portal.token}&csrf={portal.token}&decision=approve&reason=Yes'
    conn.request('POST','/review/preview',body=body,
                 headers={'Content-Type':'application/x-www-form-urlencoded'})
    resp=conn.getresponse()
    assert resp.status==400
    resp.read();conn.close()


def test_large_payload_rejected(server):
    portal,port=server
    status,_,_=request(port,'POST','/review/preview',
                       {'csrf':portal.token,'decision':'approve','reason':'x'*9000})
    assert status==413


def test_confirmation_not_reusable_after_new_case(server,monkeypatch):
    portal,port=server
    _,html,_=preview(port,portal.token,'approve')
    previous=nonce(html)
    # Replace the case without running a real MCP or requiring project dependencies.
    def new_case(_root,_mode):
        state=FakeState()
        return Case(state,FakeService(state),state.candidate,portal.case.evidence,
                    Path('/tmp/another-case'),'seeded')
    import mwalimulens.teacher_portal as teacher_portal
    monkeypatch.setattr(teacher_portal,'create_case',new_case)
    status,_,_=request(port,'POST','/case/start',{'csrf':portal.token,'mode':'seeded'})
    assert status==200
    status,_,_=request(port,'POST','/review/submit',
                       {'csrf':portal.token,'nonce':previous})
    assert status==409


def test_committed_qwen_evidence_is_labelled_separately(tmp_path, monkeypatch):
    import json
    import mwalimulens.teacher_portal as teacher_portal

    folder = tmp_path / 'evidence'
    folder.mkdir()
    (folder / 'open_weights_run.json').write_text(
        json.dumps({'model':'qwen2.5:3b','status':'pass',
                    'audited_tool_names':['get_competency_evidence']}),
        encoding='utf-8',
    )
    monkeypatch.setattr(teacher_portal, 'ROOT', tmp_path)
    html = teacher_portal._model_validation()
    assert 'qwen2.5:3b' in html
    assert 'Recorded status:</b> pass' in html
    assert 'not a live model run' in html
