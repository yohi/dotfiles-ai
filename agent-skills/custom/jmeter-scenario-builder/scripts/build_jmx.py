#!/usr/bin/env python3
"""build_jmx.py - Generate a runnable Apache JMeter test plan (.jmx) from a spec.

Why this exists:
  A .jmx file is verbose XML where (a) every test element must be followed by a
  sibling <hashTree> that holds its children, and (b) property names such as
  ThreadGroup.num_threads or HTTPSampler.domain must match JMeter exactly.
  Hand-writing it is slow and error-prone. This builder turns a small, readable
  spec (JSON or YAML) into correct XML so callers never emit raw JMeter XML.

Usage:
  python build_jmx.py spec.json -o plan.jmx
  python build_jmx.py spec.yaml -o plan.jmx
  python build_jmx.py --selftest            # build a built-in sample, validate, print to stdout

Spec schema: see ../references/spec-schema.md
Compatible with Python 3.7+ (stdlib only; PyYAML optional for YAML specs).
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET

JMETER_VERSION = "5.6.3"


# ---------------------------------------------------------------------------
# Low-level property helpers. JMeter stores config as typed <*Prop> children.
# ---------------------------------------------------------------------------
def _se(parent, tag, text=None, **attrib):
    el = ET.SubElement(parent, tag, {k: str(v) for k, v in attrib.items()})
    if text is not None:
        el.text = str(text)
    return el


def sprop(parent, name, value=""):
    return _se(parent, "stringProp", "" if value is None else value, name=name)


def bprop(parent, name, value):
    return _se(parent, "boolProp", "true" if value else "false", name=name)


def iprop(parent, name, value):
    return _se(parent, "intProp", value, name=name)


def cprop(parent, name):
    return _se(parent, "collectionProp", name=name)


def eprop(parent, name, element_type, **attrib):
    attribs = {"name": name, "elementType": element_type}
    attribs.update({k: str(v) for k, v in attrib.items()})
    return ET.SubElement(parent, "elementProp", attribs)


# ---------------------------------------------------------------------------
# Node tree. JMeter alternates <Element/> with a sibling <hashTree> holding its
# children. Modelling the plan as nested Nodes lets us emit that pattern once,
# correctly, instead of tracking it by hand at every level.
# ---------------------------------------------------------------------------
class Node:
    def __init__(self, element):
        self.element = element
        self.children = []

    def add(self, child):
        self.children.append(child)
        return child


def _emit(node, parent_hashtree):
    """Append node.element to parent_hashtree, then a <hashTree> for its kids.

    Returns the number of test elements emitted (for the selftest invariant:
    total <hashTree> count must equal element count + 1 top-level hashTree).
    """
    parent_hashtree.append(node.element)
    htree = ET.SubElement(parent_hashtree, "hashTree")
    count = 1
    for child in node.children:
        count += _emit(child, htree)
    return count


# ---------------------------------------------------------------------------
# Element builders. Each returns a bare ET element (no hashTree); the Node tree
# wires up the hashTree nesting in _emit().
# ---------------------------------------------------------------------------
def build_testplan_element(name, comments, variables):
    el = ET.Element("TestPlan", {
        "guiclass": "TestPlanGui", "testclass": "TestPlan",
        "testname": name, "enabled": "true"})
    sprop(el, "TestPlan.comments", comments)
    bprop(el, "TestPlan.functional_mode", False)
    bprop(el, "TestPlan.tearDown_on_shutdown", True)
    bprop(el, "TestPlan.serialize_threadgroups", False)
    udv = eprop(el, "TestPlan.user_defined_variables", "Arguments",
                guiclass="ArgumentsPanel", testclass="Arguments",
                testname="User Defined Variables", enabled="true")
    coll = cprop(udv, "Arguments.arguments")
    for key, value in (variables or {}).items():
        arg = eprop(coll, key, "Argument")
        sprop(arg, "Argument.name", key)
        sprop(arg, "Argument.value", value)
        sprop(arg, "Argument.metadata", "=")
    sprop(el, "TestPlan.user_define_classpath", "")
    return el


def build_threadgroup_element(tg):
    name = tg.get("name", "Thread Group")
    threads = tg.get("threads", 1)
    ramp = tg.get("ramp_up", tg.get("ramp_time", 1))
    duration = tg.get("duration")
    loops = tg.get("loops", 1)
    el = ET.Element("ThreadGroup", {
        "guiclass": "ThreadGroupGui", "testclass": "ThreadGroup",
        "testname": name, "enabled": "true"})
    sprop(el, "ThreadGroup.on_sample_error", tg.get("on_sample_error", "continue"))
    lc = eprop(el, "ThreadGroup.main_controller", "LoopController",
               guiclass="LoopControlPanel", testclass="LoopController",
               testname="Loop Controller", enabled="true")
    bprop(lc, "LoopController.continue_forever", False)
    # When the scheduler runs for a fixed duration, loops must be -1 (infinite)
    # so threads keep firing until time runs out.
    sprop(lc, "LoopController.loops", "-1" if duration else str(loops))
    sprop(el, "ThreadGroup.num_threads", str(threads))
    sprop(el, "ThreadGroup.ramp_time", str(ramp))
    if duration:
        bprop(el, "ThreadGroup.scheduler", True)
        sprop(el, "ThreadGroup.duration", str(duration))
        sprop(el, "ThreadGroup.delay", str(tg.get("startup_delay", "")))
    else:
        bprop(el, "ThreadGroup.scheduler", False)
        sprop(el, "ThreadGroup.duration", "")
        sprop(el, "ThreadGroup.delay", "")
    bprop(el, "ThreadGroup.same_user_on_next_iteration", True)
    return el


def build_http_defaults_element(defaults):
    el = ET.Element("ConfigTestElement", {
        "guiclass": "HttpDefaultsGui", "testclass": "ConfigTestElement",
        "testname": "HTTP Request Defaults", "enabled": "true"})
    args = eprop(el, "HTTPsampler.Arguments", "Arguments",
                 guiclass="HTTPArgumentsPanel", testclass="Arguments",
                 testname="User Defined Variables", enabled="true")
    cprop(args, "Arguments.arguments")
    sprop(el, "HTTPSampler.domain", defaults.get("domain", ""))
    sprop(el, "HTTPSampler.port", defaults.get("port", ""))
    sprop(el, "HTTPSampler.protocol", defaults.get("protocol", ""))
    sprop(el, "HTTPSampler.contentEncoding", defaults.get("content_encoding", ""))
    sprop(el, "HTTPSampler.path", "")
    sprop(el, "HTTPSampler.concurrentPool", "6")
    sprop(el, "HTTPSampler.connect_timeout", defaults.get("connect_timeout", ""))
    sprop(el, "HTTPSampler.response_timeout", defaults.get("response_timeout", ""))
    return el


def build_header_manager_element(headers, testname="HTTP Header Manager"):
    el = ET.Element("HeaderManager", {
        "guiclass": "HeaderPanel", "testclass": "HeaderManager",
        "testname": testname, "enabled": "true"})
    coll = cprop(el, "HeaderManager.headers")
    for key, value in headers.items():
        header = eprop(coll, "", "Header")
        sprop(header, "Header.name", key)
        sprop(header, "Header.value", value)
    return el


def build_http_sampler_element(s):
    name = s.get("name") or (s.get("method", "GET").upper() + " " + s.get("path", "/"))
    method = s.get("method", "GET").upper()
    el = ET.Element("HTTPSamplerProxy", {
        "guiclass": "HttpTestSampleGui", "testclass": "HTTPSamplerProxy",
        "testname": name, "enabled": "true"})
    args = eprop(el, "HTTPsampler.Arguments", "Arguments",
                 guiclass="HTTPArgumentsPanel", testclass="Arguments",
                 testname="User Defined Variables", enabled="true")
    coll = cprop(args, "Arguments.arguments")
    body = s.get("body")
    params = s.get("params") or {}
    raw_body = body is not None and not params
    if raw_body:
        # Raw request body (JSON/text). A single nameless HTTPArgument plus
        # HTTPSampler.postBodyRaw=true is how JMeter stores a raw payload.
        if not isinstance(body, str):
            body = json.dumps(body, ensure_ascii=False)
        arg = eprop(coll, "", "HTTPArgument")
        bprop(arg, "HTTPArgument.always_encode", False)
        sprop(arg, "Argument.value", body)
        sprop(arg, "Argument.metadata", "=")
    else:
        for key, value in params.items():
            arg = eprop(coll, key, "HTTPArgument")
            bprop(arg, "HTTPArgument.always_encode", True)
            sprop(arg, "Argument.value", value)
            sprop(arg, "Argument.metadata", "=")
            bprop(arg, "HTTPArgument.use_equals", True)
            sprop(arg, "Argument.name", key)
    sprop(el, "HTTPSampler.domain", s.get("domain", ""))
    sprop(el, "HTTPSampler.port", s.get("port", ""))
    sprop(el, "HTTPSampler.protocol", s.get("protocol", ""))
    sprop(el, "HTTPSampler.contentEncoding", s.get("content_encoding", ""))
    sprop(el, "HTTPSampler.path", s.get("path", "/"))
    sprop(el, "HTTPSampler.method", method)
    bprop(el, "HTTPSampler.follow_redirects", s.get("follow_redirects", True))
    bprop(el, "HTTPSampler.auto_redirects", s.get("auto_redirects", False))
    bprop(el, "HTTPSampler.use_keepalive", s.get("use_keepalive", True))
    bprop(el, "HTTPSampler.DO_MULTIPART_POST", False)
    sprop(el, "HTTPSampler.embedded_url_re", "")
    sprop(el, "HTTPSampler.connect_timeout", s.get("connect_timeout", ""))
    sprop(el, "HTTPSampler.response_timeout", s.get("response_timeout", ""))
    if raw_body:
        bprop(el, "HTTPSampler.postBodyRaw", True)
    return el


_ASSERT_FIELD = {
    "response_code": "Assertion.response_code",
    "response_data": "Assertion.response_data",
    "response_message": "Assertion.response_message",
    "response_headers": "Assertion.response_headers",
}
# JMeter test_type is a bit flag: matches=1, contains(regex)=2, NOT=4,
# equals=8, substring(plain)=16.
_ASSERT_TYPE = {"matches": 1, "contains": 2, "equals": 8, "substring": 16}


def build_assertion_element(a):
    field = _ASSERT_FIELD.get(a.get("field", "response_code"), "Assertion.response_code")
    flag = _ASSERT_TYPE.get(a.get("type", "equals"), 8)
    if a.get("negate"):
        flag += 4
    el = ET.Element("ResponseAssertion", {
        "guiclass": "AssertionGui", "testclass": "ResponseAssertion",
        "testname": a.get("name", "Response Assertion"), "enabled": "true"})
    # NOTE: the collection name 'Asserion.test_strings' is misspelled in JMeter
    # itself. Keep the typo or JMeter will not read the expected values.
    coll = cprop(el, "Asserion.test_strings")
    values = a.get("values")
    if values is None:
        values = [a.get("value", "200")]
    for idx, value in enumerate(values):
        sprop(coll, str(idx), value)
    sprop(el, "Assertion.custom_message", a.get("message", ""))
    sprop(el, "Assertion.test_field", field)
    bprop(el, "Assertion.assume_success", a.get("assume_success", False))
    iprop(el, "Assertion.test_type", flag)
    return el


def build_json_extractor_element(x):
    el = ET.Element("JSONPostProcessor", {
        "guiclass": "JSONPostProcessorGui", "testclass": "JSONPostProcessor",
        "testname": x.get("name", "JSON Extractor"), "enabled": "true"})
    sprop(el, "JSONPostProcessor.referenceNames", x.get("var", x.get("variable", "var")))
    sprop(el, "JSONPostProcessor.jsonPathExprs", x.get("jsonpath", x.get("expr", "$")))
    sprop(el, "JSONPostProcessor.match_numbers", str(x.get("match", "1")))
    sprop(el, "JSONPostProcessor.defaultValues", x.get("default", ""))
    return el


def build_regex_extractor_element(x):
    el = ET.Element("RegexExtractor", {
        "guiclass": "RegexExtractorGui", "testclass": "RegexExtractor",
        "testname": x.get("name", "Regular Expression Extractor"), "enabled": "true"})
    sprop(el, "RegexExtractor.useHeaders", "false")
    sprop(el, "RegexExtractor.refname", x.get("var", "var"))
    sprop(el, "RegexExtractor.regex", x.get("regex", ""))
    sprop(el, "RegexExtractor.template", x.get("template", "$1$"))
    sprop(el, "RegexExtractor.default", x.get("default", ""))
    sprop(el, "RegexExtractor.match_number", str(x.get("match", "1")))
    return el


def build_timer_element(t):
    if t.get("type") in ("uniform", "uniform_random", "random"):
        el = ET.Element("UniformRandomTimer", {
            "guiclass": "UniformRandomTimerGui", "testclass": "UniformRandomTimer",
            "testname": "Uniform Random Timer", "enabled": "true"})
        sprop(el, "ConstantTimer.delay", str(t.get("delay", 0)))
        sprop(el, "RandomTimer.range", str(t.get("range", 1000)))
        return el
    el = ET.Element("ConstantTimer", {
        "guiclass": "ConstantTimerGui", "testclass": "ConstantTimer",
        "testname": "Constant Timer", "enabled": "true"})
    sprop(el, "ConstantTimer.delay", str(t.get("delay", 1000)))
    return el


def build_csv_element(c):
    el = ET.Element("CSVDataSet", {
        "guiclass": "TestBeanGUI", "testclass": "CSVDataSet",
        "testname": c.get("name", "CSV Data Set Config"), "enabled": "true"})
    variables = c.get("variables", "")
    if isinstance(variables, list):
        variables = ",".join(variables)
    sprop(el, "delimiter", c.get("delimiter", ","))
    sprop(el, "fileEncoding", c.get("encoding", "UTF-8"))
    sprop(el, "filename", c.get("filename", ""))
    bprop(el, "ignoreFirstLine", c.get("ignore_first_line", False))
    bprop(el, "quotedData", c.get("quoted", False))
    bprop(el, "recycle", c.get("recycle", True))
    sprop(el, "shareMode", c.get("share_mode", "shareMode.all"))
    bprop(el, "stopThread", c.get("stop_thread", False))
    sprop(el, "variableNames", variables)
    return el


_LISTENER_GUI = {
    "summary": ("SummaryReport", "Summary Report"),
    "aggregate": ("StatVisualizer", "Aggregate Report"),
    "tree": ("ViewResultsFullVisualizer", "View Results Tree"),
    "table": ("TableVisualizer", "View Results in Table"),
}
_SAVE_FLAGS = [
    ("time", True), ("latency", True), ("timestamp", True), ("success", True),
    ("label", True), ("code", True), ("message", True), ("threadName", True),
    ("dataType", True), ("encoding", False), ("assertions", True),
    ("subresults", True), ("responseData", False), ("samplerData", False),
    ("xml", False), ("fieldNames", True), ("responseHeaders", False),
    ("requestHeaders", False), ("responseDataOnError", False),
    ("saveAssertionResultsFailureMessage", True), ("assertionsResultsToSave", 0),
    ("bytes", True), ("sentBytes", True), ("url", True), ("threadCounts", True),
    ("idleTime", True), ("connectTime", True),
]


def build_listener_element(spec):
    if isinstance(spec, str):
        key, filename = spec, ""
    else:
        key, filename = spec.get("type", "summary"), spec.get("filename", "")
    gui, testname = _LISTENER_GUI.get(key, _LISTENER_GUI["summary"])
    el = ET.Element("ResultCollector", {
        "guiclass": gui, "testclass": "ResultCollector",
        "testname": testname, "enabled": "true"})
    bprop(el, "ResultCollector.error_logging", False)
    obj = ET.SubElement(el, "objProp")
    ET.SubElement(obj, "name").text = "saveConfig"
    value = ET.SubElement(obj, "value", {"class": "SampleSaveConfiguration"})
    for flag, default in _SAVE_FLAGS:
        if isinstance(default, bool):
            ET.SubElement(value, flag).text = "true" if default else "false"
        else:
            ET.SubElement(value, flag).text = str(default)
    sprop(el, "filename", filename)
    return el


# ---------------------------------------------------------------------------
# Assembly: turn a spec dict into the Node tree, then into an XML document.
# ---------------------------------------------------------------------------
def build_tree(spec):
    tp = spec.get("test_plan", {})
    root_el = build_testplan_element(
        tp.get("name", "Test Plan"),
        tp.get("comments", ""),
        spec.get("variables") or tp.get("variables"))
    root = Node(root_el)
    if spec.get("defaults"):
        root.add(Node(build_http_defaults_element(spec["defaults"])))
    if spec.get("headers"):
        root.add(Node(build_header_manager_element(spec["headers"])))
    for csv in (spec.get("csv_data") or []):
        root.add(Node(build_csv_element(csv)))
    for tg in spec.get("thread_groups", []):
        tg_node = Node(build_threadgroup_element(tg))
        for csv in (tg.get("csv_data") or []):
            tg_node.add(Node(build_csv_element(csv)))
        if tg.get("headers"):
            tg_node.add(Node(build_header_manager_element(tg["headers"])))
        for s in tg.get("samplers", []):
            s_node = Node(build_http_sampler_element(s))
            if s.get("headers"):
                s_node.add(Node(build_header_manager_element(s["headers"])))
            for a in (s.get("assertions") or []):
                s_node.add(Node(build_assertion_element(a)))
            for x in (s.get("extractors") or []):
                if x.get("type") == "regex":
                    s_node.add(Node(build_regex_extractor_element(x)))
                else:
                    s_node.add(Node(build_json_extractor_element(x)))
            if s.get("timer"):
                s_node.add(Node(build_timer_element(s["timer"])))
            tg_node.add(s_node)
        if tg.get("timer"):
            tg_node.add(Node(build_timer_element(tg["timer"])))
        root.add(tg_node)
    for listener in (spec.get("listeners") or []):
        root.add(Node(build_listener_element(listener)))
    return root


def build_document(spec):
    root = ET.Element("jmeterTestPlan", {
        "version": "1.2", "properties": "5.0", "jmeter": JMETER_VERSION})
    top = ET.SubElement(root, "hashTree")
    count = _emit(build_tree(spec), top)
    return root, count


def _indent(elem, level=0):
    """Pretty-print in place. ET.indent() is 3.9+, so we ship the classic recipe
    to stay compatible with Python 3.7 environments."""
    pad = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad + "  "
        child = None
        for child in elem:
            _indent(child, level + 1)
        if child is not None and (not child.tail or not child.tail.strip()):
            child.tail = pad
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = pad


def to_xml(root):
    _indent(root)
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def load_spec(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError:
            raise SystemExit(
                "Spec is not valid JSON and PyYAML is not installed. "
                "Provide a JSON spec, or run: pip install pyyaml")
        return yaml.safe_load(text)


SAMPLE_SPEC = {
    "test_plan": {"name": "Sample API Load Test",
                  "comments": "Generated by build_jmx.py --selftest"},
    "variables": {"BASE_URL": "example.com"},
    "defaults": {"protocol": "https", "domain": "${BASE_URL}", "port": "443"},
    "headers": {"Content-Type": "application/json", "Accept": "application/json"},
    "thread_groups": [{
        "name": "Stock API",
        "threads": 100, "ramp_up": 30, "duration": 300,
        "csv_data": [{"filename": "codes.csv", "variables": ["code"]}],
        "samplers": [
            {"name": "POST /login", "method": "POST", "path": "/api/login",
             "body": {"user": "perf", "pass": "perf"},
             "assertions": [{"field": "response_code", "type": "equals", "value": "200"}],
             "extractors": [{"type": "json", "var": "token", "jsonpath": "$.token"}]},
            {"name": "GET /stock", "method": "GET", "path": "/api/stock",
             "params": {"code": "${code}"},
             "headers": {"Authorization": "Bearer ${token}"},
             "assertions": [
                 {"field": "response_code", "type": "equals", "value": "200"},
                 {"field": "response_data", "type": "substring", "value": "quantity"}],
             "timer": {"type": "uniform", "delay": 500, "range": 1000}},
        ],
    }],
    "listeners": ["summary", "aggregate"],
}


def main():
    ap = argparse.ArgumentParser(
        description="Generate a JMeter .jmx test plan from a JSON/YAML spec.")
    ap.add_argument("spec", nargs="?", help="Path to spec (.json/.yaml/.yml)")
    ap.add_argument("-o", "--output", help="Output .jmx path (default: stdout)")
    ap.add_argument("--selftest", action="store_true",
                    help="Build the built-in sample, validate structure, print to stdout")
    args = ap.parse_args()

    if args.selftest:
        spec = SAMPLE_SPEC
    elif args.spec:
        spec = load_spec(args.spec)
    else:
        ap.error("a spec path is required (or use --selftest)")

    root, node_count = build_document(spec)
    xml = to_xml(root)

    # Well-formedness check: re-parse what we produced.
    ET.fromstring(xml)
    # Structural invariant: every test element is followed by exactly one
    # <hashTree>, plus the single top-level hashTree.
    hashtree_count = xml.count("<hashTree")
    if hashtree_count != node_count + 1:
        raise SystemExit(
            "Structural check failed: %d hashTree vs %d elements + 1"
            % (hashtree_count, node_count))

    if args.selftest:
        sys.stderr.write(
            "OK: well-formed; %d elements, %d hashTree nodes\n"
            % (node_count, hashtree_count))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(xml)
        sys.stderr.write("Wrote %s\n" % args.output)
    else:
        sys.stdout.write(xml)


if __name__ == "__main__":
    main()
