# Clara Answers — AI Voice Agent Pipeline

Automates the full journey from call transcript → Retell agent 
configuration → onboarding update → versioned v2 agent.

Built for the Clara Answers intern assignment.

---

## What This Does

Takes messy call transcripts and turns them into production-ready 
AI voice agent configurations automatically.
```
Demo call transcript
      ↓
Account Memo JSON (v1)
      ↓
Retell Agent Spec (v1)
      ↓
Onboarding transcript
      ↓
Updated Memo + Spec (v2)
      ↓
Changelog (what changed and why)
```

---

## Architecture
```
clara-pipeline/
├── scripts/
│   ├── transcribe.py          # Audio/video → text (Whisper)
│   ├── extract_memo.py        # Transcript → structured JSON
│   ├── generate_agent_spec.py # JSON → Retell agent prompt
│   ├── update_agent.py        # v1 → v2 + changelog
│   └── batch_run.py           # Run all files automatically
│
├── data/                      # Put transcript files here
├── outputs/
│   └── accounts/
│       └── <account_id>/
│           ├── v1/            # Demo call outputs
│           │   ├── account_memo.json
│           │   └── agent_spec.json
│           └── v2/            # Onboarding outputs
│               ├── account_memo.json
│               └── agent_spec.json
├── changelog/                 # Per-account changelogs
├── workflows/                 # n8n workflow export
└── README.md
```

---

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/Sheshaadhri14/clara-pipeline.git
cd clara-pipeline
```

### 2. Create virtual environment
```bash
python -m venv myvenv
myvenv\Scripts\activate     # Windows
source myvenv/bin/activate  # Mac/Linux
```

### 3. Install dependencies
```bash
pip install google-generativeai python-dotenv openai-whisper
```

### 4. Set up API key

Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_key_here
```

Get a free key at: https://aistudio.google.com

### 5. Install ffmpeg (for audio/video)

Windows:
```bash
winget install ffmpeg
```

Mac:
```bash
brew install ffmpeg
```

---

## How To Run

### Option A — Single transcript file
```bash
# Demo call
python scripts/extract_memo.py data/demo.txt demo

# Generate agent spec from memo
python scripts/generate_agent_spec.py outputs/accounts/<id>/v1/account_memo.json v1

# Onboarding update
python scripts/update_agent.py <account_id> data/onboarding.txt
```

### Option B — Audio or video file
```bash
# Transcribe then extract automatically
python scripts/transcribe.py data/demo_call.m4a demo
python scripts/transcribe.py data/meeting_recording.mp4 onboarding
```

### Option C — Batch (all files at once)
```bash
# Name demo files with "demo" in filename
# Name onboarding files with "onboard" in filename
python scripts/batch_run.py data
```

---

## How To Plug In The Dataset

1. Put all transcript files in the `/data` folder
2. Name demo files: `<company>_demo.txt`
3. Name onboarding files: `<company>_onboarding.txt`
4. Run: `python scripts/batch_run.py data`

Outputs will appear in `outputs/accounts/<account_id>/`

---

## LLM — Zero Cost

This pipeline uses **Google Gemini 1.5 Flash** via the free tier.

- Free tier: 15 requests/minute, 1500 requests/day
- No credit card required
- Get key at: https://aistudio.google.com

---

## Where Outputs Are Stored
```
outputs/
└── accounts/
    └── <account_id>/
        ├── v1/
        │   ├── account_memo.json   ← structured business data
        │   └── agent_spec.json     ← Retell agent configuration
        └── v2/
            ├── account_memo.json   ← updated after onboarding
            └── agent_spec.json     ← updated agent prompt

changelog/
└── <account_id>_changes.json      ← what changed v1→v2
└── <account_id>_changes.md        ← human readable changelog
```

---

## Retell Setup

1. Create free account at retellai.com
2. Create a new LLM agent
3. Copy `system_prompt` from `agent_spec.json`
4. Paste into Retell agent prompt field
5. Set transfer number from `key_variables.emergency_phone`
6. Save and test

---

## Known Limitations

1. Account ID matching uses filename prefix — works best when 
   demo and onboarding files share the same prefix
   (e.g. `ben_demo.txt` and `ben_onboarding.txt`)

2. Whisper runs on CPU by default — install CUDA torch for 
   GPU acceleration on supported machines

3. Company name variations between calls can create 
   different account IDs for the same client

4. No real Retell API calls — agent_spec.json is designed 
   for manual import or API integration

---

## What I Would Improve With Production Access

1. **Retell API integration** — auto-create agents via API
2. **Supabase database** — replace JSON files with proper DB
3. **Webhook support** — trigger pipeline automatically on new recordings
4. **Confidence scoring** — flag low-confidence extractions
5. **Speaker diarization** — identify who said what in transcripts
6. **Conflict resolution UI** — human review for flagged conflicts
