# Downshift

A small, evidence-first AI cost-governance agent for the TrueFoundry × Polaris "Agents That Act" hackathon. It sends synthetic support tickets through a real TrueFoundry AI Gateway, reads tagged traces, replays tickets on one cheaper model, scores exact labels, and offers a review-only canary plan. The proposed routing change is **not applied by this build**; a human must review and perform the demo virtual-model change. This keeps production untouched and makes the missing integration explicit.

## Problem and scope

Expensive default models classify simple tickets. Downshift tests whether one cheaper model produces the same required labels for one `ticket-classify` route. It is not a generic cloud cleaner. Synthetic samples show mechanics, not evidence for production savings. The built-in 28-case fixture is synthetic, not proof of production quality; the rubric requires at least 20 labeled cases, at least 95% candidate accuracy, no accuracy drop, and zero candidate regressions on cases the incumbent got right. Human review is still required.

## How it acts

1. `seed` sends 28 labeled **synthetic** tickets to the baseline model with `x-tfy-metadata: {"route":"ticket-classify"}`. They generate real gateway traces.
2. `logs` queries paginated spans and returns only model, span type and cost fields. It does not export prompts from real traffic. Do not sum multiple span types as spend without confirming which spans represent billed model calls.
3. `replay` sends the same labeled tickets to the baseline and one cheaper candidate and reports exact-label accuracy and regressions. It never claims savings from synthetic samples.
4. `plan` returns a review-only 90/10 virtual-model configuration sketch with `metadata_match` on the candidate. It does not change the Gateway. To prove the routing effect, a human can set up a *demo-only* virtual model in the TrueFoundry console, then send tagged and untagged requests and inspect the response's `x-tfy-resolved-model`. An unconditioned incumbent target is required as a catch-all. Gateway fallback may land on the incumbent even when the config picked the cheap model.

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

`downshift-mcp` exposes four tools over streamable HTTP at `http://127.0.0.1:8766/mcp`: seed synthetic traffic, replay and score, recent ticket spend, propose canary. TrueForge requires a reachable MCP URL; localhost works only when TrueForge runs on the same machine. In hosted mode, serve behind HTTPS with access control, not on a public unauthenticated port. Attach it through TrueForge Settings > Connectors, enable a Daytona sandbox for Code Mode, then call its tools from the sandbox through `mcp_client.call_tool`. Credentials remain in the MCP server's private environment, never in the sandbox. This connector makes no production write available. **The approval-gated apply tool from the original design is not implemented**, so do not imply the agent changed routing. A manual demo-only configuration change requires separate human approval.

## Tests and limitations

`pytest -q` covers exact schema/label validation, invalid input, successful and failing HTTP calls, pagination, prompt omission, regression/no-go decisions, and redaction. These tests use an HTTP mock; they are not proof of account access or live end-to-end integration. Live checks still needed: account permissions, a model inference, tracing query, Daytona bridged MCP call, and a demo-only virtual-model read/update with tagged and untagged requests. No real customer data should be used.

AI assistance disclosure: Instinct's AI assistant helped design, write and review this project. Samiksha Shreya must review and be able to explain the implementation before submitting.

References: [hackathon](https://hackculture.io/hackathons/agents-that-act), [Gateway request headers](https://www.truefoundry.com/docs/ai-gateway/request-headers), [request logs](https://www.truefoundry.com/docs/ai-gateway/fetch-request-logs), [virtual models](https://www.truefoundry.com/docs/ai-gateway/virtual-model), [TrueForge Code Mode](https://trueforge.dev/key-features/code-mode).
