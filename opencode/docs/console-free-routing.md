# OpenCode Console Free — opt-in integration gate (2026-10-18)

## Status

**CATALOG_ONLY / NOT_ACTIVATED.** The repository contains a separate
`cloudflare-ai-gateway-console-free` model provider and two OmO manual
aliases. No default agent, Justice category, `models` chain or
`fallback_models` chain uses this new provider.

This is a **stacked change** on
`fix/omo-commandcode-outage-glm53-flash`. CommandCode remains unavailable;
GLM-5.3 full remains explicit/manual only. The `work` profile remains
Bedrock-only. No Cloudflare/OpenCode account settings or keys are modified
by this pull request.

## Verified public contracts (read-only)

- [OpenCode Console Models](https://opencode.ai/v2/docs/console/models/):
  `glm-5.3-flash-free` and `deepseek-v4.1-flash-free` are distinct model
  IDs with free input, output and cache read pricing **for a limited time**.
  The free variants are separate from paid `glm-5.3-flash` and
  `deepseek-v4.1-flash`. Both free model providers are documented as
  zero-retention / no model training.
- [Console Inference API](https://opencode.ai/v2/docs/console/api/inference/):
  `https://opencode.ai/inference/openai/v1/chat/completions` is the relevant
  Chat Completions endpoint. Free chat models can be called without an
  upstream Console service-account key.
- [Console Budgets](https://opencode.ai/v2/docs/console/budgets/):
  A **$0 monthly budget** blocks *chargeable* requests while free models
  are excluded from budget spend. Limits are checked at request start.
- [Console Models / Auto-reload](https://opencode.ai/v2/docs/console/models/#auto-reload):
  Console can auto-reload credit when a balance drops under $5. Disable
  auto-reload independently of the budget.
- [Cloudflare Custom Providers](https://developers.cloudflare.com/ai-gateway/configuration/custom-providers/):
  Provider-specific routing appends the provider path to its `base_url`.
  Dynamic Routing is **not** part of this integration.

These statements describe public documentation, **not** verified account
settings, deployed Cloudflare resources or live request behavior.

## Isolated endpoint design (not yet provisioned)

In Cloudflare AI Gateway, provision a **new**, separately named Custom
Provider, not `custom-opencode-go` and not a Dynamic Route:

| Field | Required |
|---|---|
| Cloudflare custom provider slug | `opencode-console-free` |
| Cloudflare `base_url` | `https://opencode.ai` |
| Gateway path | `custom-opencode-console-free/inference/openai/v1/chat/completions` |
| Upstream path | `https://opencode.ai/inference/openai/v1/chat/completions` |
| Models allowlisted in `apm.yml` | `glm-5.3-flash-free`, `deepseek-v4.1-flash-free` |
| Upstream authentication | **No Console API key / no Go key / no Cloudflare BYOK** |
| Cloudflare authentication | Existing `cf-aig-authorization` gateway token only |
| Gateway retries | 1 maximum |
| Gateway log payload collection | disabled |
| Default OmO routing | unchanged |

**Blocking condition:** Cloudflare's general Custom Provider setup
documentation lists a provider API key as a prerequisite. The actual
support for an **unkeyed** Console Free upstream through Cloudflare is
*NOT VERIFIED*. If your Cloudflare account requires storing a provider
key, **do not** bypass this condition by reusing the Console/Go API key
or enabling BYOK. Stop and evaluate a small allowlist-enforcing proxy or
direct unauthenticated Console access as a separately reviewed design.

With no upstream paid-capable key, an attempted paid-model call must
fail rather than be automatically charged. Verify this at runtime.
Do not assume `apiKey: ""` alone guarantees no authorization at
Cloudflare; inspect the deployed provider and its stored secrets.

## Hard gates before any automatic task routes may change

- [ ] Confirm with official models/pricing immediately before testing
      that both exact `-free` IDs still cost $0 and the retention/training
      terms are acceptable. If not, **STOP**, do not substitute paid IDs.
- [ ] In Console, turn **Auto-reload OFF**; independently verify it is OFF.
      Set the workspace and/or dedicated service-account **monthly budget
      to $0** and independently verify it. Free use is excluded from
      budget consumption by current public documentation. Do not give
      the free route an inference/billing credential.
- [ ] Configure only the new Cloudflare custom provider; verify
      `base_url`, slug and path match above, no Console/Go upstream key
      or BYOK is stored or injected, no paid provider/model fallback is
      configured, and all cache/retry/log settings are as intended.
- [ ] Test the unkeyed Console API with a **synthetic, non-sensitive**
      prompt first. Confirm paid model IDs without a provider credential
      are rejected. Avoid sending repository secrets, personal data or
      proprietary source. Preserve redacted response/status evidence.
- [ ] Test the same two exact models through the new Cloudflare gateway
      path with synthetic prompts, small token budgets, stream/non-stream,
      basic tool calling and a single 429/5xx failure case. Check that
      failures do **not** get remapped to paid models or auto-retried.
- [ ] Check actual Console billing: no positive charges/auto-reload and
      no decrement to the Go subscription's allowance. Re-check public
      pricing after tests; **stop** if no longer free.
- [ ] Compare task execution/quality with existing Go/Ollama for
      `sp-mechanical` and then `sp-implementation`; before
      `sp-review` or `sp-final-review`, require separate quality and
      mandatory-gate evidence. No automatic routing or production
      changes without an explicit separate approval.

## Models and explicit manual use

`apm.yml` exports a **separate** OpenCode provider with model strings:

```text
cloudflare-ai-gateway-console-free/glm-5.3-flash-free
cloudflare-ai-gateway-console-free/deepseek-v4.1-flash-free
```

The OmO catalog aliases `glm-53-flash-console-free` and
`deepseek-v41-console-free` exist for discoverability only. In OmO
v4.19.4, some task paths cannot resolve aliases, so manual model
testing should use the full provider/model names above.

Do **not** add Console Free to `sp-mechanical`, `sp-implementation`
or any category until the preceding gates are proven. If a later
change enables the free variant, the mandatory rollback is to remove
only the new primary/fallback model references; existing Ollama/Go/Plus
fallbacks must stay available. In particular, `sp-review` and
`sp-final-review` must retain their independent mandatory review gates.

The `enabled_providers` entry exposes the provider to **manual**
OpenCode model selection when configured. It does not select a
default OmO agent/category or provision any Cloudflare resource.

## Runtime status and validation

Local offline unit tests: `pytest -q tests/test_opencode_console_free_routing.py`.

Before enabling automatic routing, record independently:
Cloudflare provider config, Console budget/auto-reload state, model
price/terms snapshot, sanitized smoke request evidence, no paid model
fallback, provider error-path response, and approved rollback.

Current result: **static configuration only; live Cloudflare and
Console checks NOT EXECUTED.**
