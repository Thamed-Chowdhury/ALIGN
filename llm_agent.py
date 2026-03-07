# ============================================================
# llm_agent.py — Centralized LLM Configuration + Token Tracking
# ============================================================
# Change MODEL_NAME and PROVIDER here to switch ALL pipeline calls at once.
# No other file needs to be edited when switching models.
#
# Supported Providers:
#   "gemini" (Uses google-generativeai)
#   "openai" (Uses openai package - works for OpenAI, DeepSeek, Groq, Together, etc)
#   "qwen" (Uses openai package to connect to Alibaba Cloud DashScope)
#
# Supported Gemini models (examples):
#   "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"
#
# Supported OpenAI-compatible models (examples):
#   "gpt-4o-mini", "gpt-4o"
#   "deepseek-chat" (Set OPENAI_BASE_URL="https://api.deepseek.com")
#   "meta-llama/Llama-3.3-70B-Instruct" (For Together AI or similar)
# 
# Supported Qwen models (examples):
#   "qwen3.5-plus"
# ============================================================

PROVIDER = "together" # "gemini", "openai", "qwen", or "together"
MODEL_NAME = "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"
OPENAI_BASE_URL = None # Set to custom URL for DeepSeek or others e.g., "https://api.deepseek.com/v1" 
QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

import os
import sys
import time as _time
import google.generativeai as genai
from PIL import Image
import base64

# ── Reasoning-model helpers ────────────────────────────────────
# GPT-5 series, o1, o3, etc. are "reasoning" models that:
#   • Do NOT support `temperature`
#   • Require `max_completion_tokens` instead of `max_tokens`
#   • Need a high token limit because reasoning tokens count against it
_REASONING_PREFIXES = ("o1", "o3", "gpt-5")

def _is_reasoning_model(model_name: str = None) -> bool:
    """Return True if the current model is an OpenAI reasoning model."""
    name = (model_name or MODEL_NAME).lower()
    return any(name.startswith(p) for p in _REASONING_PREFIXES)

# ── Call Log Accumulator ──────────────────────────────────────
# Every LLM call is auto-recorded here.  The benchmark runner
# calls reset_log() before each article, then get_log() after.
_call_log: list[dict] = []
_current_stage: str = "unknown"
_success_stage: str = None  # Tracks which stage found final coords
_ai_inference_time: float = 0.0  # Cumulative AI time (seconds)


def set_stage(stage: str):
    """Set the current pipeline stage label (e.g. 'ner', 'rerank', 'vlm', 'vague')."""
    global _current_stage
    _current_stage = stage


def reset_log():
    """Clear the call log.  Call this before processing each article."""
    global _call_log, _success_stage, _ai_inference_time
    _call_log = []
    _success_stage = None
    _ai_inference_time = 0.0


def get_log() -> list[dict]:
    """Return a copy of all recorded LLM calls since the last reset."""
    return list(_call_log)


def get_token_summary() -> dict:
    """Aggregate token counts by stage from the call log."""
    summary = {}
    total_in = total_out = 0
    for entry in _call_log:
        stage = entry["stage"]
        key_in = f"tokens_{stage}_in"
        key_out = f"tokens_{stage}_out"
        summary[key_in] = summary.get(key_in, 0) + entry["input_tokens"]
        summary[key_out] = summary.get(key_out, 0) + entry["output_tokens"]
        total_in += entry["input_tokens"]
        total_out += entry["output_tokens"]
    summary["tokens_total_in"] = total_in
    summary["tokens_total_out"] = total_out
    summary["api_calls_count"] = len(_call_log)
    return summary


def set_success_stage(stage: str):
    """Mark which stage found the final coordinates."""
    global _success_stage
    _success_stage = stage


def get_success_stage() -> str:
    """Return the success stage, or 'Failed' if none set."""
    return _success_stage or "Failed"


def get_ai_inference_time() -> float:
    """Return cumulative AI inference time in seconds."""
    return _ai_inference_time


def _extract_token_usage_gemini(response) -> dict:
    """Extract token usage from a Gemini API response."""
    input_tokens = 0
    output_tokens = 0
    try:
        usage = response.usage_metadata
        input_tokens = getattr(usage, 'prompt_token_count', 0) or 0
        output_tokens = getattr(usage, 'candidates_token_count', 0) or 0
    except Exception:
        pass
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": MODEL_NAME}


def _extract_token_usage_openai(response) -> dict:
    """Extract token usage from an OpenAI Responses API response."""
    input_tokens = 0
    output_tokens = 0
    try:
        usage = response.usage
        input_tokens = getattr(usage, 'input_tokens', 0) or 0
        output_tokens = getattr(usage, 'output_tokens', 0) or 0
    except Exception:
        pass
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": MODEL_NAME}


def _extract_token_usage_qwen(response) -> dict:
    """Extract token usage from a Qwen API response."""
    input_tokens = 0
    output_tokens = 0
    try:
        usage = response.usage
        input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
        output_tokens = getattr(usage, 'completion_tokens', 0) or 0
    except Exception:
        pass
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": MODEL_NAME}


def _extract_token_usage_together(response) -> dict:
    """Extract token usage from a Together API response."""
    input_tokens = 0
    output_tokens = 0
    try:
        usage = response.usage
        input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
        output_tokens = getattr(usage, 'completion_tokens', 0) or 0
    except Exception:
        pass
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": MODEL_NAME}


def get_response(user_prompt: str, api_keys: list[str]) -> dict:
    """
    Text-only LLM call with API key rotation, supporting OpenAI and Gemini.
    """
    for idx, api_key in enumerate(api_keys, start=1):
        try:
            print(f"\n🔑 Trying API Key {idx}/{len(api_keys)}...")
            print(f"🤖 Model: {MODEL_NAME} (Provider: {PROVIDER})")
            print("🧠 Thinking...")

            t0 = _time.time()
            if PROVIDER == "gemini":
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(MODEL_NAME)
                response = model.generate_content(user_prompt)
                response_text = response.text
                token_info = _extract_token_usage_gemini(response)
            elif PROVIDER == "openai":
                import openai
                client = openai.OpenAI(api_key=api_key, base_url=OPENAI_BASE_URL)
                response = client.responses.create(
                    model=MODEL_NAME,
                    input=[{
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_prompt}]
                    }]
                )
                response_text = response.output_text
                token_info = _extract_token_usage_openai(response)
            elif PROVIDER == "qwen":
                import openai
                client = openai.OpenAI(api_key=api_key, base_url=QWEN_BASE_URL)
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": user_prompt}],
                    extra_body={'enable_thinking': False}
                )
                response_text = response.choices[0].message.content
                token_info = _extract_token_usage_qwen(response)
            elif PROVIDER == "together":
                from together import Together
                client = Together(api_key=api_key)
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                response_text = response.choices[0].message.content
                token_info = _extract_token_usage_together(response)
            else:
                raise ValueError(f"Unknown PROVIDER: {PROVIDER}")

            elapsed = _time.time() - t0

            print("\n✨ LLM Response:")
            print(response_text)

            result = {
                "text": response_text,
                **token_info,
            }
            # Accumulate AI inference time
            global _ai_inference_time
            _ai_inference_time += elapsed
            
            _call_log.append({
                "stage": _current_stage,
                "type": "text",
                "input_tokens": token_info["input_tokens"],
                "output_tokens": token_info["output_tokens"],
                "model": MODEL_NAME,
                "elapsed_s": round(elapsed, 2),
            })
            return result

        except Exception as e:
            print(f"\n❌ Error with API Key {idx}: {e}", file=sys.stderr)

    print("\n🚫 All API keys failed. Please check your keys.", file=sys.stderr)
    return {"text": None, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}


def get_response_with_images(api_keys: list[str], prompt: str,
                              image_paths: list[str],
                              ocr_texts: list[str] = None) -> dict:
    """
    Multimodal LLM call (text + images + OCR text) with API key rotation.
    Supports both Gemini and OpenAI providers.
    """
    print("len of image_paths", len(image_paths))
    print("len of ocr_texts", len(ocr_texts) if ocr_texts else "None (OCR disabled)")

    if PROVIDER == "gemini":
        prompt_parts = [prompt]
        valid_images_found = False

        for i, path in enumerate(image_paths):
            try:
                print(i)
                filename = os.path.basename(path)
                img = Image.open(path)

                prompt_parts.append(f"--- START OF IMAGE: {filename} ---")
                prompt_parts.append(img)
                if ocr_texts and i < len(ocr_texts) and ocr_texts[i]:
                    prompt_parts.append(f"--- OCR Extracted texts from IMAGE: {filename} ---\n{ocr_texts[i]}\n--- END OF OCR TEXTS ---\n")

                print(f"  \n────────────────────────────────────────────────────────────────\nFull prompt for image: {path}\n────────────────────────────────────────────────────────────────")
                valid_images_found = True
            except FileNotFoundError:
                print(f"⚠️ Warning: Image file not found at '{path}' — skipping this one.")

        if not valid_images_found:
            error_message = "❌ Error: No valid images found in the provided paths."
            print(error_message)
            return {"text": error_message, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}

    elif PROVIDER == "openai":
        content = [{"type": "input_text", "text": prompt}]
        valid_images_found = False
        
        for i, path in enumerate(image_paths):
            try:
                print(i)
                filename = os.path.basename(path)
                with open(path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
                content.append({"type": "input_text", "text": f"--- START OF IMAGE: {filename} ---"})
                
                # Determine image format
                ext = filename.split('.')[-1].lower()
                mime_type = "image/png" if ext == "png" else "image/jpeg"
                
                content.append({
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{base64_image}"
                })
                
                if ocr_texts and i < len(ocr_texts) and ocr_texts[i]:
                    content.append({"type": "input_text", "text": f"--- OCR Extracted texts from IMAGE: {filename} ---\n{ocr_texts[i]}\n--- END OF OCR TEXTS ---\n"})

                print(f"  \n────────────────────────────────────────────────────────────────\nFull prompt for image: {path}\n────────────────────────────────────────────────────────────────")
                valid_images_found = True
            except FileNotFoundError:
                print(f"⚠️ Warning: Image file not found at '{path}' — skipping this one.")

        if not valid_images_found:
            error_message = "❌ Error: No valid images found in the provided paths."
            print(error_message)
            return {"text": error_message, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}

    elif PROVIDER == "qwen":
        content = [{"type": "text", "text": prompt}]
        valid_images_found = False
        
        for i, path in enumerate(image_paths):
            try:
                print(i)
                filename = os.path.basename(path)
                with open(path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
                content.append({"type": "text", "text": f"--- START OF IMAGE: {filename} ---"})
                
                # Determine image format
                ext = filename.split('.')[-1].lower()
                mime_type = "image/png" if ext == "png" else "image/jpeg"
                
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                })
                
                if ocr_texts and i < len(ocr_texts) and ocr_texts[i]:
                    content.append({"type": "text", "text": f"--- OCR Extracted texts from IMAGE: {filename} ---\n{ocr_texts[i]}\n--- END OF OCR TEXTS ---\n"})

                print(f"  \n────────────────────────────────────────────────────────────────\nFull prompt for image: {path}\n────────────────────────────────────────────────────────────────")
                valid_images_found = True
            except FileNotFoundError:
                print(f"⚠️ Warning: Image file not found at '{path}' — skipping this one.")

        if not valid_images_found:
            error_message = "❌ Error: No valid images found in the provided paths."
            print(error_message)
            return {"text": error_message, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}
            
    elif PROVIDER == "together":
        content = [{"type": "text", "text": prompt}]
        valid_images_found = False
        
        for i, path in enumerate(image_paths):
            try:
                print(i)
                filename = os.path.basename(path)
                with open(path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
                content.append({"type": "text", "text": f"--- START OF IMAGE: {filename} ---"})
                
                # Determine image format
                ext = filename.split('.')[-1].lower()
                mime_type = "image/png" if ext == "png" else "image/jpeg"
                
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                })
                
                if ocr_texts and i < len(ocr_texts) and ocr_texts[i]:
                    content.append({"type": "text", "text": f"--- OCR Extracted texts from IMAGE: {filename} ---\n{ocr_texts[i]}\n--- END OF OCR TEXTS ---\n"})

                print(f"  \n────────────────────────────────────────────────────────────────\nFull prompt for image: {path}\n────────────────────────────────────────────────────────────────")
                valid_images_found = True
            except FileNotFoundError:
                print(f"⚠️ Warning: Image file not found at '{path}' — skipping this one.")

        if not valid_images_found:
            error_message = "❌ Error: No valid images found in the provided paths."
            print(error_message)
            return {"text": error_message, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}
    else:
        raise ValueError(f"Unknown PROVIDER: {PROVIDER}")

    for idx, api_key in enumerate(api_keys, start=1):
        try:
            print(f"\n🔑 Trying API Key {idx}/{len(api_keys)}...")
            print(f"🤖 Model: {MODEL_NAME} (Provider: {PROVIDER})")
            print("🧠 Thinking...")

            t0 = _time.time()
            if PROVIDER == "gemini":
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(MODEL_NAME)
                response = model.generate_content(prompt_parts)
                response_text = response.text
                token_info = _extract_token_usage_gemini(response)
            elif PROVIDER == "openai":
                import openai
                client = openai.OpenAI(api_key=api_key, base_url=OPENAI_BASE_URL)
                response = client.responses.create(
                    model=MODEL_NAME,
                    input=[{"role": "user", "content": content}]
                )
                response_text = response.output_text
                token_info = _extract_token_usage_openai(response)

            elif PROVIDER == "qwen":
                import openai
                client = openai.OpenAI(api_key=api_key, base_url=QWEN_BASE_URL)
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": content}],
                    extra_body={'enable_thinking': False}
                )
                response_text = response.choices[0].message.content
                token_info = _extract_token_usage_qwen(response)

            elif PROVIDER == "together":
                from together import Together
                client = Together(api_key=api_key)
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": content}]
                )
                response_text = response.choices[0].message.content
                token_info = _extract_token_usage_together(response)

            elapsed = _time.time() - t0

            print("\n✨ LLM Response:")
            print(response_text)
            print("-------------------------")

            result = {
                "text": response_text,
                **token_info,
            }
            # Accumulate AI inference time
            global _ai_inference_time
            _ai_inference_time += elapsed
            
            _call_log.append({
                "stage": _current_stage,
                "type": "multimodal",
                "input_tokens": token_info["input_tokens"],
                "output_tokens": token_info["output_tokens"],
                "model": MODEL_NAME,
                "elapsed_s": round(elapsed, 2),
            })
            return result

        except Exception as e:
            print(f"\n❌ Error with API Key {idx}: {e}", file=sys.stderr)

    error_message = "🚫 All API keys failed. Please check your keys."
    print(error_message, file=sys.stderr)
    return {"text": error_message, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}


# ── JSON Structured Output (Together AI only) ──────────────────
# These functions enforce a JSON schema on the model's response,
# guaranteeing consistent output format without regex parsing.

def get_response_json(user_prompt: str, api_keys: list[str],
                      json_schema: dict) -> dict:
    """
    Text-only LLM call with JSON structured output (Together AI only).
    Returns dict with 'text' (raw JSON string), 'parsed' (parsed dict), and token info.
    """
    if PROVIDER != "together":
        raise ValueError(f"JSON mode is only supported for 'together' provider, got '{PROVIDER}'")

    for idx, api_key in enumerate(api_keys, start=1):
        try:
            print(f"\n🔑 Trying API Key {idx}/{len(api_keys)}...")
            print(f"🤖 Model: {MODEL_NAME} (Provider: {PROVIDER}) [JSON Mode]")
            print("🧠 Thinking...")

            t0 = _time.time()
            from together import Together
            client = Together(api_key=api_key)
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": user_prompt}],
                response_format={
                    "type": "json_schema",
                    "schema": json_schema,
                }
            )
            response_text = response.choices[0].message.content
            token_info = _extract_token_usage_together(response)
            elapsed = _time.time() - t0

            print("\n✨ LLM Response (JSON):")
            print(response_text)

            import json as _json
            try:
                parsed = _json.loads(response_text)
            except _json.JSONDecodeError:
                parsed = None
                print("⚠️ Warning: Response was not valid JSON despite json_schema mode.")

            global _ai_inference_time
            _ai_inference_time += elapsed

            _call_log.append({
                "stage": _current_stage,
                "type": "text_json",
                "input_tokens": token_info["input_tokens"],
                "output_tokens": token_info["output_tokens"],
                "model": MODEL_NAME,
                "elapsed_s": round(elapsed, 2),
            })
            return {
                "text": response_text,
                "parsed": parsed,
                **token_info,
            }

        except Exception as e:
            print(f"\n❌ Error with API Key {idx}: {e}", file=sys.stderr)

    print("\n🚫 All API keys failed. Please check your keys.", file=sys.stderr)
    return {"text": None, "parsed": None, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}


def get_response_with_images_json(api_keys: list[str], prompt: str,
                                   image_paths: list[str],
                                   ocr_texts: list[str] = None,
                                   json_schema: dict = None) -> dict:
    """
    Multimodal LLM call with JSON structured output (Together AI only).
    Returns dict with 'text', 'parsed', and token info.
    """
    if PROVIDER != "together":
        raise ValueError(f"JSON mode is only supported for 'together' provider, got '{PROVIDER}'")

    print("len of image_paths", len(image_paths))
    print("len of ocr_texts", len(ocr_texts) if ocr_texts else "None (OCR disabled)")

    content = [{"type": "text", "text": prompt}]
    valid_images_found = False

    for i, path in enumerate(image_paths):
        try:
            print(i)
            filename = os.path.basename(path)
            with open(path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')

            content.append({"type": "text", "text": f"--- START OF IMAGE: {filename} ---"})

            ext = filename.split('.')[-1].lower()
            mime_type = "image/png" if ext == "png" else "image/jpeg"

            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
            })

            if ocr_texts and i < len(ocr_texts) and ocr_texts[i]:
                content.append({"type": "text", "text": f"--- OCR Extracted texts from IMAGE: {filename} ---\n{ocr_texts[i]}\n--- END OF OCR TEXTS ---\n"})

            print(f"  \n{'─'*64}\nFull prompt for image: {path}\n{'─'*64}")
            valid_images_found = True
        except FileNotFoundError:
            print(f"⚠️ Warning: Image file not found at '{path}' — skipping this one.")

    if not valid_images_found:
        error_message = "❌ Error: No valid images found in the provided paths."
        print(error_message)
        return {"text": error_message, "parsed": None, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}

    for idx, api_key in enumerate(api_keys, start=1):
        try:
            print(f"\n🔑 Trying API Key {idx}/{len(api_keys)}...")
            print(f"🤖 Model: {MODEL_NAME} (Provider: {PROVIDER}) [JSON Mode + Vision]")
            print("🧠 Thinking...")

            t0 = _time.time()
            from together import Together
            client = Together(api_key=api_key)

            create_kwargs = {
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": content}],
            }
            if json_schema:
                create_kwargs["response_format"] = {
                    "type": "json_schema",
                    "schema": json_schema,
                }

            response = client.chat.completions.create(**create_kwargs)
            response_text = response.choices[0].message.content
            token_info = _extract_token_usage_together(response)
            elapsed = _time.time() - t0

            print("\n✨ LLM Response (JSON + Vision):")
            print(response_text)
            print("-------------------------")

            import json as _json
            try:
                parsed = _json.loads(response_text)
            except _json.JSONDecodeError:
                parsed = None
                print("⚠️ Warning: Response was not valid JSON despite json_schema mode.")

            global _ai_inference_time
            _ai_inference_time += elapsed

            _call_log.append({
                "stage": _current_stage,
                "type": "multimodal_json",
                "input_tokens": token_info["input_tokens"],
                "output_tokens": token_info["output_tokens"],
                "model": MODEL_NAME,
                "elapsed_s": round(elapsed, 2),
            })
            return {
                "text": response_text,
                "parsed": parsed,
                **token_info,
            }

        except Exception as e:
            print(f"\n❌ Error with API Key {idx}: {e}", file=sys.stderr)

    error_message = "🚫 All API keys failed. Please check your keys."
    print(error_message, file=sys.stderr)
    return {"text": error_message, "parsed": None, "input_tokens": 0, "output_tokens": 0, "model": MODEL_NAME}

