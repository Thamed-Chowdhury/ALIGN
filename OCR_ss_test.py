import cv2
import math
import os
import re
import unicodedata
from thefuzz import process, fuzz
import torch
import easyocr

ocr_reader = easyocr.Reader(['bn', 'en'], gpu=torch.cuda.is_available())


def chunkwise_OCR_agent(places, image_path, crop_height=500, crop_width=1000, overlap=50, similarity_threshold=75):
    """
    Performs part-wise OCR + fuzzy matching on a large image.
    Returns both the match result (bool) and all extracted OCR text lines.

    Args:
        places (list): List of Bengali/English place names to search for.
        image_path (str): Path to the input image.
        crop_height (int): Height of each chunk in pixels.
        crop_width (int): Width of each chunk in pixels.
        overlap (int): Overlap between chunks (for avoiding cut-off text).
        similarity_threshold (int): Fuzzy similarity score threshold.

    Returns:
        tuple: (found: bool, all_detected_text: list[str])
    """

    # ---------------- Helper: Normalize Bengali text ----------------
    def normalize_bengali_text(text: str) -> str:
        if not text:
            return ""
        text = unicodedata.normalize("NFC", text)
        text = re.sub(r"[^ঀ-৿a-zA-Z0-9\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ---------------- Read Image ----------------
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        return False, []

    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ Could not read image: {image_path}")
        return False, []

    img_height, img_width = image.shape[:2]
    num_rows = math.ceil(img_height / (crop_height - overlap))
    num_cols = math.ceil(img_width / (crop_width - overlap))
    print(f"🖼️ Image size: {img_width}x{img_height}")
    print(f"🔹 Splitting into {num_rows} rows × {num_cols} cols...")

    all_detected_text = []

    # ---------------- OCR on Each Chunk ----------------
    chunk_idx = 0
    for i in range(num_rows):
        for j in range(num_cols):
            y1 = i * (crop_height - overlap)
            y2 = min(y1 + crop_height, img_height)
            x1 = j * (crop_width - overlap)
            x2 = min(x1 + crop_width, img_width)

            cropped_chunk = image[y1:y2, x1:x2]

            # Preprocess for OCR
            gray = cv2.cvtColor(cropped_chunk, cv2.COLOR_BGR2GRAY)
            _, bw = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY_INV)
            upscaled = cv2.resize(bw, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

            # Run OCR
            results = ocr_reader.readtext(upscaled)
            chunk_texts = [r[1] for r in results]
            print(f"🧩 Chunk {chunk_idx}: {len(chunk_texts)} text blocks detected.")
            all_detected_text.extend(chunk_texts)
            chunk_idx += 1

    if not all_detected_text:
        print("❌ No text detected in any chunk.")
        return False, ""

    # ---------------- Aggregate & Normalize ----------------
    full_text_block = "\n".join(all_detected_text)
    print("\n📜 Combined OCR Text:\n-----------------------------------")
    print(full_text_block)
    print("-----------------------------------\n")

    normalized_choices = [normalize_bengali_text(t) for t in all_detected_text if t.strip()]
    choices = [c for c in normalized_choices if len(c) >= 3]

    if not choices:
        print("❌ No valid text lines after normalization.")
        return False, full_text_block

    # ---------------- Fuzzy Matching ----------------
    def hybrid_score(a, b):
        score1 = fuzz.token_sort_ratio(a, b)
        score2 = fuzz.partial_ratio(a, b)
        return (score1 + score2) / 2

    for place_name in places:
        print(f"🔹 Checking for: '{place_name}'")
        place_to_find = normalize_bengali_text(place_name)
        best_match = process.extractOne(place_to_find, choices, scorer=hybrid_score)

        if not best_match:
            print(f"   ❌ No close match found for '{place_to_find}'.")
            continue

        best_match_text, score = best_match
        print(f"   🔎 Best match: '{best_match_text}'  (Similarity: {score:.1f}%)")

        if score >= similarity_threshold:
            print(f"   ✅ SUCCESS: Found match for '{place_name}' (≥{similarity_threshold}%).")
            return True, full_text_block

    print("\n❌ No matches found for any place.")
    return False, full_text_block


