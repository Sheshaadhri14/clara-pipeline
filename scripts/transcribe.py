import os
import sys
import whisper
from pathlib import Path

SUPPORTED_FORMATS = [".mp3", ".mp4", ".m4a", ".wav", ".mkv", ".avi"]

DATA_DIR = Path(__file__).parent.parent / "data"
def transcribe_file(file_path: Path, model_size: str = "base") -> str:
    """
    Transcribe audio or video file to text using Whisper.
    """
    
    print(f"[INFO] Loading Whisper model: {model_size}")
    model = whisper.load_model(model_size)
    
    print(f"[INFO] Transcribing: {file_path.name}")
    print(f"[INFO] This may take a few minutes...")
    
    result = model.transcribe(
        str(file_path),
        verbose=False,
        language="en"
    )
    
    transcript = result["text"].strip()
    print(f"[OK] Transcription complete — {len(transcript)} characters")
    
    return transcript


def save_transcript(transcript: str, original_file: Path) -> Path:
    """Save transcript as .txt file next to original"""
    
    output_path = original_file.parent / (original_file.stem + "_transcript.txt")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"TRANSCRIPT\n")
        f.write(f"Source: {original_file.name}\n")
        f.write(f"{'='*50}\n\n")
        f.write(transcript)
    
    print(f"[OK] Transcript saved to {output_path}")
    return output_path


def transcribe_and_process(file_path: Path, call_type: str = "demo") -> dict:
    """
    Full flow:
    1. Transcribe audio/video to text
    2. Save transcript
    3. Feed into extract_memo pipeline
    """
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if file_path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format: {file_path.suffix}\n"
            f"Supported: {SUPPORTED_FORMATS}"
        )
    
    transcript = transcribe_file(file_path, model_size="small")
    
    transcript_path = save_transcript(transcript, file_path)
    
    print(f"[INFO] Running extract_memo on transcript...")
    sys.path.insert(0, str(Path(__file__).parent))
    from extract_memo import extract_memo
    
    memo = extract_memo(str(transcript_path), call_type=call_type)
    
    return {
        "transcript_path": str(transcript_path),
        "account_id": memo.get("account_id"),
        "company_name": memo.get("company_name"),
        "memo": memo
    }
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <audio_file> [demo|onboarding]")
        print("Example: python transcribe.py data/demo_call.m4a demo")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    call_type = sys.argv[2] if len(sys.argv) > 2 else "demo"
    
    result = transcribe_and_process(file_path, call_type)
    
    print(f"\n=== TRANSCRIPTION COMPLETE ===")
    print(f"Company: {result['company_name']}")
    print(f"Account ID: {result['account_id']}")
    print(f"Transcript: {result['transcript_path']}")