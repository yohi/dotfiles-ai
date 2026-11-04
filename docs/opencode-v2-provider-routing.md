# OpenCode V2 Provider Routing

The isolated OpenCode V2 launcher exposes two provider routes from `apm.yml`:

| Models | Route | Authentication |
| --- | --- | --- |
| GPT family, default `openai/gpt-6-luna` | OpenCode's built-in OpenAI provider | ChatGPT subscription through the Docker Host OAuth bridge |
| Other configured hosted models, including Ollama Cloud and Sakura AI Engine | Existing `cloudflare-ai-gateway-custom` provider | Cloudflare AI Gateway Custom Provider through `/compat` |

Claude Agent is deferred. The V2 configuration does not enable other providers or fallback routes.

## OpenAI ChatGPT subscription

Store the OpenAI OAuth credential on the Host using Docker's supported host-side flow, for example:

```sh
sbx secret set openai --oauth
```

The launcher seeds OpenCode V2's auth bridge with the Docker-documented sentinels `oai-oat01-proxy-managed` and `oai-ort01-proxy-managed`. The Host proxy is responsible for resolving these when OpenCode calls the ChatGPT/Codex service and refresh endpoint. The real access and refresh tokens must remain in Docker's Host credential store; the Guest auth database contains only the sentinel values.

Do not use `/connect` or `opencode auth login` inside the Guest because OpenCode V2 stores native OAuth credentials in its server-side SQLite database. Docker documents its OAuth bridge for Codex and describes an OpenCode-kit bridge, but the kit conflicts with the built-in `opencode` agent name. Verify that the installed Docker credential proxy supports this launcher's OpenCode bridge before sending a prompt. If it does not, stop rather than authenticating in the Guest.

## Cloudflare AI Gateway Custom Provider

The existing APM route uses the Cloudflare AI Gateway `/compat` endpoint and APM-declared Custom Provider model IDs such as:

- `custom-ollama-cloud/kimi-k2.7-code`
- `custom-sakura-ai/preview/Kimi-K2.7-Code`

The corresponding upstream provider credentials must already be configured in Cloudflare. The Guest does not receive those credentials. It receives only `OC_CF_API_TOKEN=proxy-managed` for the `cf-aig-authorization` header.

Set the non-secret Account ID and Gateway ID in the Host environment, and register the Gateway authentication token as a Host-side custom secret before creating the named Sandbox:

```sh
export OC_CF_ACCOUNT_ID='<32-hex-account-id>'
export OC_CF_GATEWAY_ID='default'

sbx secret set-custom \
  --sandbox oc2-cloudflare \
  --host gateway.ai.cloudflare.com \
  --env OC_CF_API_TOKEN \
  --placeholder proxy-managed \
  --ref 'op://<vault>/<item>/<field>'
```

Replace the Sandbox name and secret reference with the operator's values. Do not put the real token in `apm.yml`, project files, or Guest configuration.

## Launch

The V2 configuration enables OpenAI and Cloudflare Custom together, with GPT as the default. Select a Cloudflare Custom Provider model explicitly in OpenCode to use Ollama Cloud, Sakura AI Engine, or another model declared in APM.

```sh
python sandbox/scripts/oc2.py --sandbox oc2-cloudflare --allow-paid-inference
```

`--allow-paid-inference` is required for every interactive launch that can make external requests. OpenAI usage counts against the signed-in ChatGPT plan; Cloudflare requests are subject to the selected Gateway's billing and logging settings.

`--prepare-only` exports and verifies the APM-derived configuration without Sandbox commands. `--dry-run` prints the launch plan without exporting configuration or invoking Sandbox commands. Neither option authorizes inference.
