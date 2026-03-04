import os
import json
import datetime
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
CHANGELOG_ROOT = Path(__file__).parent.parent / "changelog"

def merge_memos(v1: dict, updates: dict) -> tuple:
    """
    Merge onboarding updates into v1 memo.
    Returns (v2_memo, changes_list)
    
    Rules:
    - If update value is not None → overwrite v1
    - If update value is None → keep v1 value
    - Lists → combine and deduplicate
    - Always track what changed
    """
    v2 = v1.copy()
    changes = []

    for key, new_value in updates.items():
        if key.startswith("_"):
            continue

        old_value = v1.get(key)

        if new_value is None:
            continue

        if isinstance(new_value, dict) and isinstance(old_value, dict):
            for subkey, subvalue in new_value.items():
                if subvalue is not None and subvalue != old_value.get(subkey):
                    changes.append({
                        "field": f"{key}.{subkey}",
                        "from": old_value.get(subkey),
                        "to": subvalue,
                        "source": "onboarding"
                    })
                    v2[key][subkey] = subvalue

        elif isinstance(new_value, list) and isinstance(old_value, list):
            merged = old_value.copy()
            added = []
            for item in new_value:
                if item not in merged:
                    merged.append(item)
                    added.append(item)
            if added:
                changes.append({
                    "field": key,
                    "action": "items_added",
                    "added": added,
                    "source": "onboarding"
                })
                v2[key] = merged

        elif new_value != old_value:
            changes.append({
                "field": key,
                "from": old_value,
                "to": new_value,
                "source": "onboarding"
            })
            v2[key] = new_value

    return v2, changes
def save_changelog(account_id: str, company_name: str, changes: list) -> Path:
    """Save changelog as both JSON and markdown"""
    
    CHANGELOG_ROOT.mkdir(parents=True, exist_ok=True)
    
    changelog = {
        "account_id": account_id,
        "company_name": company_name,
        "generated_at": datetime.datetime.now().isoformat(),
        "total_changes": len(changes),
        "changes": changes
    }
    
    json_path = CHANGELOG_ROOT / f"{account_id}_changes.json"
    with open(json_path, "w") as f:
        json.dump(changelog, f, indent=2)
    
    md_lines = [
        f"# Changelog: {company_name}",
        f"**Account ID:** {account_id}",
        f"**Generated:** {changelog['generated_at']}",
        f"**Total Changes:** {len(changes)}",
        "",
        "## Changes (v1 → v2)",
        ""
    ]
    
    for i, change in enumerate(changes, 1):
        field = change.get("field", "unknown")
        action = change.get("action", "updated")
        
        md_lines.append(f"### {i}. `{field}`")
        
        if action == "items_added":
            md_lines.append(f"- **Added:** {change.get('added')}")
        else:
            md_lines.append(f"- **From:** `{change.get('from')}`")
            md_lines.append(f"- **To:** `{change.get('to')}`")
        
        md_lines.append("")
    
    md_path = CHANGELOG_ROOT / f"{account_id}_changes.md"
    with open(md_path, "w",encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    
    print(f"[OK] Changelog saved to {json_path}")
    print(f"[OK] Changelog saved to {md_path}")
    
    return json_path
def update_agent(account_id: str, onboarding_transcript: str) -> dict:
    """
    Full Pipeline B:
    1. Load v1 memo
    2. Extract updates from onboarding transcript
    3. Merge into v2
    4. Generate v2 agent spec
    5. Save changelog
    """
    
    v1_path = OUTPUT_ROOT / account_id / "v1" / "account_memo.json"
    
    if not v1_path.exists():
        raise FileNotFoundError(
            f"No v1 memo found for account: {account_id}\n"
            f"Expected at: {v1_path}\n"
            f"Run extract_memo.py on the demo transcript first."
        )
    
    with open(v1_path) as f:
        v1_memo = json.load(f)
    
    print(f"[INFO] Loaded v1 memo for {v1_memo.get('company_name')}")
    
    print(f"[INFO] Extracting updates from onboarding transcript...")
    
    from extract_memo import extract_with_gemini
    updates = extract_with_gemini(onboarding_transcript)
    
    v2_memo, changes = merge_memos(v1_memo, updates)
    
    v2_memo["account_id"] = account_id
    
    v2_memo["_meta"] = {
        "extracted_at": datetime.datetime.now().isoformat(),
        "call_type": "onboarding",
        "version": "v2",
        "based_on_v1": v1_memo.get("_meta", {}).get("extracted_at"),
        "changes_applied": len(changes)
    }
    
    v2_dir = OUTPUT_ROOT / account_id / "v2"
    v2_dir.mkdir(parents=True, exist_ok=True)
    
    v2_memo_path = v2_dir / "account_memo.json"
    with open(v2_memo_path, "w") as f:
        json.dump(v2_memo, f, indent=2)
    print(f"[OK] v2 memo saved to {v2_memo_path}")
    
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from generate_agent_spec import build_agent_spec
    
    v2_spec = build_agent_spec(v2_memo, "v2")
    v2_spec_path = v2_dir / "agent_spec.json"
    with open(v2_spec_path, "w") as f:
        json.dump(v2_spec, f, indent=2)
    print(f"[OK] v2 agent spec saved to {v2_spec_path}")
    
    save_changelog(account_id, v2_memo.get("company_name", account_id), changes)
    
    return {
        "account_id": account_id,
        "company_name": v2_memo.get("company_name"),
        "changes_count": len(changes),
        "v2_memo_path": str(v2_memo_path),
        "v2_spec_path": str(v2_spec_path),
        "changes": changes,
        "questions_remaining": v2_memo.get("questions_or_unknowns") or []
    }
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python update_agent.py <account_id> <onboarding_transcript>")
        print("Example: python update_agent.py ben-s-electrical-solutio-bdce data/ben_onboarding.txt")
        sys.exit(1)
    
    account_id = sys.argv[1]
    transcript_path = sys.argv[2]
    
    transcript = Path(transcript_path).read_text(encoding="utf-8")
    result = update_agent(account_id, transcript)
    
    print("\n=== UPDATE COMPLETE ===")
    print(f"Company: {result['company_name']}")
    print(f"Changes applied: {result['changes_count']}")
    print(f"Questions remaining: {len(result['questions_remaining'])}")
    print("\nChanges:")
    for change in result["changes"]:
        field = change.get("field")
        if change.get("action") == "items_added":
            print(f"  + {field}: added {change.get('added')}")
        else:
            print(f"  ~ {field}: {change.get('from')} → {change.get('to')}")