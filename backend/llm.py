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

def break_down_task(task_description: str, devices_data: list) -> list[str]:
    """
    Uses Groq to break down a high-level task into a list of natural language policy rules.
    """
    devices_json = json.dumps(devices_data, indent=2)
    
    prompt = f"""
    You are an intelligent home automation assistant.
    Your task is to break down a high-level user task into a list of specific, actionable natural language policy rules.

    Available Devices and Capabilities:
    {devices_json}

    User Task: "{task_description}"

    Instructions:
    1. Analyze the task and determine what specific actions need to be taken.
    2. Generate a list of natural language policy rules. Each rule should be specific enough to be parsed later into an execution plan (device + capability + args + time).
    3. If the task implies a schedule (e.g., "at night"), include time constraints in the rules.
    4. Return a JSON object with a "rules" key containing the list of strings.
    
    Example Output:
    {{
        "rules": [
            "Turn on the living room light at 18:00",
            "Lock the front door at 22:00"
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
        return data.get("rules", [])
        
    except Exception as e:
        print(f"LLM Task Breakdown Error: {e}")
        return []
