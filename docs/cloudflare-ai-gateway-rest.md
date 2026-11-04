# Cloudflare AI Gateway REST for OpenCode V2

This guide covers the optional Cloudflare AI Gateway REST provider in the isolated `oc2` OpenCode V2 launcher. The provider is disabled in the default `apm.yml` configuration. Selecting it requires a Cloudflare API token held by Docker Sandboxes on the Host, non-secret account and gateway identifiers in the Host environment, and an explicit inference authorization for each interactive launch.

## Requirements

- A Cloudflare API token with **Account → Workers AI → Read** permission.
- Sufficient Cloudflare AI Gateway credits for third-party model inference.
- A sandbox-scoped Docker custom secret targeting `api.cloudflare.com`.
- Host environment variables `OC_CF_ACCOUNT_ID` (32 hexadecimal characters) and `OC_CF_GATEWAY_ID` (1–64 lowercase letters, digits, or hyphens; first character must be a letter or digit).

The REST API model configured by this provider is `openai/gpt-6-luna`. Cloudflare bills requests through the selected gateway's Unified Billing configuration. Gateway logging and other configured gateway controls apply to requests; review them before sending prompts.

## Select the provider in `apm.yml`

Keep the provider disabled until its Host secret and non-secret identifiers are ready. To select it, set `opencode_v2.default_model` to the Cloudflare provider/model ID, disable the OpenAI entry, and enable Cloudflare REST:

```yaml
opencode_v2:
  default_model: cloudflare-ai-gateway-rest/openai/gpt-6-luna
  deny_provider_fallback: true
  deny_guest_auth: true
  providers:
    openai:
      enabled: false
      auth_method: docker_openai_oauth
    cloudflare-ai-gateway-rest:
      enabled: true
      auth_method: docker_custom_secret
```

The provider definition already uses environment references for the account ID, gateway ID, and API token placeholder. Do not replace those references with literal credentials or edit generated OpenCode configuration files.

## Register the Host-side custom secret

Register the token for the intended Sandbox name **before** creating that Sandbox. Use a supported secret reference so the token is not placed in shell history or passed as a command-line value:

```sh
sbx secret set-custom \
  --sandbox oc2-cloudflare \
  --host api.cloudflare.com \
  --env OC_CF_REST_API_TOKEN \
  --placeholder proxy-managed \
  --ref 'op://<vault>/<item>/<field>'
```

Replace the Sandbox name and secret reference with the operator's chosen values. Docker Sandboxes keeps the resolved token on the Host and substitutes the fixed `proxy-managed` placeholder in matching HTTP request headers. The real token must not appear in `apm.yml`, generated configuration, Guest environment, or project files.

## Launch

Set the two non-secret identifiers in the Host shell, then explicitly authorize external inference for the interactive session:

```sh
export OC_CF_ACCOUNT_ID='<32-hex-account-id>'
export OC_CF_GATEWAY_ID='default'
oc2 --sandbox oc2-cloudflare --allow-paid-inference
```

The launcher validates the IDs and passes only those IDs and the fixed token placeholder through its isolated `env -i` process environment. It never reads `OC_CF_REST_API_TOKEN` from the Host environment. OpenCode may issue billable requests only after the user sends a prompt during this explicitly authorized session.

`oc2 --prepare-only` exports and verifies the APM-derived configuration without invoking Sandbox commands. `oc2 --dry-run` prints the launch plan without exporting configuration or invoking Sandbox commands. Neither option authorizes inference.

The same `--allow-paid-inference` opt-in is required when selecting any external provider, including the OpenAI provider.
