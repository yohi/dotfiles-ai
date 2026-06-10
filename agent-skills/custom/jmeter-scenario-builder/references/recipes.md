# JMeter Scenario Recipes

Copyable spec fragments for the shapes that come up most often. Match the user's
request to one of these and adapt the values, rather than composing from a blank
page. All fragments are spec JSON for `scripts/build_jmx.py`.

## 1. Login, capture a token, then call protected endpoints

The classic correlation pattern: the first sampler authenticates and extracts a
token; later samplers send it as a Bearer header. Because the token is a JMeter
variable (`${token}`), every virtual user gets its own.

```json
{
  "test_plan": {"name": "Authenticated API Test"},
  "variables": {"BASE_URL": "api.example.com"},
  "defaults": {"protocol": "https", "domain": "${BASE_URL}", "port": "443"},
  "headers": {"Content-Type": "application/json"},
  "thread_groups": [{
    "name": "API users",
    "threads": 50, "ramp_up": 15, "duration": 180,
    "samplers": [
      {"name": "POST /login", "method": "POST", "path": "/auth/login",
       "body": {"email": "load@example.com", "password": "secret"},
       "assertions": [{"field": "response_code", "type": "equals", "value": "200"}],
       "extractors": [{"type": "json", "var": "token", "jsonpath": "$.access_token"}]},
      {"name": "GET /me", "method": "GET", "path": "/me",
       "headers": {"Authorization": "Bearer ${token}"},
       "assertions": [{"field": "response_code", "type": "equals", "value": "200"}]}
    ]
  }],
  "listeners": ["summary", "aggregate"]
}
```

## 2. Data-driven requests from a CSV file

Each iteration pulls a fresh row from `codes.csv` so users hit different records.
The file must sit next to the `.jmx` at run time; its columns map to the
`variables` names in order.

```json
{
  "test_plan": {"name": "Stock lookup by code"},
  "variables": {"BASE_URL": "stock.example.com"},
  "defaults": {"protocol": "https", "domain": "${BASE_URL}", "port": "443"},
  "thread_groups": [{
    "name": "Stock readers",
    "threads": 200, "ramp_up": 60, "duration": 600,
    "csv_data": [{"filename": "codes.csv", "variables": ["code"], "recycle": true}],
    "samplers": [
      {"name": "GET /stock", "method": "GET", "path": "/api/stock",
       "params": {"code": "${code}"},
       "assertions": [{"field": "response_code", "type": "equals", "value": "200"}],
       "timer": {"type": "uniform", "delay": 200, "range": 800}}
    ]
  }],
  "listeners": ["summary"]
}
```

## 3. Staged / stepped ramp via multiple thread groups

JMeter's standard Thread Group cannot ramp in stages by itself. The simplest
portable way to model "warm up, then peak" is several thread groups with
different sizes and start delays (`startup_delay`), all in one plan. They run
concurrently, so the offsets create the steps.

```json
{
  "test_plan": {"name": "Stepped load"},
  "defaults": {"protocol": "https", "domain": "www.example.com", "port": "443"},
  "thread_groups": [
    {"name": "Step 1 - warmup", "threads": 20, "ramp_up": 30, "duration": 300,
     "startup_delay": 0,
     "samplers": [{"name": "GET /", "method": "GET", "path": "/"}]},
    {"name": "Step 2 - peak", "threads": 80, "ramp_up": 30, "duration": 240,
     "startup_delay": 60,
     "samplers": [{"name": "GET /", "method": "GET", "path": "/"}]}
  ],
  "listeners": ["aggregate"]
}
```

## 4. Smoke test - a few iterations, fast feedback

Use `loops` instead of `duration` when you just want to confirm a plan works
before a big run. A handful of users, a fixed number of passes, results in a
tree you can eyeball.

```json
{
  "test_plan": {"name": "Smoke test"},
  "defaults": {"protocol": "https", "domain": "www.example.com", "port": "443"},
  "thread_groups": [{
    "name": "Smoke",
    "threads": 2, "ramp_up": 1, "loops": 3,
    "samplers": [
      {"name": "GET home", "method": "GET", "path": "/",
       "assertions": [{"field": "response_code", "type": "equals", "value": "200"}]},
      {"name": "GET health", "method": "GET", "path": "/health",
       "assertions": [{"field": "response_data", "type": "substring", "value": "ok"}]}
    ]
  }],
  "listeners": ["tree"]
}
```

## 5. Body text and negative assertions

Check that a response does *not* contain an error string, in addition to the
status code. `negate: true` flips a match.

```json
{
  "name": "POST /order", "method": "POST", "path": "/orders",
  "body": {"sku": "${sku}", "qty": 1},
  "assertions": [
    {"field": "response_code", "type": "equals", "value": "200"},
    {"field": "response_data", "type": "substring", "value": "error", "negate": true}
  ]
}
```

## Tips that prevent bad load tests

- **Ramp up, do not spike.** Starting 500 threads with `ramp_up: 0` measures
  your connection-setup cliff, not steady-state throughput. Spread the start.
- **Time-bound real runs.** Prefer `duration` over huge `loops` so the test ends
  predictably and you compare equal time windows across runs.
- **Add think time** with a `timer` when simulating humans; omit it when probing
  raw backend capacity.
- **Parameterise** anything that would otherwise hit one cached record - a single
  repeated `code` flatters the system under test.
- **Keep listeners light** for big runs. View Results Tree (`tree`) stores every
  response and will exhaust memory at scale; use it only for smoke tests, and
  rely on `summary`/`aggregate` plus the `-e -o report/` HTML dashboard for load.
