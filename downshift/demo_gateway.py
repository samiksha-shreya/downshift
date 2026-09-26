"""Local-only stand-in gateway for the hackathon walkthrough, not TrueFoundry.

It exercises real HTTP requests and the agent's decision path without a vendor
account. Every result is synthetic, deterministic, and labeled MOCK.
"""
from __future__ import annotations
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

LABELS=('billing','technical','account','other')

def classify(ticket: str) -> str:
    t=ticket.lower()
    if any(w in t for w in ('invoice','charged','charge','bill','refund','receipt','price','checkout')):return 'billing'
    if any(w in t for w in ('freezes','api returns','csv import','dashboard','webhook','search stops','files upload')):return 'technical'
    if any(w in t for w in ('password','account','two-factor','sign in','profile','username')):return 'account'
    return 'other'

class MockGateway(BaseHTTPRequestHandler):
    traces=[]
    def log_message(self,format,*args):pass
    def reply(self,status,body,headers=None):
        b=json.dumps(body).encode()
        self.send_response(status); self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)))
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(b)
    def do_POST(self):
        if self.client_address[0] not in ('127.0.0.1','::1'):
            return self.reply(403,{'error':'loopback only'})
        n=int(self.headers.get('Content-Length','0'))
        if n>12000:return self.reply(413,{'error':'body too large'})
        try:body=json.loads(self.rfile.read(n))
        except (ValueError,TypeError):return self.reply(400,{'error':'invalid JSON'})
        path=urlparse(self.path).path
        if path=='/v1/chat/completions':
            model=body.get('model')
            if model not in ('demo/incumbent','demo/cheap','demo/virtual'):
                return self.reply(404,{'error':'unknown mock model'})
            try:
                ticket=body['messages'][-1]['content']
                if not isinstance(ticket,str):raise TypeError
            except (KeyError,IndexError,TypeError):return self.reply(400,{'error':'missing ticket'})
            try:meta=json.loads(self.headers.get('x-tfy-metadata','{}'))
            except ValueError:return self.reply(400,{'error':'bad metadata'})
            resolved='demo/incumbent' if model=='demo/virtual' and meta.get('route')!='ticket-classify' else ('demo/cheap' if model=='demo/virtual' else model)
            label=classify(ticket)
            # Deliberate hard-case regression on the cheap model demonstrates KEEP.
            if resolved=='demo/cheap' and 'charged me but order failed' in ticket.lower():label='technical'
            self.traces.append({'spanAttributes':{'tfy.span_type':'Model','tfy.request.metadata':meta,'tfy.model.fqn':resolved,'tfy.model.metric.cost_in_usd':0.01 if resolved=='demo/incumbent' else 0.001,'tfy.input':ticket,'tfy.output':label}})
            return self.reply(200,{'model':model,'choices':[{'message':{'content':json.dumps({'label':label})}}],'usage':{'total_tokens':42}}, {'x-tfy-resolved-model':resolved,'x-downshift-mock':'true'})
        if path=='/api/svc/v1/spans/query':
            return self.reply(200,{'data':self.traces[:], 'pagination':{}}, {'x-downshift-mock':'true'})
        return self.reply(404,{'error':'unknown mock endpoint'})

def main():
    host=os.getenv('MOCK_HOST','127.0.0.1')
    if host not in ('127.0.0.1','::1'):
        raise SystemExit('Mock gateway refuses non-loopback binding')
    server=ThreadingHTTPServer((host,int(os.getenv('MOCK_PORT','8765'))),MockGateway)
    print(f'MOCK GATEWAY ONLY at http://{host}:{server.server_port}',flush=True)
    server.serve_forever()
if __name__=='__main__':main()
