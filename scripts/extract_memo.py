import os
import sys
import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google import genai



load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash"
OUTPUT_ROOT = Path(__file__).parent.parent / "outputs" / "accounts"


EXTRACTION_PROMPT = """
You are a configuration assistant for Clara Answers, an AI voice agent 
platform for service businesses.

Read this call transcript and extract ONLY facts that are explicitly stated.
NEVER guess or invent missing information.
integration_constraints means technical system rules like 
"never auto-create jobs in ServiceTrade" — NOT setup instructions.
If something is not mentioned, use null.
Put unclear or missing items in questions_or_unknowns.

Return ONLY a valid JSON object. No explanation. No markdown. Just JSON.

Use exactly this structure:
{
  "account_id": null,
  "company_name": null,
  "business_hours": {
    "days": null,
    "start": null,
    "end": null,
    "timezone": null
  },
  "office_address": null,
  "services_supported": [],
  "emergency_definition": [],
  "emergency_routing_rules": {
    "primary_contact": null,
    "phone_number": null,
    "fallback": null
  },
  "non_emergency_routing_rules": {
    "action": null,
    "details": null
  },
  "call_transfer_rules": {
    "timeout_seconds": null,
    "fail_message": null
  },
  "special_clients": [],
  "pricing": {
    "service_call_fee": null,
    "hourly_rate": null,
    "mention_to_caller": null
  },
  "notification_preferences": {
    "email": null,
    "phone": null
  },
  "integration_constraints": [],
  "after_hours_flow_summary": null,
  "office_hours_flow_summary": null,
  "questions_or_unknowns": [],
  "notes": null
}

TRANSCRIPT:
"""


def generate_account_id(company_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "-", company_name.lower()).strip("-")[:24]
    hash4 = hashlib.md5(company_name.encode()).hexdigest()[:4]
    return f"{slug}-{hash4}"


def clean_json_response(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)



def extract_with_gemini(transcript: str) -> dict:
    prompt = EXTRACTION_PROMPT + transcript

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )

        if not response.text:
            raise ValueError("Empty response from Gemini")

        return clean_json_response(response.text)

    except Exception as e:
        raise RuntimeError(f"Gemini extraction failed: {str(e)}")



def extract_memo(transcript_path: str, call_type: str = "demo") -> dict:
    transcript = Path(transcript_path).read_text(encoding="utf-8")

    print("[INFO] Sending to Gemini...")
    memo = extract_with_gemini(transcript)

    if memo.get("company_name"):
        memo["account_id"] = generate_account_id(memo["company_name"])
    else:
        memo["account_id"] = "unknown-account"

    memo["_meta"] = {
        "extracted_at": datetime.now().isoformat(),
        "call_type": call_type,
        "version": "v1" if call_type == "demo" else "v2",
        "source_file": Path(transcript_path).name,
    }

    account_id = memo["account_id"]
    version = memo["_meta"]["version"]

    out_dir = OUTPUT_ROOT / account_id / version
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "account_memo.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(memo, f, indent=2)

    print(f"[OK] Saved to {out_path}")

    return memo



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_memo.py <transcript_file> [demo|onboarding]")
        sys.exit(1)

    transcript_file = sys.argv[1]
    call_type = sys.argv[2] if len(sys.argv) > 2 else "demo"

    result = extract_memo(transcript_file, call_type)
    print(json.dumps(result, indent=2))