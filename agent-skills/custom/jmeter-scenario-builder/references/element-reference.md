# JMeter Element Reference

The exact XML for each element the builder emits. Use this when you must
hand-author an element the builder does not support, when debugging a generated
plan, or when adding a new `build_*_element` function to `scripts/build_jmx.py`.

## The two rules that break hand-written .jmx

1. **Alternating hashTree.** Inside the document, every test element is
   immediately followed by a *sibling* `<hashTree>` that contains its children
   (which themselves each get a following `<hashTree>`). An element with no
   children still gets an empty `<hashTree/>`. The builder guarantees this via
   its Node tree; by hand it is the #1 source of mistakes.

2. **Exact property names.** JMeter reads properties by `name` attribute, so the
   *order* of `<*Prop>` lines does not matter, but the *names* must be exact -
   including the historical typo `Asserion.test_strings` (missing an `s`).

## Document skeleton

```xml
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan ...>...</TestPlan>
    <hashTree>
      <ThreadGroup ...>...</ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy ...>...</HTTPSamplerProxy>
        <hashTree>
          <ResponseAssertion ...>...</ResponseAssertion>
          <hashTree/>
        </hashTree>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
```

## TestPlan

```xml
<TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test Plan" enabled="true">
  <stringProp name="TestPlan.comments"></stringProp>
  <boolProp name="TestPlan.functional_mode">false</boolProp>
  <boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp>
  <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
  <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
    <collectionProp name="Arguments.arguments">
      <elementProp name="BASE_URL" elementType="Argument">
        <stringProp name="Argument.name">BASE_URL</stringProp>
        <stringProp name="Argument.value">example.com</stringProp>
        <stringProp name="Argument.metadata">=</stringProp>
      </elementProp>
    </collectionProp>
  </elementProp>
  <stringProp name="TestPlan.user_define_classpath"></stringProp>
</TestPlan>
```

## ThreadGroup

`num_threads` = concurrent users, `ramp_time` = seconds to start them all.
For a time-bounded run set `scheduler=true`, `duration` (seconds), and the loop
controller `loops=-1` (infinite within the window). For a fixed-iteration run
set `scheduler=false` and `loops=N`.

```xml
<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Stock API" enabled="true">
  <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
  <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
    <boolProp name="LoopController.continue_forever">false</boolProp>
    <stringProp name="LoopController.loops">-1</stringProp>
  </elementProp>
  <stringProp name="ThreadGroup.num_threads">100</stringProp>
  <stringProp name="ThreadGroup.ramp_time">30</stringProp>
  <boolProp name="ThreadGroup.scheduler">true</boolProp>
  <stringProp name="ThreadGroup.duration">300</stringProp>
  <stringProp name="ThreadGroup.delay"></stringProp>
  <boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp>
</ThreadGroup>
```

`on_sample_error`: `continue` / `startnextloop` / `stopthread` / `stoptest` / `stoptestnow`.

## HTTP Request Defaults (ConfigTestElement)

Shared host/protocol/port so individual samplers only carry a path.

```xml
<ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" testname="HTTP Request Defaults" enabled="true">
  <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
    <collectionProp name="Arguments.arguments"/>
  </elementProp>
  <stringProp name="HTTPSampler.domain">${BASE_URL}</stringProp>
  <stringProp name="HTTPSampler.port">443</stringProp>
  <stringProp name="HTTPSampler.protocol">https</stringProp>
  <stringProp name="HTTPSampler.path"></stringProp>
</ConfigTestElement>
```

## HTTP Header Manager

```xml
<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Header Manager" enabled="true">
  <collectionProp name="HeaderManager.headers">
    <elementProp name="" elementType="Header">
      <stringProp name="Header.name">Content-Type</stringProp>
      <stringProp name="Header.value">application/json</stringProp>
    </elementProp>
  </collectionProp>
</HeaderManager>
```

## HTTP Request (HTTPSamplerProxy)

Query/form params go in the Arguments collection as `HTTPArgument`s with
`use_equals=true` and a name. A raw JSON body instead uses a single nameless
`HTTPArgument` plus `HTTPSampler.postBodyRaw=true`.

```xml
<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="GET /stock" enabled="true">
  <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
    <collectionProp name="Arguments.arguments">
      <elementProp name="code" elementType="HTTPArgument">
        <boolProp name="HTTPArgument.always_encode">true</boolProp>
        <stringProp name="Argument.value">${code}</stringProp>
        <stringProp name="Argument.metadata">=</stringProp>
        <boolProp name="HTTPArgument.use_equals">true</boolProp>
        <stringProp name="Argument.name">code</stringProp>
      </elementProp>
    </collectionProp>
  </elementProp>
  <stringProp name="HTTPSampler.domain"></stringProp>
  <stringProp name="HTTPSampler.port"></stringProp>
  <stringProp name="HTTPSampler.protocol"></stringProp>
  <stringProp name="HTTPSampler.path">/api/stock</stringProp>
  <stringProp name="HTTPSampler.method">GET</stringProp>
  <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
  <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
  <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
</HTTPSamplerProxy>
```

Raw JSON body variant (POST/PUT):

```xml
  <elementProp name="HTTPsampler.Arguments" ...>
    <collectionProp name="Arguments.arguments">
      <elementProp name="" elementType="HTTPArgument">
        <boolProp name="HTTPArgument.always_encode">false</boolProp>
        <stringProp name="Argument.value">{"user":"perf","pass":"perf"}</stringProp>
        <stringProp name="Argument.metadata">=</stringProp>
      </elementProp>
    </collectionProp>
  </elementProp>
  ...
  <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
```

## Response Assertion

`Assertion.test_type` is a bit flag: matches=1, contains(regex)=2, NOT=4,
equals=8, substring(plain)=16. `test_field` picks what to check:
`Assertion.response_code`, `Assertion.response_data` (body),
`Assertion.response_message`, `Assertion.response_headers`.

```xml
<ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="Response Assertion" enabled="true">
  <collectionProp name="Asserion.test_strings">
    <stringProp name="0">200</stringProp>
  </collectionProp>
  <stringProp name="Assertion.custom_message"></stringProp>
  <stringProp name="Assertion.test_field">Assertion.response_code</stringProp>
  <boolProp name="Assertion.assume_success">false</boolProp>
  <intProp name="Assertion.test_type">8</intProp>
</ResponseAssertion>
```

## JSON Extractor (JSONPostProcessor)

Capture a value from a response into a variable the next request can use.

```xml
<JSONPostProcessor guiclass="JSONPostProcessorGui" testclass="JSONPostProcessor" testname="JSON Extractor" enabled="true">
  <stringProp name="JSONPostProcessor.referenceNames">token</stringProp>
  <stringProp name="JSONPostProcessor.jsonPathExprs">$.token</stringProp>
  <stringProp name="JSONPostProcessor.match_numbers">1</stringProp>
  <stringProp name="JSONPostProcessor.defaultValues"></stringProp>
</JSONPostProcessor>
```

## Regex Extractor

```xml
<RegexExtractor guiclass="RegexExtractorGui" testclass="RegexExtractor" testname="Regular Expression Extractor" enabled="true">
  <stringProp name="RegexExtractor.useHeaders">false</stringProp>
  <stringProp name="RegexExtractor.refname">token</stringProp>
  <stringProp name="RegexExtractor.regex">"token":"([^"]+)"</stringProp>
  <stringProp name="RegexExtractor.template">$1$</stringProp>
  <stringProp name="RegexExtractor.default"></stringProp>
  <stringProp name="RegexExtractor.match_number">1</stringProp>
</RegexExtractor>
```

## Timers

```xml
<ConstantTimer guiclass="ConstantTimerGui" testclass="ConstantTimer" testname="Constant Timer" enabled="true">
  <stringProp name="ConstantTimer.delay">1000</stringProp>
</ConstantTimer>
```

```xml
<UniformRandomTimer guiclass="UniformRandomTimerGui" testclass="UniformRandomTimer" testname="Uniform Random Timer" enabled="true">
  <stringProp name="ConstantTimer.delay">500</stringProp>
  <stringProp name="RandomTimer.range">1000</stringProp>
</UniformRandomTimer>
```

## CSV Data Set Config

```xml
<CSVDataSet guiclass="TestBeanGUI" testclass="CSVDataSet" testname="CSV Data Set Config" enabled="true">
  <stringProp name="delimiter">,</stringProp>
  <stringProp name="fileEncoding">UTF-8</stringProp>
  <stringProp name="filename">codes.csv</stringProp>
  <boolProp name="ignoreFirstLine">false</boolProp>
  <boolProp name="quotedData">false</boolProp>
  <boolProp name="recycle">true</boolProp>
  <stringProp name="shareMode">shareMode.all</stringProp>
  <boolProp name="stopThread">false</boolProp>
  <stringProp name="variableNames">code</stringProp>
</CSVDataSet>
```

## Listener (ResultCollector)

`guiclass` selects the listener: `SummaryReport`, `StatVisualizer` (Aggregate),
`ViewResultsFullVisualizer` (Results Tree), `TableVisualizer` (Results in Table).
A non-empty `filename` writes results to that path.

```xml
<ResultCollector guiclass="SummaryReport" testclass="ResultCollector" testname="Summary Report" enabled="true">
  <boolProp name="ResultCollector.error_logging">false</boolProp>
  <objProp>
    <name>saveConfig</name>
    <value class="SampleSaveConfiguration">
      <time>true</time><latency>true</latency><timestamp>true</timestamp>
      <success>true</success><label>true</label><code>true</code>
      <message>true</message><threadName>true</threadName><dataType>true</dataType>
      <assertions>true</assertions><subresults>true</subresults>
      <fieldNames>true</fieldNames><assertionsResultsToSave>0</assertionsResultsToSave>
      <bytes>true</bytes><sentBytes>true</sentBytes><url>true</url>
      <threadCounts>true</threadCounts><idleTime>true</idleTime><connectTime>true</connectTime>
    </value>
  </objProp>
  <stringProp name="filename"></stringProp>
</ResultCollector>
```
