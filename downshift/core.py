"""Gateway adapter and conservative classification evaluation.

The tool does not change production routing.
"""
from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
import httpx

TASK = "ticket-classify"
LABELS = frozenset({"billing", "technical", "account", "other"})

class DownshiftError(Exception):
    pass

@dataclass(frozen=True)
class Config:
    gateway_url: str
    control_url: str
    token: str
    baseline_model: str
    candidate_model: str
    virtual_model: str = ""
    data_routing_destination: str = "default"

    @classmethod
    def from_env(cls) -> "Config":
        keys = ("TFY_GATEWAY_URL", "TFY_CONTROL_URL", "TFY_API_TOKEN", "TFY_BASELINE_MODEL", "TFY_CANDIDATE_MODEL")
        missing = [k for k in keys if not os.getenv(k)]
        if missing:
            raise DownshiftError("Missing required environment variables: " + ", ".join(missing))
        urls = [os.environ["TFY_GATEWAY_URL"], os.environ["TFY_CONTROL_URL"]]
        for url in urls:
            p = urlparse(url)
            if p.scheme != "https" and p.hostname not in ("localhost", "127.0.0.1"):
                raise DownshiftError("Gateway and control URLs must use HTTPS except localhost")
            if not p.hostname or p.username or p.password or p.query or p.fragment:
                raise DownshiftError("Invalid gateway/control URL")
        return cls(*(os.environ[k].rstrip("/") if k.endswith("URL") else os.environ[k] for k in keys), os.getenv("TFY_VIRTUAL_MODEL", ""), os.getenv("TFY_DATA_ROUTING_DESTINATION", "default"))

def _label(value: Any) -> str | None:
    if isinstance(value, dict) and set(value) == {"label"} and isinstance(value.get("label"), str):
        value = value["label"]
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                value = parsed if set(parsed) != {"label"} else parsed.get("label")
        except ValueError:
            pass
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if value in LABELS else None

def redact(s: str) -> str:
    s = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", s)
    s = re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "[PHONE]", s)
    return s

def synthetic_cases() -> list[dict[str,str]]:
    return [
        {"ticket": "I was charged twice on my invoice", "label": "billing"},
        {"ticket": "My subscription invoice is wrong", "label": "billing"},
        {"ticket": "The app freezes when I upload a PDF", "label": "technical"},
        {"ticket": "API returns 500 for my request", "label": "technical"},
        {"ticket": "Please reset my password", "label": "account"},
        {"ticket": "I need to change my account email", "label": "account"},
        {"ticket": "Do you have an office in Pune?", "label": "other"},
        {"ticket": "Where can I read your product updates?", "label": "other"},
        {"ticket": "Invoice says tax was added twice", "label": "billing"},
        {"ticket": "Refund for duplicate charge has not arrived", "label": "billing"},
        {"ticket": "Please update my payment receipt", "label": "billing"},
        {"ticket": "The annual plan price on my bill looks wrong", "label": "billing"},
        {"ticket": "Checkout charged me but order failed", "label": "billing"},
        {"ticket": "CSV import gives a parse error", "label": "technical"},
        {"ticket": "The dashboard stays blank after loading", "label": "technical"},
        {"ticket": "Webhook requests time out", "label": "technical"},
        {"ticket": "Search stops responding after an update", "label": "technical"},
        {"ticket": "Files upload but cannot be opened", "label": "technical"},
        {"ticket": "I lost access to my profile", "label": "account"},
        {"ticket": "Two-factor code is not arriving", "label": "account"},
        {"ticket": "Please change my account username", "label": "account"},
        {"ticket": "I cannot sign in after changing my password", "label": "account"},
        {"ticket": "My account appears locked", "label": "account"},
        {"ticket": "Can I export a copy of the docs?", "label": "other"},
        {"ticket": "Where is the API guide?", "label": "other"},
        {"ticket": "What regions do you support?", "label": "other"},
        {"ticket": "Do you offer training sessions?", "label": "other"},
        {"ticket": "Is there a public status page?", "label": "other"},
    ]

def messages(ticket: str) -> list[dict[str,str]]:
    return [{"role":"system","content":"Classify the support ticket. Return ONLY a JSON object with label equal to one of billing, technical, account, other. No extra keys."}, {"role":"user","content":ticket}]

class Gateway:
    def __init__(self, config: Config, client: httpx.Client | None = None):
        self.c = config
        self.client = client or httpx.Client(timeout=httpx.Timeout(25.0, connect=8.0))

    def _request(self, method: str, url: str, **kwargs: Any) -> tuple[Any, httpx.Headers]:
        try:
            r = self.client.request(method, url, headers={"Authorization": f"Bearer {self.c.token}", **kwargs.pop("headers", {})}, **kwargs)
            r.raise_for_status()
            return r.json(), r.headers
        except httpx.HTTPStatusError as e:
            raise DownshiftError(f"Gateway HTTP {e.response.status_code} from {urlparse(url).hostname}") from e
        except (httpx.HTTPError, ValueError) as e:
            raise DownshiftError(f"Gateway request failed: {type(e).__name__}") from e

    def complete(self, model: str, ticket: str, tagged: bool = True) -> dict[str,Any]:
        if model not in (self.c.baseline_model, self.c.candidate_model, self.c.virtual_model):
            raise DownshiftError("Model is not configured for this rehearsal")
        if not isinstance(ticket,str) or not ticket.strip() or len(ticket)>4000:
            raise DownshiftError("Ticket must be 1-4000 characters")
        headers = {"x-tfy-metadata":json.dumps({"route":TASK})} if tagged else {}
        d, response_headers = self._request("POST", self.c.gateway_url + "/v1/chat/completions", json={"model":model,"messages":messages(ticket),"temperature":0,"max_tokens":60}, headers=headers)
        try:
            text = d["choices"][0]["message"]["content"]
            return {"label":_label(text),"model":d.get("model",model),"tokens":d.get("usage",{}).get("total_tokens"),"resolved_model":response_headers.get("x-tfy-resolved-model"),"raw":text}
        except (KeyError,IndexError,TypeError) as e:
            raise DownshiftError("Malformed gateway completion response") from e

    def fetch_recent_spans(self, start_time: str, max_pages: int = 5) -> list[dict[str,Any]]:
        """Summarize recent traffic; do not return prompt/response content from production logs."""
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(start_time.replace("Z","+00:00"))
            if dt.tzinfo is None: raise ValueError("timezone required")
        except ValueError as e: raise DownshiftError("start_time must be ISO-8601") from e
        token = None
        summaries: list[dict[str,Any]] = []
        seen = set()
        for _ in range(max_pages):
            payload = {"dataRoutingDestination":self.c.data_routing_destination,"startTime":start_time}
            if token: payload["pageToken"] = token
            d, _ = self._request("POST",self.c.control_url+"/api/svc/v1/spans/query",json=payload)
            for span in d.get("data",[]):
                a=span.get("spanAttributes") or {}
                metadata=a.get("tfy.request.metadata") or {}
                if isinstance(metadata,str):
                    try: metadata=json.loads(metadata)
                    except ValueError: metadata={}
                if isinstance(metadata,dict) and metadata.get("route") == TASK and a.get("tfy.span_type") == "Model":
                    summaries.append({"model":a.get("tfy.model.fqn"),"cost_usd":a.get("tfy.model.metric.cost_in_usd"),"span_type":a.get("tfy.span_type")})
            token=(d.get("pagination") or {}).get("nextPageToken")
            if not token: break
            if token in seen: raise DownshiftError("Repeated pagination token")
            seen.add(token)
        if token:
            raise DownshiftError("Span query exceeded max_pages; results incomplete. Narrow start_time and retry")
        return summaries

def evaluate(gateway: Gateway, cases: list[dict[str,str]] | None = None) -> dict[str,Any]:
    cases = cases if cases is not None else synthetic_cases()
    if not cases or len(cases)>100:
        raise DownshiftError("Need 1-100 cases")
    rows=[]
    for case in cases:
        if not isinstance(case,dict) or not isinstance(case.get("ticket"),str): raise DownshiftError("Invalid case")
        expected = _label(case.get("label"))
        if not expected: raise DownshiftError("Invalid expected label in case")
        base=gateway.complete(gateway.c.baseline_model,case["ticket"])
        cand=gateway.complete(gateway.c.candidate_model,case["ticket"])
        baseline_resolved=base.get("resolved_model")
        candidate_resolved=cand.get("resolved_model")
        verified=baseline_resolved==gateway.c.baseline_model and candidate_resolved==gateway.c.candidate_model
        rows.append({"ticket":redact(case["ticket"]),"expected":expected,"baseline":base["label"],"candidate":cand["label"],"baseline_resolved_model":baseline_resolved,"candidate_resolved_model":candidate_resolved,"models_verified":verified,"baseline_correct":base["label"]==expected,"candidate_correct":cand["label"]==expected})
    n=len(rows)
    base_rate=sum(r["baseline_correct"] for r in rows)/n
    candidate_rate=sum(r["candidate_correct"] for r in rows)/n
    # Never declare victory on a tiny fixture; use the sample as demonstration only.
    return {"task":TASK,"count":n,"baseline_accuracy":base_rate,"candidate_accuracy":candidate_rate,"candidate_regressions":sum(r["baseline_correct"] and not r["candidate_correct"] for r in rows),"eligible_for_canary":n>=20 and all(r["models_verified"] for r in rows) and candidate_rate>=0.95 and candidate_rate>=base_rate and all(not (r["baseline_correct"] and not r["candidate_correct"]) for r in rows),"rows":rows,"caveat":"Synthetic cases demonstrate workflow, not real-world quality. Model identity must be confirmed by x-tfy-resolved-model on every call; any missing/mismatched header makes this run inconclusive. No routing update is automatic."}
