import os
import json
from datetime import datetime
from pathlib import Path

OUTPUT_ROOT=Path(__file__).parent.parent / "outputs" / "accounts"

def build_system_prompt(memo:dict)-> str:
    """Build Clara's instruction pompt from account memo"""
    company = memo.get("company_name", "our company")
    bh=memo.get("business_hours") or {}
    days = bh.get("days") or "Monday to Friday"
    start = bh.get("start") or "9:00 AM"
    end = bh.get("end") or "5:00 PM"
    tz = bh.get("timezone") or "local time"

    routing = memo.get("emergency_routing_rules") or {}
    emergency_contact = routing.get("primary_contact") or "our on-call team"
    emergency_phone = routing.get("phone_number") or "[ON_CALL_NUMBER]"
    transfer_rules = memo.get("call_transfer_rules") or {}
    timeout = transfer_rules.get("timeout_seconds") or 60

    pricing = memo.get("pricing") or {}
    service_fee = pricing.get("service_call_fee") or None
    hourly = pricing.get("hourly_rate") or None
    mention_pricing = pricing.get("mention_to_caller") or False

    special_clients = memo.get("special_clients") or []
    emergencies = memo.get("emergency_definition") or []
    constraints = memo.get("integration_constraints") or []
    pricing_section=""
    if service_fee:
        pricing_section=f""" # PRICING (only mention if caller asks) 
- Service call fee: {service_fee}
- Hourly rate: {hourly}
- Do NOT mention this on every call. Only when asked.
"""

    special_section = ""
    if special_clients:
        clients_list = "\n".join([
    f"- {c if isinstance(c, str) else c.get('company_name', str(c))}" 
    for c in special_clients
])
        special_section = f"""
# SPECIAL CLIENTS (patch through after hours)
{clients_list}
If any of these clients call after hours mentioning an emergency,
transfer immediately to {emergency_phone}.
"""

    constraints_section = ""
    if constraints:
        c_list = "\n".join([f"- {c}" for c in constraints])
        constraints_section = f"""
# SYSTEM CONSTRAINTS (never mention to caller)
{c_list}
"""
    prompt = f"""
        # IDENTITY
You are Clara, the professional AI voice assistant for {company}.
You handle inbound calls warmly and efficiently.
Never mention you are an AI unless directly asked.
Never mention "function calls", "tools", or "systems" to callers.
Keep responses short and clear — this is a phone call, not an email.

# BUSINESS HOURS
{days}, {start} to {end} {tz}

# WHAT COUNTS AS AN EMERGENCY
{chr(10).join([f"- {e}" for e in emergencies]) if emergencies else "- Active safety hazards requiring immediate attention"}

{pricing_section}
{special_section}
{constraints_section}

---
# BUSINESS HOURS FLOW

Step 1 - Greeting
Say: "Thank you for calling {company}, this is Clara. How can I help you today?"

Step 2 - Understand Purpose
Listen carefully. Is this an emergency, service request, or inquiry?
Ask one focused question if needed.

Step 3 - Collect Caller Info
Ask: "May I get your name and the best number to reach you?"
Always repeat the number back to confirm.

Step 4 - Transfer
Say: "Let me connect you with the right person, please hold."
Transfer to {emergency_contact} at {emergency_phone}.
Wait up to {timeout} seconds.

Step 5 - If Transfer Fails
Say: "I wasn't able to reach someone right now, but your information
has been noted and someone will call you back shortly."
Log: caller name, number, issue, timestamp.

Step 6 - Wrap Up
Ask: "Is there anything else I can help you with?"
If no: "Thank you for calling {company}. Have a great day!"

---

# AFTER HOURS FLOW

Step 1 - Greeting
Say: "Thank you for calling {company}. Our office is currently closed.
We are open {days} from {start} to {end} {tz}.
This is Clara — I'm here to help. What are you calling about?"

Step 2 - Understand Purpose
Listen. Determine if this is an emergency or non-emergency.

Step 3a - IF EMERGENCY
Ask: "Is this an active emergency right now?"
If yes:
Say: "I'm going to get someone on the line for you right away.
Can I quickly get your name, phone number, and the address
where the issue is?"
Collect: full name, callback number, service address.
Transfer to {emergency_phone}.
If transfer fails after {timeout} seconds:
Say: "I wasn't able to reach our team directly, but your call
has been flagged as urgent. Someone will call you back
at your number very shortly."
Log everything immediately.

Step 3b - IF NOT EMERGENCY
Say: "I understand. Let me make sure the right person
follows up with you during business hours."
Collect: name, phone number, brief description of issue.
Confirm: "We will follow up with you on the next business day."

Step 4 - Wrap Up
Ask: "Is there anything else I can help you with?"
If no: "Thank you for calling {company}. Have a good night!"

---

# RULES - ALWAYS FOLLOW
- Never ask more than 2 questions at once
- Never mention tools, functions, systems or databases
- Always repeat phone numbers back to confirm
- Be warm and calm, especially with stressed callers
- Never promise exact arrival times
- If unsure: "Let me make sure the right person follows up with you"
"""
    return prompt.strip()

def build_agent_spec(memo: dict, version: str = "v1") -> dict:
    """Build complete agent spec from memo"""
    
    bh = memo.get("business_hours") or {}
    routing = memo.get("emergency_routing_rules") or {}
    transfer = memo.get("call_transfer_rules") or {}
    
    spec = {
        "agent_name": f"Clara - {memo.get('company_name', 'Unknown')}",
        "version": version,
        "voice_style": {
            "tone": "warm, professional, calm",
            "pace": "natural, not rushed",
            "language": "plain English, no jargon"
        },
        "system_prompt": build_system_prompt(memo),
        "key_variables": {
            "company_name": memo.get("company_name"),
            "timezone": bh.get("timezone"),
            "business_days": bh.get("days"),
            "business_hours_start": bh.get("start"),
            "business_hours_end": bh.get("end"),
            "emergency_phone": routing.get("phone_number"),
            "emergency_contact": routing.get("primary_contact"),
            "transfer_timeout_seconds": transfer.get("timeout_seconds") or 60
        },
        "call_transfer_protocol": {
            "method": "warm_transfer",
            "announce_before_transfer": True,
            "announcement": "Please hold while I connect you.",
            "timeout_seconds": transfer.get("timeout_seconds") or 60
        },
        "fallback_protocol": {
            "trigger": "Transfer fails or timeout exceeded",
            "action": "log_and_assure",
            "message": transfer.get("fail_message") or 
                "I'm sorry I couldn't reach someone right now. "
                "Your information has been recorded and someone "
                "will follow up with you very soon."
        },
        "questions_or_unknowns": memo.get("questions_or_unknowns") or [],
        "_meta": {
            "generated_at": datetime.now().isoformat(),
            "source_account_id": memo.get("account_id"),
            "version": version
        }
    }
    return spec


def generate_agent_spec(memo_path: str, version: str = "v1") -> dict:
    """Load memo, generate spec, save it"""
    
    with open(memo_path) as f:
        memo = json.load(f)
    
    spec = build_agent_spec(memo, version)
    
    out_path = Path(memo_path).parent / "agent_spec.json"
    with open(out_path, "w") as f:
        json.dump(spec, f, indent=2)
    
    print(f"[OK] Agent spec saved to {out_path}")
    return spec
import requests

def create_retell_agent(spec: dict, api_key: str) -> dict:
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    llm_payload = {
        "model": "claude-4.5-sonnet",
        "system_prompt": spec.get("system_prompt", ""),
        "temperature": 0,
        "max_tokens": 200
    }

    llm_response = requests.post(
        "https://api.retellai.com/create-retell-llm",
        headers=headers,
        json=llm_payload
    )

    if llm_response.status_code not in (200, 201):
        return {"success": False, "error": f"LLM creation failed: {llm_response.text}"}

    llm_id = llm_response.json().get("llm_id")

    # Step 2 — Create agent using that LLM
    company_name = spec.get("key_variables", {}).get("company_name", "us")
    
    agent_payload = {
        "agent_name": spec.get("agent_name", "Clara"),
        "response_engine": {
            "type": "retell-llm",
            "llm_id": llm_id
        },
        "voice_id": "11labs-Adrian",
        "language": "en-US",
        "begin_message": f"Thank you for calling {company_name}, this is Clara. How can I help you today?"
    }

    agent_response = requests.post(
        "https://api.retellai.com/create-agent",
        headers=headers,
        json=agent_payload
    )

    if agent_response.status_code not in (200, 201):
        return {"success": False, "error": f"Agent creation failed: {agent_response.text}"}

    agent_data = agent_response.json()
    agent_id = agent_data.get("agent_id")

    return {
        "success": True,
        "agent_id": agent_id,
        "llm_id": llm_id,
        "agent_name": agent_data.get("agent_name"),
        "retell_url": f"https://app.retellai.com/agent/{agent_id}"
    }

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python generate_agent_spec.py <memo_path> [v1|v2]")
        sys.exit(1)
    
    memo_path = sys.argv[1]
    version = sys.argv[2] if len(sys.argv) > 2 else "v1"
    
    result = generate_agent_spec(memo_path, version)
    print(json.dumps(result, indent=2))
