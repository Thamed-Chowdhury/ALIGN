"""
run_single_benchmark.py — Single Entry Experiment Runner
================================================
Takes a single text string as input and runs the geolocation pipeline
on that entry, then outputs the results.

Usage:
    .venv/Scripts/python.exe run_single_benchmark.py --text "Your news text here"
"""

import argparse
import ast
import glob
import json
import math
import os
import re
import shutil
import sys
import time
import traceback
import io

# ── Pipeline Module Selection ────────────────────────────────
import llm_agent
USE_OCR = True  # Set to False to disable EasyOCR pre-filtering (uses VLM-only pipeline)
USE_LLAMA_JSON = True  # Set to True to use Llama JSON structured output mode (Together AI only)

if USE_LLAMA_JSON:
    import Text2GeolocationV7_llama as Text2GeolocationV7
    from Text2GeolocationV7_llama import geolocation_agent
elif USE_OCR:
    import Text2GeolocationV7
    from Text2GeolocationV7 import geolocation_agent
else:
    import Text2GeolocationV7_OCR_Removed as Text2GeolocationV7
    from Text2GeolocationV7_OCR_Removed import geolocation_agent

# ── Gemini API Keys (first 10 from Gemini APIs.txt) ──────────
GEMINI_API_KEYS = [
    "YOUR_GEMINI_API_KEY_HERE"
]

OPENAI_API_KEYS = [
    "YOUR_OPENAI_API_KEY_HERE"
]

QWEN_API_KEYS = [
    "YOUR_QWEN_API_KEY_HERE"
]

TOGETHER_API_KEYS = [
    "YOUR_TOGETHER_API_KEY_HERE"
]

if llm_agent.PROVIDER == "gemini":
    ACTIVE_API_KEYS = GEMINI_API_KEYS
elif llm_agent.PROVIDER == "openai":
    ACTIVE_API_KEYS = OPENAI_API_KEYS
elif llm_agent.PROVIDER == "qwen":
    ACTIVE_API_KEYS = QWEN_API_KEYS
elif llm_agent.PROVIDER == "together":
    ACTIVE_API_KEYS = TOGETHER_API_KEYS
else:
    ACTIVE_API_KEYS = []

# ── User Settings ────────────────────────────────────────────
OUTPUT_DIR = "results_single"
DEFAULT_TEXT = """
সুনামগঞ্জে সড়কে তিনজন নিহতের ঘটনায় বাসের চালক গ্রেপ্তার
নিজস্ব প্রতিবেদক
সুনামগঞ্জ
প্রকাশ: ০৮ আগস্ট ২০২৫, ১০: ৫৫

শেয়ার করুন
ফলো করুন
গ্রেপ্তার 
গ্রেপ্তারপ্রতীকী ছবি
সুনামগঞ্জে সড়ক দুর্ঘটনায় দুই শিক্ষার্থীসহ তিনজনের মৃত্যুর ঘটনায় বাসচালককে গ্রেপ্তার করেছে র‍্যাব (র‍্যাপিড অ্যাকশন ব্যাটালিয়ন)। গতকাল বৃহস্পতিবার রাতে সিলেটের বিশ্বনাথ উপজেলার লামাকাজী এলাকায় সুনামগঞ্জ-সিলেট সড়কের পাশ থেকে তাঁকে গ্রেপ্তার করা হয়।

এ ঘটনায় সুনামগঞ্জ সদর থানায় একটি মামলা হয়েছে। ওই বাসচালকের নাম জাকির আলম (৩৫)। তিনি সিলেটের বিশ্বনাথ উপজেলার মাহতাবপুর গ্রামের আবদুল কুদ্দুসের ছেলে।


র‍্যাব-৯–এর মিডিয়া কর্মকর্তা অতিরিক্ত পুলিশ সুপার কে এম শহিদুল ইসলাম বলেন, গতকাল রাতে র‍্যাবের সিলেট সদর ও সুনামগঞ্জ সিপিসি-৩–এর সদস্যরা অভিযান চালিয়ে জাকির আলমকে গ্রেপ্তার করেছেন।

গত বুধবার দুপুরে সুনামগঞ্জ-সিলেট সড়কের সদর উপজেলার বাহাদুরপুর গ্রামের পাশে যাত্রীবাহী বাস ও সিএনজিচালিত অটোরিকশার মুখোমুখি সংঘর্ষে তিনজন নিহত হন। তাঁরা হলেন স্নেহা চক্রবর্তী যিনি বুধবার সুনামগঞ্জ বিজ্ঞান ও প্রযুক্তি বিশ্ববিদ্যালয়ে (সুবিপ্রবি) কম্পিউটার সায়েন্স অ্যান্ড ইঞ্জিনিয়ারিং (সিএসই) বিভাগে ভর্তি হয়ে বাড়ি ফিরছিলেন, সুনামগঞ্জ টেক্সটাইল ইনিস্টিটিউটের দ্বিতীয়বর্ষের শিক্ষার্থী আফসানা জাহান ওরফে খুশি এবং সুনামগঞ্জ পৌর শহরের আলীপাড়া এলাকার বাসিন্দা শফিকুল ইসলাম (৭৩)।

আরও পড়ুন
জন্মদিনে সড়ক দুর্ঘটনায় নিহত বিশ্ববিদ্যালয়ের ছাত্রী, ব্যাগে ছিল সহপাঠীদের দেওয়া উপহার
০৭ আগস্ট ২০২৫
জন্মদিনে সড়ক দুর্ঘটনায় নিহত বিশ্ববিদ্যালয়ের ছাত্রী, ব্যাগে ছিল সহপাঠীদের দেওয়া উপহার
এ ঘটনার প্রতিবাদে ও নিরাপদ সড়কের দাবিতে গতকাল বৃহস্পতিবার সুনামগঞ্জের শান্তিগঞ্জ ওই দুই শিক্ষাপ্রতিষ্ঠানের শিক্ষার্থীরা ও সুনামগঞ্জ পৌর শহরে বিক্ষোভ ও মানববন্ধন কর্মসূচি পালন করেন বিভিন্ন শ্রেণি ও পেশার লোকজন।

সুনামগঞ্জ বিজ্ঞান ও প্রযুক্তি বিশ্ববিদ্যালয়ের অস্থায়ী ক্যাম্পাস জেলার শান্তিগঞ্জ উপজেলার শান্তিগঞ্জে সুনামগঞ্জ টেক্মটাইল ইনস্টিটিউটে অবস্থিত। বিশ্ববিদ্যালয়ে গত বছর পাঠদান শুরু হয়। এবার দ্বিতীয় ব্যাচে শিক্ষার্থীরা ভর্তি হচ্ছেন। অনেক শিক্ষার্থী জেলা শহর থেকে প্রায় ১৭ কিলোমিটার দূরের ওই দুই শিক্ষাপ্রতিষ্ঠানে যাতায়াত করেন।
"""

def main():
    parser = argparse.ArgumentParser(description="Run single text benchmark")
    parser.add_argument("--text", type=str, default=DEFAULT_TEXT, help="The news text to geolocate")
    parser.add_argument("--outdir", type=str, default=OUTPUT_DIR, help="Output directory")

    args = parser.parse_args()
    news_text = args.text
    outdir = args.outdir

    # ── Prepare output dir ────────────────────────────────────
    os.makedirs(outdir, exist_ok=True)
    verbose_path = os.path.join(outdir, "single_verbose.txt")
    jsonl_path = os.path.join(outdir, "single_calls.jsonl")
    summary_path = os.path.join(outdir, "single_summary.json")
    screenshots_dir = os.path.join(outdir, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    # ── TeeWriter: writes to verbose_file AND original stdout live ─
    class TeeWriter:
        """Writes every print() call to both the verbose file and the terminal in real time."""
        def __init__(self, file, stream):
            self.file = file
            self.stream = stream
        def write(self, data):
            self.file.write(data)
            self.file.flush()
            self.stream.write(data)
            self.stream.flush()
        def flush(self):
            self.file.flush()
            self.stream.flush()
        def fileno(self):
            return self.stream.fileno()

    # Helper: collect all screenshots generated during the run
    def collect_screenshots(dest_dir):
        """Copy all screenshot files produced during the run into dest_dir."""
        os.makedirs(dest_dir, exist_ok=True)
        patterns = [
            "screenshot.png",
            "temp_vague_ss.png",
            "screenshots_first/*.png",
            "screenshots/*.png",
        ]
        copied = []
        for pattern in patterns:
            for src in glob.glob(pattern):
                basename = os.path.basename(src)
                parent = os.path.dirname(src).replace(os.sep, "_").strip("_")
                dest_name = f"{parent}_{basename}" if parent else basename
                dest = os.path.join(dest_dir, dest_name)
                try:
                    shutil.copy2(src, dest)
                    copied.append(dest)
                except Exception as e:
                    print(f"⚠️ Could not copy screenshot {src}: {e}")
        return copied

    print(f"\n{'='*70}")
    print(f"▶ Running Single Benchmark on Text ({len(news_text)} chars)")
    print(f"{'='*70}")

    # Reset LLM call log
    llm_agent.reset_log()

    # Open verbose file and redirect stdout through TeeWriter (live writing)
    verbose_file = open(verbose_path, "w", encoding="utf-8")
    # Write header to verbose file
    verbose_file.write(f"\n{'='*70}\n")
    verbose_file.write(f"Text: {news_text}\n")
    verbose_file.write(f"{'='*70}\n")
    verbose_file.flush()

    old_stdout = sys.stdout
    sys.stdout = TeeWriter(verbose_file, old_stdout)

    t0 = time.time()
    success = True
    pred_lat = pred_lon = None
    is_vague = False

    try:
        result = geolocation_agent(news_text, ACTIVE_API_KEYS)
        if result and len(result) >= 2:
            pred_lat = result[0]
            pred_lon = result[1]
            is_vague = result[2] if len(result) > 2 else False
            # Check for error strings
            if isinstance(pred_lat, str):
                pred_lat = pred_lon = None
                success = False
    except Exception as e:
        sys.stdout = old_stdout
        print(f"❌ Exception: {e}")
        traceback.print_exc()
        success = False

    elapsed = time.time() - t0
    sys.stdout = old_stdout

    # Get timing breakdown
    selenium_time = Text2GeolocationV7.get_selenium_time()
    ai_time = llm_agent.get_ai_inference_time()
    processing_time = elapsed - selenium_time - ai_time
    
    # Get success stage
    winning_stage = llm_agent.get_success_stage()

    # Write result footer to verbose file
    result_line = f"\n--- Result: lat={pred_lat}, lon={pred_lon}, vague={is_vague}, time={elapsed:.1f}s ---\n"
    verbose_file.write(result_line)
    verbose_file.flush()
    verbose_file.close()
    print(result_line.strip())

    # ── Copy screenshots ────────────────────────────────────────────
    copied = collect_screenshots(screenshots_dir)
    if copied:
        print(f"📸 Saved {len(copied)} screenshot(s) → {screenshots_dir}")

    # Get token summary
    token_summary = llm_agent.get_token_summary()

    # Write JSONL (per-call log)
    with open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
        for call_entry in llm_agent.get_log():
            call_entry["text_snippet"] = news_text[:50] + "..."
            jsonl_file.write(json.dumps(call_entry, ensure_ascii=False) + "\n")

    # Calculate cost dynamically based on the model
    model_pricing = {
        "gemini-2.5-flash": (0.075, 0.30),
        "gemini-2.0-flash": (0.10, 0.40),
        "gemini-1.5-flash": (0.075, 0.30),
        "gemini-1.5-pro": (1.25, 5.00),
        "gpt-4o-mini": (0.150, 0.600),
        "gpt-5-mini": (0.150, 0.600),
        "gpt-4o": (2.50, 10.00),
        "deepseek-chat": (0.14, 0.28),
        "qwen3.5-plus": (0.001, 0.004),
        "meta-llama/llama-4-maverick-17b-128e-instruct-fp8": (0.27, 0.85)
    }
    price_in, price_out = model_pricing.get(llm_agent.MODEL_NAME.lower(), (0.0, 0.0))
    input_cost = (token_summary.get("tokens_total_in", 0) / 1_000_000) * price_in
    output_cost = (token_summary.get("tokens_total_out", 0) / 1_000_000) * price_out
    total_cost = input_cost + output_cost

    # Write summary JSON
    summary = {
        "event_type": "FINAL_RESULT",
        "input_text": news_text,
        "status": "SUCCESS" if (success and pred_lat) else "FAILURE",
        "winning_stage": winning_stage,
        "lat": pred_lat,
        "lon": pred_lon,
        "is_vague": is_vague,
        "timing": {
            "total_duration": round(elapsed, 2),
            "selenium_overhead": round(selenium_time, 2),
            "ai_inference": round(ai_time, 2),
            "processing": round(processing_time, 2)
        },
        "cost": {
            "input_tokens": token_summary.get("tokens_total_in", 0),
            "output_tokens": token_summary.get("tokens_total_out", 0),
            "estimated_usd": round(total_cost, 5)
        }
    }
    
    with open(summary_path, "w", encoding="utf-8") as summary_file:
        summary_file.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    print(f"✅ Result: lat={pred_lat}, lon={pred_lon}")
    print(f"   time={elapsed:.1f}s, calls={token_summary.get('api_calls_count', 0)}, "
          f"tokens_in={token_summary.get('tokens_total_in', 0)}, "
          f"tokens_out={token_summary.get('tokens_total_out', 0)}")
          
    print(f"\n{'='*70}")
    print(f"📊 Single Benchmark complete! Results in {outdir}/")
    print(f"   • {verbose_path}   — verbose console output")
    print(f"   • {jsonl_path}       — per-call LLM logs")
    print(f"   • {summary_path}     — final summary JSON")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
