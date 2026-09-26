"""Real local HTTP E2E, clearly a mock provider (not a live TrueFoundry test)."""
from threading import Thread
from http.server import ThreadingHTTPServer
from downshift.demo_gateway import MockGateway
from downshift.core import Config,Gateway,evaluate,synthetic_cases

def test_full_mock_http_flow():
    MockGateway.traces=[]
    srv=ThreadingHTTPServer(('127.0.0.1',0),MockGateway)
    thread=Thread(target=srv.serve_forever,daemon=True)
    thread.start()
    try:
        root=f'http://127.0.0.1:{srv.server_port}'
        c=Config(root,root,'mock-token','demo/incumbent','demo/cheap','demo/virtual')
        g=Gateway(c)
        result=evaluate(g,synthetic_cases())
        assert result['count']==28
        assert result['baseline_accuracy']==1
        assert result['candidate_regressions']==1
        assert result['eligible_for_canary'] is False
        assert all(r['models_verified'] for r in result['rows'])
        tagged=g.complete(c.virtual_model,'My account password needs a reset',tagged=True)
        untagged=g.complete(c.virtual_model,'My account password needs a reset',tagged=False)
        assert tagged['resolved_model']==c.candidate_model
        assert untagged['resolved_model']==c.baseline_model
        rows=g.fetch_recent_spans('2026-09-26T00:00:00Z')
        assert len(rows)==57 and all('tfy.input' not in r for r in rows)
    finally:
        srv.shutdown();srv.server_close();thread.join(timeout=3)
