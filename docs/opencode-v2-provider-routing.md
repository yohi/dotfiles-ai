# OpenCode V2 Provider Routing

The isolated OpenCode V2 launcher exposes two provider routes from `apm.yml`:

| Models | Route | Authentication |
| --- | --- | --- |
| GPT family, default `openai/gpt-6-luna` | OpenCode's built-in OpenAI provider | ChatGPT subscription through the Docker Host OAuth bridge |
| Other configured hosted models, including Ollama Cloud and Sakura AI Engine | Existing `cloudflare-ai-gateway-custom` provider | Cloudflare AI Gateway Custom Provider through `/compat` |

Claude Agent is deferred. The V2 configuration does not enable other providers or fallback routes.

## OpenAI ChatGPT subscription

The launcher generates a temporary Docker schema-v2 credential Mixin and attaches
it to the built-in `shell` Sandbox at creation. The Mixin declares OpenAI OAuth
interception, the ChatGPT resource host, and the sentinel-backed OpenCode
credential file. It also declares the Cloudflare Gateway credential injection
into `cf-aig-authorization`. The temporary kit is removed after Sandbox
creation; no credential is copied by the launcher.

**End-to-end ChatGPT OAuth support for this built-in OpenCode launch remains
unverified.** The Docker Mixin schema documents the required binding, but this
launcher has not been validated against a real Sandbox OAuth exchange. Do not
send GPT prompts through this route until the Host proxy is confirmed to replace
and refresh the sentinels. Docker may prompt for Host credential binding approval
during Sandbox creation; approve only through Docker's interactive flow. The
launcher does not register secrets or suppress the approval.

Do not use `/connect` or `opencode auth login` inside the Guest: OpenCode V2 stores native OAuth credentials in its Guest-side SQLite database. Do not place an OpenAI API key in APM or Guest files as a workaround. Use the Cloudflare Custom Provider route below while the subscription OAuth path is unresolved.

## Cloudflare AI Gateway Custom Provider

The existing APM route uses the Cloudflare AI Gateway `/compat` endpoint and APM-declared Custom Provider model IDs such as:

- `custom-ollama-cloud/kimi-k2.7-code`
- `custom-sakura-ai/preview/Kimi-K2.7-Code`

The corresponding upstream provider credentials must already be configured in
Cloudflare. The Guest does not receive those credentials. Docker's proxy supplies
the bound Host credential to the `cf-aig-authorization: Bearer …` header; the
launcher itself passes only `OC_CF_API_TOKEN=proxy-managed`.

Set the non-secret Account ID and Gateway ID in the Host environment. Provision
the `cloudflare-ai-gateway` credential through Docker's supported Host-side
secret/binding flow, or approve its first-run binding prompt when creating the
Sandbox. The launcher does not register the secret:

```sh
export OC_CF_ACCOUNT_ID='<32-hex-account-id>'
export OC_CF_GATEWAY_ID='default'

sbx secret set cloudflare-ai-gateway --sandbox oc2-cloudflare
```

Replace `oc2-cloudflare` with the Sandbox name. The `--sandbox` option scopes the
stored secret to that Sandbox. Use Docker's interactive secret input rather than
a command-line argument so the token is not exposed in shell history or process
arguments. Do not put the real token in `apm.yml`, project files, or Guest
configuration.

## Launch

The V2 configuration enables OpenAI and Cloudflare Custom together, with GPT as the default. Select a Cloudflare Custom Provider model explicitly in OpenCode to use Ollama Cloud, Sakura AI Engine, or another model declared in APM.

```sh
python sandbox/scripts/oc2.py --sandbox oc2-cloudflare --allow-paid-inference
```

`--allow-paid-inference` is required for every interactive launch that can make external requests. OpenAI usage counts against the signed-in ChatGPT plan; Cloudflare requests are subject to the selected Gateway's billing and logging settings.

`--prepare-only` exports and verifies the APM-derived configuration without Sandbox commands. `--dry-run` prints the launch plan without exporting configuration or invoking Sandbox commands. Neither option authorizes inference.
