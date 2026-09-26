"""TrueForge MCP tools. Attach this streamable-HTTP server as a connector.

Only synthetic tickets enter live gateway calls. The server has no apply tool;
production routing is unchanged.
"""
import os
from .core import Config, Gateway, DownshiftError, evaluate, synthetic_cases

def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise RuntimeError("Install project dependencies first: pip install -e .") from e
    host=os.getenv("DOWNSHIFT_HOST","127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise DownshiftError("Refusing non-loopback MCP binding; use a separately authenticated private tunnel/ingress")
    mcp=FastMCP("downshift",host=host,port=int(os.getenv("DOWNSHIFT_PORT","8766")))

    @mcp.tool()
    def seed_synthetic_traffic() -> dict:
        """Send 28 labeled SYNTHETIC support tickets through the baseline model to create real Gateway traces."""
        g=Gateway(Config.from_env())
        rows=[]
        for case in synthetic_cases():
            r=g.complete(g.c.baseline_model,case["ticket"])
            rows.append({"ticket":case["ticket"],"expected":case["label"],"baseline":r["label"]})
        return {"calls":len(rows),"results":rows,"synthetic":True}

    @mcp.tool()
    def replay_and_score_synthetic() -> dict:
        """Call baseline and cheaper candidate models on labeled synthetic tickets; no production changes."""
        return evaluate(Gateway(Config.from_env()))

    @mcp.tool()
    def recent_ticket_spend(start_time: str) -> dict:
        """Return model and cost fields for ticket-classify traces, never prompt content."""
        spans=Gateway(Config.from_env()).fetch_recent_spans(start_time)
        return {"spans":spans,"count":len(spans),"warning":"Only Model spans are returned; verify billed cost semantics in the live tenant. No savings claim is made."}

    @mcp.tool()
    def propose_canary() -> dict:
        """Return a review-only 90/10 routing proposal. Does NOT update the Gateway."""
        c=Config.from_env()
        return {"virtual_model":c.virtual_model,"type":"weight-based-routing","load_balance_targets":[{"target":c.baseline_model,"weight":90},{"target":c.candidate_model,"weight":10,"metadata_match":{"route":"ticket-classify"}}],"status":"non-actionable illustration only; no stored evaluation or live config comparison"}

    return mcp

def main():
    create_server().run(transport="streamable-http")

if __name__=="__main__": main()
