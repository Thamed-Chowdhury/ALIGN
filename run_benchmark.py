"""
run_benchmark.py — Automated Experiment Runner
================================================
Reads a test dataset (CSV or XLSX with a 'Gemini_responses' column for news text
and optionally 'Co-ordinates' for ground truth), runs the geolocation pipeline
on each row, and saves structured results:

  results/
    benchmark_results.csv     — one-row-per-article structured metrics
    benchmark_verbose.txt     — full console output per article
    benchmark_calls.jsonl     — per-LLM-call log (stage, tokens, timing)

Usage:
    .venv/Scripts/python.exe run_benchmark.py --input Geolocation_val_dataset_2.csv --n 10
"""

import ast
import csv
import glob
import io
import json
import math
import os
import re
import shutil
import sys
import time
import traceback

import pandas as pd

# ── Pipeline Module Selection ────────────────────────────────
import llm_agent
USE_OCR = True  # Set to False to disable EasyOCR pre-filtering (uses VLM-only pipeline)
USE_ROADS = True  # Set to False to disable bd_roads.json road injection
USE_LLAMA_JSON = True  # Set to True to use Llama JSON structured output mode (Together AI only)

if USE_LLAMA_JSON:
    import Text2GeolocationV7_llama as Text2GeolocationV7
    from Text2GeolocationV7_llama import geolocation_agent
elif USE_OCR:
    if USE_ROADS:
        import Text2GeolocationV7
        from Text2GeolocationV7 import geolocation_agent
    else:
        import Text2GeolocationV7_no_roads as Text2GeolocationV7
        from Text2GeolocationV7_no_roads import geolocation_agent
else:
    if USE_ROADS:
        import Text2GeolocationV7_OCR_Removed as Text2GeolocationV7
        from Text2GeolocationV7_OCR_Removed import geolocation_agent
    else:
        import Text2GeolocationV7_no_roads as Text2GeolocationV7
        from Text2GeolocationV7_no_roads import geolocation_agent

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
# Edit these variables to configure your benchmark run
INPUT_FILE = "dataset.xlsx"
OUTPUT_DIR = "results"
START_ROW = 0
NUM_ROWS = 45
SPECIFIC_ROWS = None #"0"  # Comma-separated row indices, or set to None to use START_ROW and NUM_ROWS


# ── Haversine Distance ───────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    """Return great-circle distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Parse ground truth coords ────────────────────────────────
def parse_gt(coord_str):
    """Parse '[lat, lon, flag]' or '(lat, lon)' strings → (lat, lon) or None."""
    if not coord_str or pd.isna(coord_str):
        return None, None
    try:
        vals = ast.literal_eval(str(coord_str))
        if isinstance(vals, (list, tuple)) and len(vals) >= 2:
            return float(vals[0]), float(vals[1])
    except Exception:
        pass
    return None, None


# ── Main ─────────────────────────────────────────────────────
def main():
    # Use settings from top of file
    input_file = INPUT_FILE
    outdir = OUTPUT_DIR
    start_row = START_ROW
    num_rows = NUM_ROWS
    specific_rows = SPECIFIC_ROWS

    # ── Load dataset ──────────────────────────────────────────
    ext = os.path.splitext(input_file)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(input_file)
    else:
        df = pd.read_excel(input_file)

    if specific_rows and specific_rows.strip():
        row_indices = [int(x.strip()) for x in specific_rows.split(",")]
        subset = df.iloc[row_indices]
        print(f"📂 Loaded {len(df)} rows from {input_file}; processing {len(subset)} selected rows: {row_indices}")
    else:
        subset = df.iloc[start_row : start_row + num_rows]
        print(f"📂 Loaded {len(df)} rows from {input_file}; processing rows {start_row}–{start_row + num_rows - 1}")

    # ── Prepare output dir ────────────────────────────────────
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, "benchmark_results.csv")
    verbose_path = os.path.join(outdir, "benchmark_verbose.txt")
    jsonl_path = os.path.join(outdir, "benchmark_calls.jsonl")
    screenshots_base_dir = os.path.join(outdir, "screenshots")
    os.makedirs(screenshots_base_dir, exist_ok=True)

    # ── CSV header ────────────────────────────────────────────
    csv_fields = [
        "row_idx", "news_title", "model",
        "pred_lat", "pred_lon", "is_vague",
        "gt_lat", "gt_lon", "error_km",
        "total_time_s",
        "api_calls_count",
        "tokens_total_in", "tokens_total_out",
        "tokens_ner_in", "tokens_ner_out",
        "tokens_rerank_in", "tokens_rerank_out",
        "tokens_vlm_in", "tokens_vlm_out",
        "tokens_vague_in", "tokens_vague_out",
        "tokens_grid_in", "tokens_grid_out",
        "success",
        "winning_stage", "selenium_time_s", "ai_inference_time_s", "processing_time_s",
    ]
    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(csv_file, fieldnames=csv_fields)
    csv_writer.writeheader()

    verbose_file = open(verbose_path, "w", encoding="utf-8")
    jsonl_file = open(jsonl_path, "w", encoding="utf-8")
    summary_path = os.path.join(outdir, "benchmark_summary.jsonl")
    summary_file = open(summary_path, "w", encoding="utf-8")

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

    # Helper: collect all screenshots generated during a run and copy them
    def collect_screenshots(dest_dir):
        """Copy all screenshot files produced during a benchmark row into dest_dir."""
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
                # Add parent folder prefix to avoid name collisions (e.g. screenshots_first_screenshot_1.png)
                parent = os.path.dirname(src).replace(os.sep, "_").strip("_")
                dest_name = f"{parent}_{basename}" if parent else basename
                dest = os.path.join(dest_dir, dest_name)
                try:
                    shutil.copy2(src, dest)
                    copied.append(dest)
                except Exception as e:
                    print(f"⚠️ Could not copy screenshot {src}: {e}")
        return copied

    # ── Check for ground truth column ─────────────────────────
    has_gt = "Actual Co-ordinates" in df.columns

    # ── Process each article ──────────────────────────────────
    for i, (idx, row) in enumerate(subset.iterrows()):
        news_text = str(row.get("Description", ""))
        news_title = str(row.get("News Title", f"Row {idx}"))[:80]

        # Safe folder name for this row's screenshots
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', news_title)[:50]
        row_ss_dir = os.path.join(screenshots_base_dir, f"row_{idx}_{safe_title}")

        # Write article header to verbose file and print to terminal
        row_header = f"\n{'='*70}\nRow {idx}: {news_title}\n{'='*70}\n"
        verbose_file.write(row_header)
        verbose_file.flush()

        print(f"\n{'='*70}")
        print(f"▶ [{i+1}/{len(subset)}]  Row {idx}: {news_title}")
        print(f"{'='*70}")

        # Reset LLM call log and Selenium timer for this article
        llm_agent.reset_log()

        # Redirect stdout through TeeWriter so all prints go live to verbose_file
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

        # Write result footer and flush
        result_line = f"\n--- Result: lat={pred_lat}, lon={pred_lon}, vague={is_vague}, time={elapsed:.1f}s ---\n"
        verbose_file.write(result_line)
        verbose_file.flush()
        print(result_line.strip())

        # ── Copy screenshots for this row ─────────────────────
        copied = collect_screenshots(row_ss_dir)
        if copied:
            print(f"📸 Saved {len(copied)} screenshot(s) → {row_ss_dir}")

        # Get token summary
        token_summary = llm_agent.get_token_summary()

        # Write JSONL (per-call log)
        for call_entry in llm_agent.get_log():
            call_entry["row_idx"] = idx
            call_entry["news_title"] = news_title
            jsonl_file.write(json.dumps(call_entry, ensure_ascii=False) + "\n")
        jsonl_file.flush()

        # Ground truth
        gt_lat, gt_lon = None, None
        error_km = None
        if has_gt:
            gt_lat, gt_lon = parse_gt(row.get("Actual Co-ordinates"))
        if pred_lat is not None and gt_lat is not None:
            try:
                error_km = round(haversine(float(pred_lat), float(pred_lon),
                                           float(gt_lat), float(gt_lon)), 3)
            except Exception:
                error_km = None

        # Write CSV row
        csv_row = {
            "row_idx": idx,
            "news_title": news_title,
            "model": llm_agent.MODEL_NAME,
            "pred_lat": pred_lat,
            "pred_lon": pred_lon,
            "is_vague": is_vague,
            "gt_lat": gt_lat,
            "gt_lon": gt_lon,
            "error_km": error_km,
            "total_time_s": round(elapsed, 1),
            "api_calls_count": token_summary.get("api_calls_count", 0),
            "tokens_total_in": token_summary.get("tokens_total_in", 0),
            "tokens_total_out": token_summary.get("tokens_total_out", 0),
            "tokens_ner_in": token_summary.get("tokens_ner_in", 0),
            "tokens_ner_out": token_summary.get("tokens_ner_out", 0),
            "tokens_rerank_in": token_summary.get("tokens_rerank_in", 0),
            "tokens_rerank_out": token_summary.get("tokens_rerank_out", 0),
            "tokens_vlm_in": token_summary.get("tokens_vlm_in", 0),
            "tokens_vlm_out": token_summary.get("tokens_vlm_out", 0),
            "tokens_vague_in": token_summary.get("tokens_vague_in", 0),
            "tokens_vague_out": token_summary.get("tokens_vague_out", 0),
            "tokens_grid_in": token_summary.get("tokens_grid_in", 0),
            "tokens_grid_out": token_summary.get("tokens_grid_out", 0),
            "success": success,
            "winning_stage": winning_stage,
            "selenium_time_s": round(selenium_time, 2),
            "ai_inference_time_s": round(ai_time, 2),
            "processing_time_s": round(processing_time, 2),
        }
        csv_writer.writerow(csv_row)
        csv_file.flush()

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
            "row_idx": idx,
            "status": "SUCCESS" if (success and pred_lat) else "FAILURE",
            "winning_stage": winning_stage,
            "lat": pred_lat,
            "lon": pred_lon,
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
        summary_file.write(json.dumps(summary, ensure_ascii=False) + "\n")
        summary_file.flush()
        print(json.dumps(summary, ensure_ascii=False, indent=2))

        print(f"✅ Row {idx}: lat={pred_lat}, lon={pred_lon}, err={error_km}km, "
              f"time={elapsed:.1f}s, calls={token_summary.get('api_calls_count', 0)}, "
              f"tokens_in={token_summary.get('tokens_total_in', 0)}, "
              f"tokens_out={token_summary.get('tokens_total_out', 0)}")

    # ── Cleanup ───────────────────────────────────────────────
    csv_file.close()
    verbose_file.close()
    jsonl_file.close()
    summary_file.close()

    print(f"\n{'='*70}")
    print(f"📊 Benchmark complete! Results in {outdir}/")
    print(f"   • {csv_path}   — structured metrics")
    print(f"   • {verbose_path} — verbose console output")
    print(f"   • {jsonl_path}     — per-call LLM logs")
    print(f"   • {summary_path}   — final summary JSON per row")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
