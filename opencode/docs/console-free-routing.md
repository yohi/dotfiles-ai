# OpenCode Console Free via Cloudflare — blocked evidence (2026-10-18)

## Verdict: BLOCKED / NOT ACTIVATED

The proposed Cloudflare Custom Provider `opencode-free` cannot currently be
recommended or enabled as an automatic OmO route. Two independent synthetic
smoke requests supplied by the owner on **2026-10-18 JST** failed:

| Test | HTTP | Evidence | Interpretation |
|---|---|---|---|
| Cloudflare `custom-opencode-free/inference/openai/v1/chat/completions` | 401 | `AiGatewayError`, code `2009`, `Unauthorized` | Cloudflare gateway authentication / provider credential boundary unresolved. Cannot identify the exact failing credential from this alone. |
| Direct `https://opencode.ai/inference/openai/v1/chat/completions` | 403 | `FreeTierError`: "OpenCode's free tier can only be used from within OpenCode." | OpenCode upstream rejected the unauthenticated external request independently of Cloudflare. |

**These are observed results, not a generalized proof of permanent API
unavailability.** The public
[Console Inference API documentation](https://opencode.ai/v2/docs/console/api/inference/)
states that free Chat models may be called without a service account token,
but the observed runtime behavior differs. Official OpenCode GitHub issues
[#56397](https://github.com/anomalyco/opencode/issues/56397),
[#56324](https://github.com/anomalyco/opencode/issues/56324), and
[#56398](https://github.com/anomalyco/opencode/issues/56398)
also report `FreeTierError` in some **genuine OpenCode clients**. Treat
service/client/region/account restrictions and incidents as **NOT RESOLVED**;
do not infer a supported Cloudflare integration from the model's $0 price.

Cloudflare's [authenticated gateway guidance](https://developers.cloudflare.com/ai-gateway/configuration/authentication/)
requires the `cf-aig-authorization` header on the provider-native gateway.
A 401/2009 response does not prove the upstream 403 caused the gateway
error. Investigate each separately if external integration is eventually
permitted, and check the Gateway Run permission, gateway ID, account, and
provider key configuration **without exposing token values**.

## Repository state and safety boundary

- Stacked on `fix/omo-commandcode-outage-glm53-flash`; parent fix untouched.
- `apm.yml` preserves a candidate **disabled** provider definition using the
  Cloudflare slug `opencode-free`. Its entry in `enabled_providers` is
  commented out, so it is not enabled for use.
- The two manual OmO aliases were **removed** to prevent presenting broken
  free endpoints as selectable models.
- No OmO personal agent, category, fallback, or Justice mandatory review
  path uses Console Free. The Work profile remains Bedrock-only.
- Existing Ollama / Go / Plus / OCTG paths remain in place; CommandCode is
  suspended and GLM-5.3 full stays manual-only in the parent fix.
- No Cloudflare/provider credentials or account settings were changed by
  this PR. A provider already created in the Cloudflare dashboard must be
  considered separate account state; Git changes do not delete it.

## Safe next investigation: OpenCode's native provider

The official CLI may offer these models through its **native** `opencode`
provider, without routing through a third-party Cloudflare Gateway.
This is a separate experiment, and success is **NOT YET PROVEN**.
Use a sandbox or non-sensitive directory and synthetic prompt only:

```sh
opencode --version
opencode models | grep -E 'opencode/(deepseek-v4\.1-flash-free|glm-5\.3-flash-free)'
opencode run --model opencode/deepseek-v4.1-flash-free "Reply OK only."
```

Observe the actual response and any error event, not only the command exit
code. If `FreeTierError` recurs, stop and record the version, timestamp,
model and redacted error. Follow official issue/status guidance rather
than simulating client identity or adding undocumented headers.

Potential future OmO integration is a separate reviewed change targeting
native provider model IDs `opencode/...`, **not** Cloudflare, and only after
successful native functional tests, model-price checks, privacy review and
Justice fallback verification.

## Reopening conditions for Cloudflare route

1. Provider explicitly supports the external or gateway-based API use case,
   with documented compliant authentication and request shape.
2. Synthetic direct API and Gateway requests succeed with supported
   credentials, without spoofing official-client-only identity.
3. Model billing, budget (including $0 budget if relevant), zero-retention
   claims, no paid fallback, and no auto-reload are independently verified.
4. Explicit owner decision authorizes promotion from disabled catalog.
5. OmO `models[1:]` / `fallback_models` and mandatory review contracts
   are validated before activation.

Until these conditions are demonstrated, **no further Cloudflare free-model
routing attempts or automatic integration are recommended**.

## Offline regression

`pytest -q tests/test_opencode_console_free_routing.py` (not run via
GitHub connector). These tests guard that the candidate is disabled and not
routed, but cannot prove live service availability.
