# Downshift

A small, evidence-first AI cost-governance agent for the TrueFoundry × Polaris "Agents That Act" hackathon. It sends synthetic support tickets through a real TrueFoundry AI Gateway, reads tagged traces, replays tickets on one cheaper model, scores exact labels, and offers a review-only canary plan. The proposed routing change is **not applied by this build**; a human must review and perform the demo virtual-model change. This keeps production untouched and makes the missing integration explicit.

## Problem and scope

Expensive default models classify simple tickets. Downshift tests whether one cheaper model produces the same required labels for one `ticket-classify` route. It is not a generic cloud cleaner. Synthetic samples show mechanics, not evidence for production savings. The built-in 28-case fixture is synthetic, not proof of production quality; the rubric requires at least 20 labeled cases, at least 95% candidate accuracy, no accuracy drop, zero candidate regressions on cases the incumbent got right, and verified resolved-model headers on every call. Human review is still required.

## How it acts

1. `seed` sends 28 labeled **synthetic** tickets to the baseline model with `x-tfy-metadata: {"route":"ticket-classify"}`. They generate real gateway traces.
2. `logs` queries paginated spans and returns only model, span type and cost fields. It does not export prompts from real traffic; only Model spans are returned, and a truncated pagination raises an error. Confirm how the tenant bills spans before calling it spend.
3. `replay` sends the same labeled tickets to the baseline and one cheaper candidate and reports exact-label accuracy and regressions. It never claims savings from synthetic samples.
4. `plan` returns a non-actionable 90/10 virtual-model configuration illustration with `metadata_match` on the candidate. It does not change the Gateway. To prove the routing effect, a human can set up a *demo-only* virtual model in the TrueFoundry console, then send tagged and untagged requests and inspect the response's `x-tfy-resolved-model`. An unconditioned incumbent target is required as a catch-all. Gateway fallback may land on the incumbent even when the config picked the cheap model.

## Run

Python 3.10+.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
export TFY_GATEWAY_URL=https://gateway.truefoundry.ai
export TFY_CONTROL_URL=https://YOUR_CONTROL_PLANE
export TFY_API_TOKEN=YOUR_SECRET_FROM_PRIVATE_ENV
export TFY_BASELINE_MODEL=provider/incumbent
export TFY_CANDIDATE_MODEL=provider/cheap
export TFY_VIRTUAL_MODEL=demo/virtual
python -m downshift.cli seed
python -m downshift.cli logs --start 2026-09-26T00:00:00Z
python -m downshift.cli replay
python -m downshift.cli plan
pytest -q
```

Never commit `.env`, a PAT, customer prompts or raw span data. Gateway requests cost provider credits. Start with one test call before sending all 28.

## TrueForge connector

`downshift-mcp` exposes four tools over streamable HTTP at `http://127.0.0.1:8766/mcp`: seed synthetic traffic, replay and score, recent ticket spend, propose canary. TrueForge requires a reachable MCP URL; localhost works only when TrueForge runs on the same machine. The server refuses non-loopback binding. In hosted mode, a separate private tunnel/HTTPS ingress needs authentication and least-privilege credentials; this repository does not provide that ingress. Do not expose it publicly. Attach it through TrueForge Settings > Connectors, enable a Daytona sandbox for Code Mode, then call its tools from the sandbox through `mcp_client.call_tool`. Credentials remain in the MCP server's private environment, never in the sandbox. This connector makes no production write available. **The approval-gated apply tool from the original design is not implemented**, so do not imply the agent changed routing. A manual demo-only configuration change requires separate human approval.

## Tests and limitations

`pytest -q` covers exact schema/label validation, invalid input, successful and failing HTTP calls, pagination, prompt omission, regression/no-go decisions, and redaction. These tests use an HTTP mock; they are not proof of account access or live end-to-end integration. Live checks still needed: account permissions, a model inference, tracing query, Daytona bridged MCP call, and a demo-only virtual-model read/update with tagged and untagged requests. No real customer data should be used.

AI assistance disclosure: Instinct's AI assistant helped design, write and review this project. Samiksha Shreya must review and be able to explain the implementation before submitting.

References: [hackathon](https://hackculture.io/hackathons/agents-that-act), [Gateway request headers](https://www.truefoundry.com/docs/ai-gateway/request-headers), [request logs](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs), [virtual models](https://www.truefoundry.com/docs/ai-gateway/virtual-model), [TrueForge Code Mode](https://trueforge.dev/key-features/code-mode).

## Local mock walkthrough (when participant tenant access is not available)

A deliberately labeled `MOCK` gateway is included for a network-level rehearsal, not a substitute for TrueFoundry E2E. It binds to 127.0.0.1 only and never uses real provider credits. In one terminal run `python -m downshift.demo_gateway`; in another use:

```sh
export TFY_GATEWAY_URL=http://127.0.0.1:8765
export TFY_CONTROL_URL=http://127.0.0.1:8765
export TFY_API_TOKEN=mock-only
export TFY_BASELINE_MODEL=demo/incumbent
export TFY_CANDIDATE_MODEL=demo/cheap
export TFY_VIRTUAL_MODEL=demo/virtual
python -m downshift.cli seed
python -m downshift.cli logs --start 2026-09-26T00:00:00Z
python -m downshift.cli replay
python -m downshift.cli plan
```

The mock intentionally misclassifies one "charged me but order failed" ticket on the cheap model, so the safe result is **KEEP** despite lower mock unit cost. Tagged `demo/virtual` requests resolve to the cheap model; untagged ones to incumbent, exercised by `tests/test_http_e2e.py`. These are invented behaviors for test coverage, not evidence that TrueFoundry's real routing follows the same pattern. Never show mock data as live Gateway logs or savings.
