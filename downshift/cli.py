"""Command-line demo, with no implicit production write path."""
import argparse
import json
import sys
from datetime import datetime, timezone
from .core import Config, DownshiftError, Gateway, TASK, evaluate, synthetic_cases

def main() -> int:
    p = argparse.ArgumentParser(description="Downshift: synthetic ticket-classification rehearsal")
    p.add_argument("action", choices=("seed", "replay", "logs", "plan"))
    p.add_argument("--start", help="ISO-8601 start time for logs")
    p.add_argument("--output", help="Save report JSON to this local file")
    args = p.parse_args()
    try:
        c = Config.from_env()
        g = Gateway(c)
        if args.action == "seed":
            result=[]
            for case in synthetic_cases():
                r=g.complete(c.baseline_model,case["ticket"])
                result.append({"ticket":case["ticket"],"expected":case["label"],"baseline":r["label"]})
            report={"task":TASK,"calls":len(result),"results":result,"note":"Synthetic tickets only. Baseline gateway requests generate real traces."}
        elif args.action == "replay": report=evaluate(g)
        elif args.action == "logs":
            start=args.start or datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
            spans=g.fetch_recent_spans(start)
            report={"task":TASK,"matched_spans":len(spans),"models":sorted(set(str(s["model"]) for s in spans)),"cost_usd_sum":sum(float(s["cost_usd"] or 0) for s in spans),"warning":"Span types can double-count costs; inspect before using as savings evidence. Prompt content is deliberately excluded."}
        else:
            report={"task":TASK,"virtual_model":c.virtual_model or "NOT SET","baseline_model":c.baseline_model,"candidate_model":c.candidate_model,"proposed_routing_config":{"type":"weight-based-routing","load_balance_targets":[{"target":c.baseline_model,"weight":90},{"target":c.candidate_model,"weight":10}]},"status":"PROPOSAL ONLY - no production write. Human must compare live configuration and approve any apply separately."}
        text=json.dumps(report,indent=2,sort_keys=True)
        if args.output:
            with open(args.output,"w",encoding="utf8") as f:f.write(text+"\n")
        print(text)
        return 0
    except (DownshiftError,KeyError) as e:
        print("Downshift error: " + str(e),file=sys.stderr)
        return 1

if __name__ == "__main__": raise SystemExit(main())
