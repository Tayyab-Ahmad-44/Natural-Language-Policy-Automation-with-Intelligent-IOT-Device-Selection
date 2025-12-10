import os
import json
from groq import Groq
import schemas
from load_dotenv import load_dotenv

load_dotenv()

# Configure Groq
# In a real app, use env vars. For this demo, we assume the user has set up their environment.
# If API key is missing, this will fail.

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def parse_policy_with_llm(policy_text: str, devices_data: list) -> schemas.PolicyResponseLLM:
    """
    Uses Gemini to parse natural language policy into structured data.
    """
    
    # Construct prompt
    devices_json = json.dumps(devices_data, indent=2)
    
    prompt = f"""
    You are an intelligent home automation assistant.
    Your task is to parse a natural language policy and convert it into a structured execution plan.

    Available Devices and Capabilities:
    {devices_json}

    User Policy: "{policy_text}"

    Instructions:
    1. Identify the time window (start_time and end_time) in HH:MM 24-hour format. If not specified, assume 00:00 to 23:59.
    2. Identify which devices and capabilities are relevant to the policy.
    3. For each relevant capability, generate the necessary arguments (args) based on the input_schema.
    4. Return a JSON object with the following structure:
    {{
        "time_window": {{
            "from_time": "HH:MM",
            "to_time": "HH:MM"
        }},
        "execution_plan": [
            {{
                "device": "Device Name",
                "capability": "Capability Name",
                "args": {{ ... }}
            }}
        ]
    }}
    
    If the policy is ambiguous or no device matches, do your best to infer or return an empty plan.
    ONLY return the JSON string, no markdown formatting.
    """
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        text = response.choices[0].message.content.strip()
        
        # Clean up potential markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
            
        data = json.loads(text)
        return schemas.PolicyResponseLLM(**data)
        
    except Exception as e:
        print(f"LLM Error: {e}")
        # Fallback or re-raise
        return schemas.PolicyResponseLLM(
            execution_plan=[],
            time_window={"from_time": "00:00", "to_time": "23:59"}
        )

def break_down_task(task_description: str, devices_data: list) -> list:
    """
    Uses Groq to analyze a high-level task and return a list of structured policies.

    Each returned policy should be a dict with at least:
      - original_text: the natural-language description for the policy
      - time_window: {"from_time": "HH:MM", "to_time": "HH:MM"}
      - execution_plan: [{"device": "Device Name", "capability": "Capability Name", "args": {...}}]

    The LLM should use the available device capabilities when creating the execution plans.
    """
    devices_json = json.dumps(devices_data, indent=2)

    prompt = f"""
    You are an intelligent home automation assistant.
    Your task is to analyze a high-level user *task* (not already-written policies) and produce a list of concrete, structured policies
    that, when executed, will achieve the task using the provided devices and their capabilities.

    Available Devices and Capabilities:
    {devices_json}

    User Task: "{task_description}"

    Instructions:
    1. Understand the user's intent and determine what concrete actions are required.
    2. For each required action, create a policy object with these fields:
       - "original_text": a short natural-language description of the policy
       - "time_window": {{"from_time": "HH:MM", "to_time": "HH:MM"}} (use full-day 00:00-23:59 if no specific time)
       - "execution_plan": a list of actions, where each action maps to a device capability and includes any required "args" based on the capability's input_schema
    3. Use the available devices and their capabilities to populate the execution_plan. If multiple devices can fulfil the same role, choose the most appropriate one.
    4. Return a JSON object with a single key "policies" whose value is the list of policy objects.

        Example Output:
        {{
            "policies": [
                {{
                    "original_text": "Turn off living room lights at 20:00",
                    "time_window": {{"from_time": "20:00", "to_time": "20:00"}},
                    "execution_plan": [
                        {{"device": "Living Room Light", "capability": "Turn Off", "args": {{}}}}
                    ]
                }}
            ]
        }}

    ONLY return the JSON string, no markdown formatting.
    """

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        text = response.choices[0].message.content.strip()

        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]

        data = json.loads(text)
        # Expecting a dict with key "policies"
        return data.get("policies", [])

    except Exception as e:
        print(f"LLM Task Breakdown Error: {e}")
        return []
