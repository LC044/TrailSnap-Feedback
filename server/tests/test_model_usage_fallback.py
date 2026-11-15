import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from requirement_platform import dsh
from requirement_platform.ai_guard import model_call_budget
from requirement_platform.collaboration_models import ModelRequestUsage
from requirement_platform.db import SessionLocal
from requirement_platform.main import app
from requirement_platform.model_usage import reported_usage
from test_z_collaboration import actor


def test_usage_reads_json_sse_cache_and_cumulative_counters():
    assert reported_usage(b'{"usage":{"input_tokens":100,"output_tokens":20}}') == (100,20)
    events = [
        {"type":"message_start","message":{"usage":{"input_tokens":100,"cache_read_input_tokens":50,"cache_creation_input_tokens":10,"output_tokens":0}}},
        {"type":"message_delta","usage":{"output_tokens":10}},
        {"type":"message_delta","usage":{"output_tokens":20}},
    ]
    assert reported_usage(b'\n'.join(b'data: '+json.dumps(e).encode() for e in events)) == (160,20)
    assert reported_usage(b'data: [DONE]\n') == (None,None)
    assert reported_usage(b'{"usage":{"input_tokens":-1,"output_tokens":true}}') == (None,None)
    assert reported_usage(b'{"message":"error"}') == (None,None)


def test_ordered_fallback_shares_budget_and_never_retries_local_quota(monkeypatch):
    calls = []
    def run(target, prompt, **kwargs):
        calls.append((target, model_call_budget.get()['remaining']))
        model_call_budget.get()['remaining'] -= 1
        if target != 'available-api': raise RuntimeError('Provider unavailable')
        return '行影集分析完成'
    monkeypatch.setattr(dsh, 'run_harness', run)
    assert dsh.run_with_fallback(['unavailable-model', 'available-api'], '{}') == '行影集分析完成'
    assert calls == [('unavailable-model',3),('available-api',2)]
    assert model_call_budget.get() is None
    calls.clear()
    def quota(target, *args, **kwargs):
        calls.append(target)
        raise HTTPException(429, 'Budget exhausted')
    monkeypatch.setattr(dsh, 'run_harness', quota)
    with pytest.raises(HTTPException): dsh.run_with_fallback(['first','second'], '{}')
    assert calls == ['first']
    assert model_call_budget.get() is None


def test_fallback_has_bounded_target_count(monkeypatch):
    calls = []
    def fail(target, *args, **kwargs): calls.append(target); raise RuntimeError('offline')
    monkeypatch.setattr(dsh, 'run_harness', fail)
    with pytest.raises(RuntimeError): dsh.run_with_fallback(list(range(10)), '{}')
    assert calls == [0,1,2]


def test_usage_is_manager_only_and_keeps_unreported_separate():
    with TestClient(app) as client:
        assert client.get('/api/admin/ai-model-usage').status_code == 401
        assert client.get('/api/admin/ai-model-usage', headers=actor()).status_code == 403
        model = uuid4().hex
        with SessionLocal() as db:
            db.add_all([
                ModelRequestUsage(connection_id='test-api', connection_name='API', model_id=model, model_name='test-model', reserved_tokens=3000, input_tokens=100, output_tokens=20, status='completed'),
                ModelRequestUsage(connection_id='test-api', connection_name='API', model_id=model, model_name='test-model', reserved_tokens=2000, status='failed'),
            ]);db.commit()
        result = client.get('/api/admin/ai-model-usage', headers=actor('admin'))
        assert result.status_code == 200
        row = next(r for r in result.json()['data']['models'] if r['model_id']==model)
        assert (row['requests'],row['failed'],row['unreported']) == (2,1,1)
        assert (row['input_tokens'],row['output_tokens'],row['today_tokens'],row['reserved_tokens']) == (100,20,120,5000)
