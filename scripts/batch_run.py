import os
import sys
import json
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extract_memo import extract_memo
from generate_agent_spec import generate_agent_spec
from update_agent import update_agent

OUTPUT_ROOT = Path(__file__).parent.parent / "outputs" / "accounts"
LOG_PATH = Path(__file__).parent.parent / "outputs" / "batch_log.json"

def process_demo(transcript_path: Path) -> dict:
    """Pipeline A: demo transcript → v1 memo + v1 spec"""
    
    print(f"\n[PIPELINE A] {transcript_path.name}")
    
    memo = extract_memo(str(transcript_path), call_type="demo")
    account_id = memo["account_id"]
    
    existing = OUTPUT_ROOT / account_id / "v1" / "account_memo.json"
    if existing.exists():
        print(f"  [SKIP] {account_id} already has v1 — skipping")
        return {
            "account_id": account_id,
            "company_name": memo.get("company_name"),
            "status": "skipped",
            "reason": "v1 already exists"
        }
    
    memo_path = OUTPUT_ROOT / account_id / "v1" / "account_memo.json"
    generate_agent_spec(str(memo_path), "v1")
    
    print(f"  [OK] Processed → {account_id}")
    
    return {
        "account_id": account_id,
        "company_name": memo.get("company_name"),
        "status": "ok",
        "unknowns": len(memo.get("questions_or_unknowns") or [])
    }

def process_onboarding(transcript_path: Path, account_id: str) -> dict:
    """Pipeline B: onboarding transcript → v2 memo + spec + changelog"""
    
    print(f"\n[PIPELINE B] {transcript_path.name}")
    
    existing = OUTPUT_ROOT / account_id / "v2" / "account_memo.json"
    if existing.exists():
        print(f"  [SKIP] {account_id} already has v2 — skipping")
        return {
            "account_id": account_id,
            "status": "skipped",
            "reason": "v2 already exists"
        }
    
    v1_path = OUTPUT_ROOT / account_id / "v1" / "account_memo.json"
    if not v1_path.exists():
        print(f"  [ERROR] No v1 found for {account_id} — run demo first")
        return {
            "account_id": account_id,
            "status": "error",
            "reason": "v1 not found"
        }
    
    transcript = transcript_path.read_text(encoding="utf-8")
    result = update_agent(account_id, transcript)
    
    print(f"  [OK] {result['changes_count']} changes applied")
    
    return {
        "account_id": account_id,
        "company_name": result.get("company_name"),
        "status": "ok",
        "changes": result["changes_count"],
        "questions_remaining": len(result["questions_remaining"])
    }

def run_batch(data_dir: Path) -> dict:
    """Run full batch on all files in data directory"""
    
    started_at = datetime.datetime.now().isoformat()
    
    print(f"\n{'='*50}")
    print(f"CLARA PIPELINE — BATCH RUN")
    print(f"Data directory: {data_dir}")
    print(f"{'='*50}")
    
    all_files = list(data_dir.glob("*.txt")) + list(data_dir.glob("*.md"))
    
    demo_files = [f for f in all_files if "demo" in f.name.lower()]
    onboard_files = [f for f in all_files if "onboard" in f.name.lower()]
    
    print(f"\nFound {len(demo_files)} demo files")
    print(f"Found {len(onboard_files)} onboarding files")
    
    demo_results = []
    onboard_results = []
    
    print(f"\n--- PIPELINE A: Demo Calls ---")
    for demo_file in demo_files:
        try:
            result = process_demo(demo_file)
            demo_results.append(result)
        except Exception as e:
            print(f"  [ERROR] {demo_file.name}: {e}")
            demo_results.append({
                "file": demo_file.name,
                "status": "error",
                "error": str(e)
            })
    
    print(f"\n--- PIPELINE B: Onboarding Calls ---")
    for onboard_file in onboard_files:
        
        account_id = find_matching_account(onboard_file, demo_results)
        
        if not account_id:
            print(f"  [ERROR] Could not match {onboard_file.name} to any account")
            onboard_results.append({
                "file": onboard_file.name,
                "status": "error",
                "reason": "no matching account found"
            })
            continue
        
        try:
            result = process_onboarding(onboard_file, account_id)
            onboard_results.append(result)
        except Exception as e:
            print(f"  [ERROR] {onboard_file.name}: {e}")
            onboard_results.append({
                "file": onboard_file.name,
                "status": "error",
                "error": str(e)
            })
    
    total = len(demo_results) + len(onboard_results)
    errors = sum(1 for r in demo_results + onboard_results 
                 if r.get("status") == "error")
    skipped = sum(1 for r in demo_results + onboard_results 
                  if r.get("status") == "skipped")
    
    log = {
        "started_at": started_at,
        "completed_at": datetime.datetime.now().isoformat(),
        "summary": {
            "total_files": total,
            "succeeded": total - errors - skipped,
            "skipped": skipped,
            "errors": errors
        },
        "demo_results": demo_results,
        "onboard_results": onboard_results
    }
    
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"BATCH COMPLETE")
    print(f"Total: {total} | OK: {total-errors-skipped} | Skipped: {skipped} | Errors: {errors}")
    print(f"Log saved to {LOG_PATH}")
    print(f"{'='*50}\n")
    
    return log
def find_matching_account(onboard_file: Path, demo_results: list) -> str:
    """
    Match onboarding file to account_id.
    Strategy 1: match by first word against demo results
    Strategy 2: match by first word against existing accounts on disk
    """
    prefix = onboard_file.name.split("_")[0].lower()
    
    for result in demo_results:
        account_id = result.get("account_id", "")
        if prefix in account_id:
            return account_id
    
    if OUTPUT_ROOT.exists():
        for account_dir in OUTPUT_ROOT.iterdir():
            if account_dir.is_dir() and prefix in account_dir.name:
                v1_exists = (account_dir / "v1" / "account_memo.json").exists()
                if v1_exists:
                    print(f"  [MATCH] Found existing account: {account_dir.name}")
                    return account_dir.name
    
    return None

if __name__ == "__main__":
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    
    if not data_dir.exists():
        print(f"[ERROR] Data directory not found: {data_dir}")
        sys.exit(1)
    
    run_batch(data_dir)