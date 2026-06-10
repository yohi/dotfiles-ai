---
name: jmeter-scenario-builder
description: >-
  Generate runnable Apache JMeter test plans (.jmx XML) from a natural-language
  description of a load or performance test. Use this skill whenever the user
  wants to create, build, or scaffold a JMeter scenario, load test, stress test,
  performance test, or .jmx file - including phrasings like "100 users hitting
  the login API for 5 minutes", "make a jmeter test for these endpoints",
  "負荷テストのシナリオを作って", or "jmxファイルを生成して". Trigger even when the user
  does not say ".jmx" explicitly but clearly describes concurrent users, ramp-up,
  throughput, endpoints to hammer, or think time. Do NOT use for analysing
  existing .jtl results, for non-JMeter tools (k6, Locust, Gatling, ab), or for
  functional API testing without a load/concurrency dimension.
---

# JMeter Scenario Builder

Turn a plain-language load-test description into a valid, runnable JMeter `.jmx`.

The hard part of `.jmx` is not the ideas - it is the XML. Every test element must
be followed by a sibling `<hashTree>`, and property names like
`ThreadGroup.num_threads` or the misspelled `Asserion.test_strings` must match
JMeter byte-for-byte. Getting one wrong yields a file JMeter silently mis-loads.
So instead of hand-writing XML, you express the scenario as a small spec and let
the bundled builder emit correct XML deterministically.

## Workflow

### 1. Extract the scenario from the request

Read the user's description and pull out these pieces. Most requests give you the
load profile and endpoints; the rest you infer or ask about.

- **Target**: protocol (http/https), host/domain, port. Often a base URL.
- **Endpoints**: for each, the method, path, query/form params or request body,
  and any per-request headers (e.g. `Authorization`).
- **Load profile per thread group**: concurrent users (`threads`), `ramp_up`
  seconds, and either a `duration` (time-bounded run) or `loops` (fixed
  iterations). A request like "100 users for 5 minutes" means
  `threads=100, ramp_up≈30, duration=300`.
- **Parameterisation**: should requests vary per user (e.g. different product
  codes)? That points to a CSV Data Set and `${var}` references.
- **Auth / correlation**: login first, capture a token, reuse it. That is an
  extractor (`extractors`) writing a variable the next request reads.
- **Assertions**: what makes a request "pass"? Usually HTTP 200; sometimes a
  substring in the body.
- **Think time**: pauses between requests (`timer`).
- **Output**: which listeners/result files the user wants.

### 2. Fill gaps with sensible defaults; ask only about blockers

Apply these defaults silently rather than interrogating the user:

- `ramp_up` ≈ `threads / 3` seconds (so you do not start everyone at once).
- One thread group unless distinct user populations are described.
- A `response_code equals 200` assertion on each sampler.
- `listeners: ["summary", "aggregate"]` for results.
- HTTPS on port 443 if the host looks like a public URL.

Ask the user only when a missing detail would change the test's meaning - e.g.
an unknown target host, or whether a run is time-bounded vs a fixed iteration
count. Do not block on cosmetic choices.

### 3. Write the spec

Compose a spec object and save it as `spec.json` (or `.yaml`). The schema is in
`references/spec-schema.md` - read it when you need a field you do not remember.
`assets/example-spec.json` is a complete, copyable starting point. Keep the spec
minimal: omit fields you do not need; the builder supplies defaults.

### 4. Build the .jmx

```bash
python scripts/build_jmx.py spec.json -o <name>.jmx
```

The builder validates that the output is well-formed XML and that the
element/`hashTree` nesting is internally consistent before writing. If it raises,
the spec has a structural problem - fix the spec, do not patch the XML by hand.

If the environment has no shell or Python, fall back to hand-writing XML using
`references/element-reference.md`, which documents the exact tags and properties.
This is the slower, error-prone path - prefer the builder.

### 5. Verify and hand off

Sanity-check the builder first if you are unsure of the environment:

```bash
python scripts/build_jmx.py --selftest   # builds the sample, prints OK to stderr
```

Then tell the user how to run their plan (non-GUI mode is the right way to load
test - the GUI is for editing only):

```bash
jmeter -n -t <name>.jmx -l results.jtl -e -o report/
```

`-n` non-GUI, `-t` the plan, `-l` raw results, `-e -o report/` an HTML dashboard.
If the spec referenced a CSV (e.g. `codes.csv`), remind the user it must sit next
to the `.jmx` at run time.

## What the builder supports today

Test Plan + User Defined Variables, Thread Groups (threads / ramp-up /
duration or loops), HTTP Request Defaults, HTTP Header Manager (global, per
group, per sampler), HTTP Request samplers (GET/POST/... with params or raw JSON
body), Response Assertions, JSON and Regex extractors, Constant and Uniform
Random timers, CSV Data Set Config, and result listeners (Summary, Aggregate,
View Results Tree/Table).

Need something outside this list (e.g. a Transaction Controller, Constant
Throughput Timer, JSR223 sampler)? Two options: add a small builder function to
`scripts/build_jmx.py` following the existing pattern (each `build_*_element`
returns a bare element; the Node tree handles `hashTree` nesting), or hand-author
that one element using `references/element-reference.md`. Prefer extending the
builder when the element will recur.

## Common patterns

See `references/recipes.md` for ready-made spec fragments: login-then-call with
token correlation, data-driven requests from CSV, staged ramp via multiple
thread groups, and throughput-shaped load. Reach for it when the request matches
one of these shapes - it is faster than composing from scratch.
