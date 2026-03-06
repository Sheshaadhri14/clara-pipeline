import os
import re
import base64
import hashlib
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import edge_tts

load_dotenv()


from google import genai

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash"

model = client.models
app = FastAPI(title="Clara Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory company store (resets on server restart)
# For production use a database
COMPANIES = {}

class ChatRequest(BaseModel):
    message: str
    history: list = []
    company: str = "Apex Home Services"
    business_hours: str = "Monday to Friday 8am to 6pm"
    emergency_phone: str = "our on-call technician"
    services: str = "HVAC, Electrical, Plumbing"
    language: str = "en"

class CompanyRequest(BaseModel):
    company_name: str
    services: str
    business_hours: str
    emergency_contact: str
    emergency_phone: str
    after_hours: str = "emergency only"
    pricing: str = ""
    language: str = "en"

@app.get("/")
def root():
    return {"status": "Clara Pipeline API running"}

@app.post("/chat")
async def chat(req: ChatRequest):
    """Chat with Clara — multilingual support"""
    try:
        # Step 1 — Detect language and translate to English
        lang_prompt = f"""Detect the language of this message and translate it to English.
Return ONLY valid JSON like this:
{{"detected_language": "tamil", "language_code": "ta", "english_text": "translated text here"}}

Message: {req.message}"""

        lang_response = model.generate_content(lang_prompt)
        lang_raw = lang_response.text.strip()
        lang_raw = re.sub(r'^```json\s*', '', lang_raw)
        lang_raw = re.sub(r'\s*```$', '', lang_raw)

        try:
            lang_data = json.loads(lang_raw)
            english_message = lang_data.get("english_text", req.message)
            detected_lang = lang_data.get("detected_language", "english")
            lang_code = lang_data.get("language_code", "en")
        except:
            english_message = req.message
            detected_lang = "english"
            lang_code = "en"

        # Step 2 — Get Clara's response in English
        system = f"""You are Clara, an AI receptionist for {req.company}.
Services: {req.services}
Business hours: {req.business_hours}
Emergency contact: {req.emergency_phone}
After hours: emergency calls only.

Rules:
- Keep replies SHORT — 2-3 sentences max
- Never say you are an AI unless asked
- Never mention tools or functions
- Always repeat phone numbers back to confirm
- Be warm, calm and professional
- Never promise exact arrival times
- If pricing asked: mention it only if explicitly asked"""

        messages = []
        for h in req.history:
            messages.append({
                "role": h["role"],
                "parts": [h["content"]]
            })

        chat_session = model.start_chat(history=messages)
        response = chat_session.send_message(
            f"System context: {system}\n\nUser message: {english_message}"
        )
        english_reply = response.text.strip()

        # Step 3 — Translate reply back to detected language
        if lang_code != "en" and detected_lang != "english":
            translate_prompt = f"""Translate this English text to {detected_lang}.
Keep it natural and conversational.
Return ONLY the translated text, nothing else.

English text: {english_reply}"""
            trans_response = model.generate_content(translate_prompt)
            final_reply = trans_response.text.strip()
        else:
            final_reply = english_reply

        # Step 4 — Convert to speech
        # Pick voice based on language
        voice_map = {
            "en": "en-US-JennyNeural",
            "hi": "hi-IN-SwaraNeural",
            "ta": "ta-IN-PallaviNeural",
            "es": "es-ES-ElviraNeural",
            "fr": "fr-FR-DeniseNeural",
            "de": "de-DE-KatjaNeural",
            "zh": "zh-CN-XiaoxiaoNeural",
            "ar": "ar-SA-ZariyahNeural",
            "pt": "pt-BR-FranciscaNeural",
            "ja": "ja-JP-NanamiNeural",
        }
        voice = voice_map.get(lang_code, "en-US-JennyNeural")

        communicate = edge_tts.Communicate(final_reply, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        audio_base64 = base64.b64encode(audio_data).decode()

        return {
            "reply": final_reply,
            "english_reply": english_reply,
            "detected_language": detected_lang,
            "language_code": lang_code,
            "audio": audio_base64,
            "format": "mp3"
        }

    except Exception as e:
        return {"error": str(e), "reply": "I had trouble processing that. Please try again."}


@app.post("/create-company")
async def create_company(req: CompanyRequest):
    """Create a new company agent with shareable URL"""
    try:
        # Generate unique company ID
        slug = re.sub(r'[^a-z0-9]', '-', req.company_name.lower()).strip('-')[:24]
        hash4 = hashlib.md5(req.company_name.encode()).hexdigest()[:4]
        company_id = f"{slug}-{hash4}"

        # Generate agent config using Gemini
        config_prompt = f"""Create a professional AI receptionist system prompt for this business:

Company: {req.company_name}
Services: {req.services}
Business Hours: {req.business_hours}
Emergency Contact: {req.emergency_contact}
Emergency Phone: {req.emergency_phone}
After Hours Policy: {req.after_hours}
Pricing: {req.pricing if req.pricing else "not specified"}

Generate a warm, professional system prompt that includes:
1. Identity (name is Clara)
2. Business hours flow (greet, understand purpose, collect name/number, transfer)
3. After hours flow (greet, check emergency, collect details, assure callback)
4. Key rules (never mention AI, never mention tools, max 2 questions at once)

Keep it concise and practical. Return only the system prompt text."""

        config_response = model.generate_content(config_prompt)
        system_prompt = config_response.text.strip()

        # Store company
        COMPANIES[company_id] = {
            "id": company_id,
            "company_name": req.company_name,
            "services": req.services,
            "business_hours": req.business_hours,
            "emergency_contact": req.emergency_contact,
            "emergency_phone": req.emergency_phone,
            "after_hours": req.after_hours,
            "pricing": req.pricing,
            "system_prompt": system_prompt,
            "language": req.language
        }

        return {
            "success": True,
            "company_id": company_id,
            "company_name": req.company_name,
            "agent_url": f"/#/agent/{company_id}",
            "config": COMPANIES[company_id]
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/company/{company_id}")
async def get_company(company_id: str):
    """Get company config by ID"""
    if company_id not in COMPANIES:
        return {"error": "Company not found"}
    return COMPANIES[company_id]


@app.post("/chat/{company_id}")
async def chat_company(company_id: str, req: ChatRequest):
    """Chat with a specific company's Clara agent"""
    if company_id in COMPANIES:
        company = COMPANIES[company_id]
        req.company = company["company_name"]
        req.services = company["services"]
        req.business_hours = company["business_hours"]
        req.emergency_phone = company["emergency_phone"]
    return await chat(req)
