import json
from dataclasses import replace
import httpx
import pytest
from downshift.core import Config, Gateway, DownshiftError, _label, redact, evaluate, synthetic_cases

C=Config('https://gateway.truefoundry.ai','https://control.example.test','test-token','incumbent/model','cheap/model','demo/virtual')

def test_labels_are_strict():
    assert _label('{"label":"billing"}')=='billing'
    assert _label('technical')=='technical'
    assert _label('{"label":"billing","x":1}') is None
    assert _label('financial') is None
    assert _label('') is None

@pytest.mark.parametrize('ticket', ['', 'x'*4001])
def test_invalid_ticket(ticket):
    g=Gateway(C,httpx.Client(transport=httpx.MockTransport(lambda r: None)))
    with pytest.raises(DownshiftError):g.complete(C.baseline_model,ticket)

def test_gateway_synthetic_request_and_response():
    def handler(r):
        assert r.url.path=='/v1/chat/completions'
        assert r.headers['x-tfy-metadata']==json.dumps({'route':'ticket-classify'})
        assert json.loads(r.content)['model']==C.candidate_model
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"label":"technical"}'}}], 'model':C.candidate_model, 'usage':{'total_tokens':37}},headers={'x-tfy-resolved-model':C.candidate_model})
    g=Gateway(C,httpx.Client(transport=httpx.MockTransport(handler)))
    assert g.complete(C.candidate_model,'app crash')['label']=='technical'

def test_gateway_http_failure_does_not_expose_token():
    g=Gateway(C,httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(401,json={'error':'bad'}))))
    with pytest.raises(DownshiftError,match='HTTP 401') as e:g.complete(C.baseline_model,'hi')
    assert C.token not in str(e.value)

def test_gateway_bad_response():
    g=Gateway(C,httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[]}))))
    with pytest.raises(DownshiftError,match='Malformed'):g.complete(C.baseline_model,'hi')

def test_spans_pagination_does_not_return_prompts():
    seen=[]
    def handler(r):
        payload=json.loads(r.content); seen.append(payload)
        if len(seen)==1:
            return httpx.Response(200,json={'data':[{'spanAttributes':{'tfy.request.metadata':{'route':'ticket-classify'},'tfy.input':'secret@example.com','tfy.model.metric.cost_in_usd':0.01,'tfy.model.fqn':'incumbent/model','tfy.span_type':'Model'}}], 'pagination':{'nextPageToken':'next'}})
        return httpx.Response(200,json={'data':[{'spanAttributes':{'tfy.request.metadata':{'route':'other'},'tfy.model.metric.cost_in_usd':0.12}}], 'pagination':{}})
    rows=Gateway(C,httpx.Client(transport=httpx.MockTransport(handler))).fetch_recent_spans('2026-09-26T00:00:00Z')
    assert len(rows)==1 and rows[0]['cost_usd']==.01 and 'secret' not in str(rows)
    assert seen[1]['pageToken']=='next'

def test_spans_repeating_cursor_fails():
    def handler(r):return httpx.Response(200,json={'data':[],'pagination':{'nextPageToken':'repeat'}})
    with pytest.raises(DownshiftError,match='Repeated'):
        Gateway(C,httpx.Client(transport=httpx.MockTransport(handler))).fetch_recent_spans('2026-09-26T00:00:00Z')

def test_evaluation_never_promotes_small_sample():
    class Fake:
        c=C
        def complete(self,model,ticket):
            return {'label': next(c['label'] for c in synthetic_cases() if c['ticket']==ticket)}
    r=evaluate(Fake())
    assert r['count']==8 and r['candidate_accuracy']==1 and r['eligible_for_canary'] is False

def test_regression_is_no_go():
    class Fake:
        c=C
        def complete(self,model,ticket):return {'label':'billing' if model==C.candidate_model else 'technical'}
    r=evaluate(Fake(),[{'ticket':'app issue','label':'technical'}]*20)
    assert r['candidate_regressions']==20 and not r['eligible_for_canary']

def test_redaction():
    assert 'sam@example.com' not in redact('Email sam@example.com and call +1 415-555-1212')
