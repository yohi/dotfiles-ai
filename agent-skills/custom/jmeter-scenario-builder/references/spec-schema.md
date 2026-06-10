# JMeter Scenario Spec Schema

`build_jmx.py` turns a small, readable spec (JSON or YAML) into a valid JMeter
`.jmx` test plan. You (the agent) translate the user's natural-language request
into this spec, then run the builder. You should rarely need to hand-write `.jmx`.

## Top-level fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `test_plan.name` | string | `"Test Plan"` | Shown as the root node name. |
| `test_plan.comments` | string | `""` | Free text. |
| `variables` | object | `{}` | User Defined Variables, e.g. `{"BASE_URL":"example.com"}`. Reference with `${BASE_URL}`. |
| `defaults` | object | none | HTTP Request Defaults shared by all samplers. See below. |
| `headers` | object | none | Global HTTP Header Manager, e.g. `{"Content-Type":"application/json"}`. |
| `csv_data` | array | `[]` | Global CSV Data Set Config(s). See below. |
| `thread_groups` | array | **required** | One or more load profiles. See below. |
| `listeners` | array | `[]` | Result collectors: `"summary"`, `"aggregate"`, `"tree"`, `"table"`, or `{ "type": "...", "filename": "out.jtl" }`. |

## `defaults` (HTTP Request Defaults)

| Field | Notes |
|-------|-------|
| `protocol` | `http` / `https` |
| `domain` | host, e.g. `${BASE_URL}` |
| `port` | e.g. `443` (string or number) |
| `connect_timeout` / `response_timeout` | ms, optional |
| `content_encoding` | e.g. `UTF-8`, optional |

When `defaults` are set, samplers may omit `protocol`/`domain`/`port`.

## `thread_groups[]`

| Field | Default | Notes |
|-------|---------|-------|
| `name` | `"Thread Group"` | |
| `threads` | `1` | Concurrent virtual users. |
| `ramp_up` (or `ramp_time`) | `1` | Seconds to start all threads. |
| `loops` | `1` | Iterations per thread. `-1` = infinite. Ignored when `duration` is set (becomes time-bounded). |
| `duration` | none | Seconds. When set, the scheduler runs for this long (loops become `-1`). |
| `startup_delay` | `""` | Seconds before threads start. |
| `on_sample_error` | `"continue"` | `continue` / `startnextloop` / `stopthread` / `stoptest` / `stoptestnow`. |
| `headers` | none | Header Manager scoped to this group. |
| `csv_data` | `[]` | CSV Data Set scoped to this group. |
| `timer` | none | Think time applied to every sampler in the group. See timer. |
| `samplers` | **required** | See below. |

## `samplers[]` (HTTP Request)

| Field | Default | Notes |
|-------|---------|-------|
| `name` | `"<METHOD> <path>"` | |
| `method` | `GET` | GET/POST/PUT/DELETE/PATCH... |
| `path` | `/` | e.g. `/api/stock`. |
| `protocol`/`domain`/`port` | from `defaults` | Override per sampler if needed. |
| `params` | `{}` | Query/form params: `{"code":"${code}"}`. |
| `body` | none | Raw request body (string, or object -> serialized to JSON). Use for JSON POST/PUT. Do not combine with `params`. |
| `headers` | none | Header Manager scoped to this sampler. |
| `assertions` | `[]` | See assertions. |
| `extractors` | `[]` | See extractors. |
| `timer` | none | Think time for this sampler only. |

## assertions[]

| Field | Default | Notes |
|-------|---------|-------|
| `field` | `response_code` | `response_code` / `response_data` / `response_message` / `response_headers`. |
| `type` | `equals` | `equals` (8) / `substring` (16, plain contains) / `contains` (2, regex) / `matches` (1, regex full). |
| `value` | `"200"` | Single expected value. |
| `values` | none | List of expected values (overrides `value`). |
| `negate` | `false` | Invert (adds NOT flag). |
| `message` | `""` | Custom failure message. |

Guidance: for HTTP status use `field=response_code`, `type=equals`. For body text
use `field=response_data` with `type=substring` (plain) or `type=contains` (regex).

## extractors[]

JSON (default):

| Field | Default | Notes |
|-------|---------|-------|
| `type` | `json` | |
| `var` | `var` | Variable name to store the captured value. |
| `jsonpath` | `$` | JSONPath, e.g. `$.token`. |
| `match` | `1` | Match number (`0` = random, `-1` = all). |
| `default` | `""` | Default if no match. |

Regex (`type: regex`):

| Field | Notes |
|-------|-------|
| `var` | Variable name. |
| `regex` | Pattern with a capture group. |
| `template` | e.g. `$1$`. |
| `match` | Match number. |
| `default` | Default value. |

## timer

| Field | Notes |
|-------|-------|
| `type` | `constant` (default) or `uniform`. |
| `delay` | ms. For `constant`, the fixed pause. For `uniform`, the constant offset. |
| `range` | ms. Random spread added on top (uniform only). |

## csv_data[]

| Field | Default | Notes |
|-------|---------|-------|
| `filename` | `""` | Path relative to the `.jmx` at run time. |
| `variables` | `[]` | Column -> variable names, e.g. `["code","name"]`. |
| `delimiter` | `,` | |
| `encoding` | `UTF-8` | |
| `recycle` | `true` | Loop file when exhausted. |
| `ignore_first_line` | `false` | Skip header row. |
| `share_mode` | `shareMode.all` | `all` / `group` / `thread`. |
| `stop_thread` | `false` | Stop thread at EOF (when `recycle=false`). |
