"""Network-level MCP and CLI smoke tests; mocked Gateway boundary only."""
import json
import os
import subprocess
import sys
from downshift.core import Config, Gateway, synthetic_cases
from downshift.server import create_server

def test_mcp_tools_available():
    import asyncio
    m=create_server()
    tools=asyncio.run(m.list_tools())
    assert {t.name for t in tools}=={'seed_synthetic_traffic','replay_and_score_synthetic','recent_ticket_spend','propose_canary'}

def test_cli_fails_closed_without_secrets():
    env={k:v for k,v in os.environ.items() if not k.startswith('TFY_')}
    p=subprocess.run([sys.executable,'-m','downshift.cli','seed'],env=env,capture_output=True,text=True)
    assert p.returncode==1 and 'Missing required environment variables' in p.stderr
    assert 'Traceback' not in p.stderr

def test_case_data_contains_only_synthetic_tickets():
    rows=synthetic_cases()
    assert len(rows)==28 and len(set(c['ticket'] for c in rows))==28
    assert all('@' not in c['ticket'] for c in rows)
