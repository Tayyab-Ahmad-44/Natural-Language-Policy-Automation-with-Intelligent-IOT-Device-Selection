import json
from typing import List

from pydantic import ValidationError

import dag_utils
import llm_provider
import schemas

# Bounded retry budget for DAG generation: 1 initial attempt + up to 2
# corrections. Kept small -- each retry costs a full round trip and re-sends
# the whole prompt, so this trades a little latency for rejecting malformed
# or ungrounded output instead of silently degrading to an empty DAG.
MAX_DAG_GENERATION_ATTEMPTS = 3

# ──────────────────────────────────────────────────────────────────
# Few-shot examples for DAG generation
# ──────────────────────────────────────────────────────────────────

DAG_EXAMPLES = """
EXAMPLE 1 — Pure parallel (all independent actions):
User Policy: "At 8 PM, set living room lights to purple, play party hits at volume 80, and set thermostat fan to on."
Output:
{
  "time_window": {"from_time": "20:00", "to_time": "20:00"},
  "execution_dag": {
    "nodes": [
      {"id": "step_1", "device": "Living Room Light", "capability": "Set Color", "args": {"hex": "#800080"}, "dependencies": [], "condition": null, "on_failure": "ignore"},
      {"id": "step_2", "device": "Smart Speaker", "capability": "Play Music", "args": {"playlist": "Party Hits"}, "dependencies": [], "condition": null, "on_failure": "ignore"},
      {"id": "step_3", "device": "Smart Speaker", "capability": "Set Volume", "args": {"level": 80}, "dependencies": ["step_2"], "condition": {"type": "on_success"}, "on_failure": "ignore"},
      {"id": "step_4", "device": "Thermostat", "capability": "Fan Control", "args": {"state": "on"}, "dependencies": [], "condition": null, "on_failure": "ignore"}
    ]
  }
}

EXAMPLE 2 — Sequential with value-based condition:
User Policy: "Read the temperature sensor, if it exceeds 30 degrees then activate the cooling fan at 2000 RPM and flash the warning light yellow for 30 seconds."
Output:
{
  "time_window": {"from_time": "00:00", "to_time": "23:59"},
  "execution_dag": {
    "nodes": [
      {"id": "step_1", "device": "Temp Sensor", "capability": "Read", "args": {}, "dependencies": [], "condition": null, "on_failure": "halt_branch"},
      {"id": "step_2", "device": "Cooling Fan", "capability": "Set Speed", "args": {"rpm": 2000}, "dependencies": ["step_1"], "condition": {"type": "on_value", "source_node_id": "step_1", "field": "temp", "operator": ">", "value": 30}, "on_failure": "ignore"},
      {"id": "step_3", "device": "Warning Light", "capability": "Flash", "args": {"color": "yellow", "duration": 30}, "dependencies": ["step_1"], "condition": {"type": "on_value", "source_node_id": "step_1", "field": "temp", "operator": ">", "value": 30}, "on_failure": "ignore"}
    ]
  }
}

EXAMPLE 3 — Mixed DAG (sequential + parallel + conditional):
User Policy: "At 11 PM, lock the front door and close the garage door. Once the front door is locked, arm the security camera to record for 60 seconds. Also turn off all lights."
Output:
{
  "time_window": {"from_time": "23:00", "to_time": "23:00"},
  "execution_dag": {
    "nodes": [
      {"id": "step_1", "device": "Front Door Lock", "capability": "Lock", "args": {}, "dependencies": [], "condition": null, "on_failure": "halt_branch"},
      {"id": "step_2", "device": "Garage Door", "capability": "Close", "args": {}, "dependencies": [], "condition": null, "on_failure": "skip_dependents"},
      {"id": "step_3", "device": "Security Camera", "capability": "Record", "args": {"duration": 60}, "dependencies": ["step_1"], "condition": {"type": "on_success"}, "on_failure": "ignore"},
      {"id": "step_4", "device": "Living Room Light", "capability": "Turn Off", "args": {}, "dependencies": [], "condition": null, "on_failure": "ignore"}
    ]
  }
}

EXAMPLE 4 — Camera image analysis with VLM:
User Policy: "If the security camera sees smoke or fire, turn on the warning light red and start recording for 60 seconds."
Output:
{
  "time_window": {"from_time": "00:00", "to_time": "23:59"},
  "execution_dag": {
    "nodes": [
      {"id": "step_1", "device": "Security Camera", "capability": "Analyze Scene", "args": {"prompt": "Detect whether smoke or fire is visible", "target_labels": ["smoke", "fire"]}, "dependencies": [], "condition": null, "on_failure": "halt_branch"},
      {"id": "step_2", "device": "Warning Light", "capability": "Solid", "args": {"color": "red"}, "dependencies": ["step_1"], "condition": {"type": "all", "conditions": [{"type": "on_value", "source_node_id": "step_1", "field": "detected", "operator": "==", "value": true}, {"type": "on_value", "source_node_id": "step_1", "field": "confidence", "operator": ">=", "value": 0.7}]}, "on_failure": "ignore"},
      {"id": "step_3", "device": "Security Camera", "capability": "Record", "args": {"duration": 60}, "dependencies": ["step_1"], "condition": {"type": "all", "conditions": [{"type": "on_value", "source_node_id": "step_1", "field": "detected", "operator": "==", "value": true}, {"type": "on_value", "source_node_id": "step_1", "field": "confidence", "operator": ">=", "value": 0.7}]}, "on_failure": "ignore"}
    ]
  }
}
"""

DAG_SCHEMA_INSTRUCTIONS = """
EXECUTION DAG STRUCTURE:
The execution_dag contains "nodes" — each node is a device action. Nodes can depend on other nodes forming a Directed Acyclic Graph (DAG).

Each node has:
- "id": unique string identifier (e.g. "step_1", "step_2")
- "device": the device name (must match an available device exactly)
- "capability": the capability name (must match exactly)
- "args": arguments dict matching the capability's input_schema
- "dependencies": list of node IDs that must complete before this node executes. Empty list = root node (executes immediately in parallel with other root nodes)
- "condition": when this node should execute relative to its dependencies:
    - null or omitted: execute when ALL dependencies succeed (default behavior)
    - {"type": "on_success"}: same as null — execute when all deps succeed
    - {"type": "on_failure"}: execute only if a dependency FAILED
    - {"type": "on_value", "source_node_id": "step_X", "field": "fieldname", "operator": ">", "value": 30}: execute only if a specific field in a dependency's response meets the condition. Operators: ">", "<", "==", "!=", ">=", "<=", "contains"
    - {"type": "all", "conditions": [...]}: execute only when every nested condition is true
    - {"type": "any", "conditions": [...]}: execute when at least one nested condition is true
- "on_failure": what happens if THIS node fails:
    - "halt_branch": all nodes that depend on this one (and their dependents) are skipped. Use for CRITICAL actions (emergency stops, locks, sensors providing data for decisions)
    - "skip_dependents": only direct dependents are skipped, not transitive ones
    - "ignore": treat failure as success — dependents still execute. Use for non-critical/ambient actions (music, lights in non-emergency contexts)

VLM CAMERA CAPABILITIES:
- If an available camera capability has method "VLM", treat it as a data-producing visual sensor node.
- Use a short "prompt" arg that states exactly what to look for in the image.
- Optional VLM args include: "target_labels"/"labels", "image_url", "image_base64", "video_path", "video_url", "video_frame_count", "video_frame_interval_seconds", "source_method", "capture_args", "provider", and "model".
- VLM responses expose JSON fields for conditions: "detected" (boolean), "labels" (list), "summary" (string), "confidence" (0-1), and "observations" (object).
- Downstream actions that depend on visual evidence should use on_value conditions against fields like "detected", "confidence", or "labels".
- For fire/safety detections, prefer an "all" condition requiring both detected == true and confidence >= 0.7 before triggering actions.

RULES FOR BUILDING THE DAG:
1. Actions that are INDEPENDENT should have no dependencies (empty list) — they run in parallel
2. Action B depends on Action A if: B needs A's result (sensor reading), B should happen AFTER A (lock door THEN arm camera), or B only makes sense if A succeeds
3. Multiple nodes can depend on the same parent — they fan out in parallel after the parent completes
4. Multiple nodes can be listed as dependencies of one node — it waits for ALL of them (fan-in)
5. NEVER create cycles (A depends on B, B depends on A)
6. Choose on_failure based on context: emergency/safety policies → "halt_branch", ambient/comfort → "ignore", general → "skip_dependents"
"""


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _ground_dag_nodes(dag: schemas.ExecutionDAG, devices_data: list) -> List[str]:
    """Verify every node's (device, capability) pair exists in the live device
    catalog. Returns one error string per ungrounded node, empty if all nodes
    reference real devices/capabilities.
    """
    catalog = {d["name"]: {c["name"] for c in d.get("capabilities", [])} for d in devices_data}
    errors: List[str] = []
    for node in dag.nodes:
        if node.device not in catalog:
            errors.append(
                f"Node '{node.id}': device '{node.device}' does not exist. "
                f"Available devices: {sorted(catalog)}"
            )
            continue
        if node.capability not in catalog[node.device]:
            errors.append(
                f"Node '{node.id}': capability '{node.capability}' does not exist on device "
                f"'{node.device}'. Available capabilities for '{node.device}': {sorted(catalog[node.device])}"
            )
    return errors


def _validate_and_ground(parsed: schemas.PolicyResponseLLM, devices_data: list) -> List[str]:
    """Structural + grounding checks run before a generated DAG is accepted.
    An empty node list is left alone -- the prompt explicitly allows an empty
    DAG for ambiguous policies, so that's not a failure to retry on.
    """
    if not parsed.execution_dag.nodes:
        return []
    errors = list(dag_utils.validate_dag(parsed.execution_dag).errors)
    errors += _ground_dag_nodes(parsed.execution_dag, devices_data)
    return errors


def _append_correction(messages: list, assistant_text: str, errors: List[str]) -> list:
    """Feed the model its own bad output plus the specific errors, so the
    retry is a targeted correction rather than a blind re-ask.
    """
    correction = (
        "Your previous response had the following problem(s):\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n\nFix ONLY these problems and return the corrected JSON object. "
          "ONLY return the JSON string, no markdown formatting, no explanation."
    )
    return messages + [
        {"role": "assistant", "content": assistant_text},
        {"role": "user", "content": correction},
    ]


def _empty_policy_response() -> schemas.PolicyResponseLLM:
    return schemas.PolicyResponseLLM(
        execution_dag=schemas.ExecutionDAG(nodes=[]),
        time_window={"from_time": "00:00", "to_time": "23:59"},
    )


def parse_policy_with_llm(
    policy_text: str,
    devices_data: list,
    max_attempts: int = MAX_DAG_GENERATION_ATTEMPTS,
) -> schemas.PolicyResponseLLM:
    """
    Uses the configured LLM to parse a natural language policy into a
    structured DAG execution plan.

    Every candidate response is schema-validated (pydantic) and grounded
    (every node's device/capability must exist in devices_data) before being
    accepted. On failure, the specific error is fed back to the model as
    correction context for up to `max_attempts` total tries. If every attempt
    fails, falls back to an empty DAG rather than raising.
    """
    devices_json = json.dumps(devices_data, indent=2)

    prompt = f"""You are an intelligent IoT automation assistant.
Your task is to parse a natural language policy and convert it into a structured execution DAG (Directed Acyclic Graph).

Available Devices and Capabilities:
{devices_json}

{DAG_SCHEMA_INSTRUCTIONS}

{DAG_EXAMPLES}

User Policy: "{policy_text}"

Instructions:
1. Identify the time window (from_time and to_time) in HH:MM 24-hour format. If not specified, use 00:00 to 23:59.
2. Analyze the policy to determine which devices/capabilities are needed and how they relate to each other.
3. Build an execution DAG: identify which actions are independent (parallel), which depend on others (sequential), and which have conditions.
4. Return a JSON object with "time_window" and "execution_dag" keys.

If the policy is ambiguous or no device matches, do your best to infer or return an empty DAG.
ONLY return the JSON string, no markdown formatting, no explanation.
"""

    messages: list = [{"role": "user", "content": prompt}]
    last_errors: List[str] = []

    for attempt in range(1, max_attempts + 1):
        try:
            response = llm_provider.create_chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            )
            text = response.choices[0].message.content.strip()
        except Exception as e:
            # Transport/provider failure -- resending the same messages won't
            # change the outcome, so don't burn retries on it.
            print(f"LLM Error (attempt {attempt}/{max_attempts}): {e}")
            return _empty_policy_response()

        cleaned = _strip_markdown_fences(text)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_errors = [f"Response was not valid JSON ({e})."]
            messages = _append_correction(messages, text, last_errors)
            continue

        if not isinstance(data, dict):
            last_errors = [f"Response must be a JSON object with \"time_window\" and \"execution_dag\" keys, got {type(data).__name__}."]
            messages = _append_correction(messages, text, last_errors)
            continue

        try:
            parsed = schemas.PolicyResponseLLM(**data)
        except ValidationError as e:
            last_errors = [f"Response did not match the required schema: {e}"]
            messages = _append_correction(messages, text, last_errors)
            continue

        errors = _validate_and_ground(parsed, devices_data)
        if not errors:
            return parsed

        last_errors = errors
        messages = _append_correction(messages, text, errors)

    print(f"LLM DAG generation failed after {max_attempts} attempt(s): {last_errors}")
    return _empty_policy_response()


def break_down_task(task_description: str, devices_data: list) -> list:
    """
    Uses Groq LLM to break down a high-level task into multiple structured policies,
    each with its own execution DAG.
    """
    devices_json = json.dumps(devices_data, indent=2)

    prompt = f"""You are an intelligent IoT automation assistant.
Your task is to analyze a high-level user task and produce a list of concrete, structured policies.
Each policy should have its own execution DAG (Directed Acyclic Graph).

Available Devices and Capabilities:
{devices_json}

{DAG_SCHEMA_INSTRUCTIONS}

{DAG_EXAMPLES}

User Task: "{task_description}"

Instructions:
1. Break the task into logical, separate policies (each one can be scheduled independently).
2. For each policy, create:
   - "original_text": a short natural-language description
   - "time_window": {{"from_time": "HH:MM", "to_time": "HH:MM"}} (use 00:00-23:59 if no specific time)
   - "execution_dag": a DAG structure with nodes, dependencies, conditions, and failure strategies
3. Return a JSON object with a single key "policies" whose value is the list of policy objects.

Example Output:
{{
    "policies": [
        {{
            "original_text": "Turn off living room lights at 20:00",
            "time_window": {{"from_time": "20:00", "to_time": "20:00"}},
            "execution_dag": {{
                "nodes": [
                    {{"id": "step_1", "device": "Living Room Light", "capability": "Turn Off", "args": {{}}, "dependencies": [], "condition": null, "on_failure": "ignore"}}
                ]
            }}
        }}
    ]
}}

ONLY return the JSON string, no markdown formatting, no explanation.
"""

    try:
        response = llm_provider.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2048,
        )
        text = response.choices[0].message.content.strip()

        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        data = json.loads(text.strip())
        return data.get("policies", [])

    except Exception as e:
        print(f"LLM Task Breakdown Error: {e}")
        return []


# ──────────────────────────────────────────────────────────────────
# Device auto-discovery: map an arbitrary catalog response → our schema
# ──────────────────────────────────────────────────────────────────

DEVICE_TARGET_SCHEMA = """
Our system stores devices in this EXACT JSON shape:
{
  "devices": [
    {
      "name": "Living Room Camera",          // unique, human-readable name
      "type": "camera",                        // infer best fit: camera, light, lock, sensor, thermostat, speaker, appliance, alarm, hvac, pump, motor, door, ...
      "capabilities": [
        {
          "name": "Snapshot",                  // short action/command name
          "url": "http://host:port/path",      // FULL absolute URL that triggers this capability
          "method": "GET",                     // one of: GET, POST, PUT, SSE, VLM
          "input_schema": {"duration": "int"}  // dict of body arguments the action accepts ({} if none)
        }
      ]
    }
  ]
}
"""


def map_devices_from_response(raw_response: str, source_endpoint: str = "") -> list:
    """
    Uses the LLM to map an arbitrary external device-catalog JSON response into
    our internal Device/Capability schema. Returns a list of schemas.DeviceCreate.
    """
    # Guard the token budget against very large payloads.
    snippet = raw_response[:12000]

    prompt = f"""You are an IoT device-registry integration assistant.
A user pointed our system at an external device-catalog endpoint and we fetched its raw response.
Map that arbitrary response into OUR internal schema so the devices can be stored.

{DEVICE_TARGET_SCHEMA}

MAPPING RULES:
1. Identify every distinct physical device described in the response.
2. Give each device a clear, unique "name" and infer a sensible "type".
3. Map each controllable action / endpoint / command of a device into one capability entry.
4. "url" MUST be a full absolute URL. If the response only contains relative paths, join them with the origin of the source endpoint: {source_endpoint or "(unknown — keep paths as given)"}
5. Choose "method" from GET, POST, PUT, SSE, VLM. Use SSE for streaming sensor feeds, VLM for camera scene-analysis capabilities, GET for reads/status, POST for actions/commands.
6. "input_schema" is a dict describing the JSON body arguments the action accepts ({{}} if none). Infer it from any parameter/argument lists present.
7. If the structure is ambiguous, make a reasonable best-effort mapping rather than returning nothing.

Raw response from {source_endpoint or "the endpoint"}:
{snippet}

Return ONLY a JSON object of the form {{"devices": [...]}}. No markdown, no explanation.
"""

    try:
        response = llm_provider.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
        )
        text = response.choices[0].message.content.strip()

        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        data = json.loads(text.strip())
        devices = []
        for d in data.get("devices", []):
            try:
                devices.append(schemas.DeviceCreate(**d))
            except Exception as ex:
                print(f"Skipping malformed device from discovery: {ex}")
        return devices

    except Exception as e:
        print(f"LLM Device Mapping Error: {e}")
        return []
