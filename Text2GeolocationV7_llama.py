# ── Selenium Config ──────────────────────────────────────
SELENIUM_HEADLESS = True  # Set True for headless (no visible Chrome window)

# ── Selenium Timing Tracker ──────────────────────────────
import time
_selenium_time_cumulative = 0.0

class _SeleniumTimer:
    """Context manager to time Selenium operations."""
    def __init__(self):
        self.start = None
    def __enter__(self):
        self.start = time.time()
        return self
    def __exit__(self, *args):
        global _selenium_time_cumulative
        _selenium_time_cumulative += time.time() - self.start

def get_selenium_time() -> float:
    """Return cumulative Selenium time in seconds."""
    return _selenium_time_cumulative

def reset_selenium_time():
    """Reset cumulative Selenium time to 0."""
    global _selenium_time_cumulative
    _selenium_time_cumulative = 0.0

def geolocation_agent(news_string:str, Gemini_API_Keys: list[str]): 
    # Reset timing for this run
    reset_selenium_time() 
    import llm_agent
    import sys
    import json

    # ── JSON Schemas for Together AI structured output ──────────
    NER_SCHEMA = {
        "type": "object",
        "properties": {
            "road_name": {"type": "string", "description": "Road name or 'Not Available'"},
            "road_type": {"type": "string", "description": "Road type or 'Not Available'"},
            "landmark": {"type": "string", "description": "Accident landmark or 'Not Available'"},
            "union": {"type": "string", "description": "Union name or 'Not Available'"},
            "zilla": {"type": "string", "description": "Zilla name or 'Not Available'"},
            "upazilla": {"type": "string", "description": "Upazilla name or 'Not Available'"},
            "thana": {"type": "string", "description": "Thana name or 'Not Available'"},
            "district": {"type": "string", "description": "District name or 'Not Available'"},
            "sug_str": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of Google Maps search hit strings (max 20: 12 Bangla + 8 English)"
            },
            "place_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "All place names from article in both English and Bangla"
            }
        },
        "required": ["road_name", "road_type", "landmark", "union", "zilla", "upazilla", "thana", "district", "sug_str", "place_list"]
    }

    RERANK_SCHEMA = {
        "type": "object",
        "properties": {
            "best_suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group": {"type": "integer", "description": "Group number"},
                        "best": {"type": "string", "description": "Best suggestion text or 'Not Valid'"}
                    },
                    "required": ["group", "best"]
                },
                "description": "One best suggestion per group"
            }
        },
        "required": ["best_suggestions"]
    }

    VLM_SCHEMA = {
        "type": "object",
        "properties": {
            "screenshots": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Screenshot filename e.g. screenshot_1.png"},
                        "boundary_reasoning": {"type": "string", "description": "2-4 bullets describing visible cues"},
                        "isRedBounded": {"type": "string", "enum": ["Yes", "No"], "description": "Whether map shows red boundary"},
                        "extracted_map_labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "All readable map labels"
                        },
                        "incident_landmarks": {"type": "string", "description": "Incident landmarks quoted from article"},
                        "non_incident_mentions": {"type": "string", "description": "Non-incident mentions quoted"},
                        "map_labels_used": {"type": "string", "description": "Map labels used for matching"},
                        "road_equivalence_used": {"type": "string", "description": "Yes/No and basis"},
                        "requirement_check": {"type": "string", "description": "Incident Landmark = Pass/Fail; Road = Pass/Fail"},
                        "justification": {"type": "string", "description": "Brief 1-3 line justification"},
                        "isSame": {"type": "string", "enum": ["Yes", "No"], "description": "Whether map shows same location"},
                        "landmark_match": {"type": "string", "description": "Matching landmark text if isSame=Yes, else empty"}
                    },
                    "required": ["filename", "isRedBounded", "isSame"]
                },
                "description": "Analysis results for each screenshot"
            }
        },
        "required": ["screenshots"]
    }

    def get_gemini_response(user_prompt: str, Gemini_API_Keys: list[str]) -> str:
        """Text-only LLM call. Delegates to llm_agent.get_response()."""
        result = llm_agent.get_response(user_prompt, Gemini_API_Keys)
        return result["text"]

    def get_gemini_response_json(user_prompt: str, Gemini_API_Keys: list[str], json_schema: dict) -> dict:
        """Text-only LLM call with JSON schema. Delegates to llm_agent.get_response_json()."""
        result = llm_agent.get_response_json(user_prompt, Gemini_API_Keys, json_schema)
        return result

    prompt_1 = f"""
    You are given a Bangladeshi accident news article in Bengali. Your job is to extract and structure the location information to help pinpoint the accident spot on Google Maps. 
    Follow these steps strictly: 

    1) Extract all location mentions from the news. 

    2) Organize them into the following categories: 
    Road name (if the news mentions a specific highway, expressway, or road, list it here), 
    Road Type (Mention the type of road here such as, highway, expressway etc.), 
    Landmark (specific named places, excluding suffixes like 'এলাকা', 'থানা', 'উপজেলা'; if multiple landmarks are mentioned, list them separately; Be careful that the landmark must be the place where the accident took place. Landmarks related to other events must be ignored.), 
    Union (name of the union if available, otherwise write "Not Available"), 
    Zilla (name of the zilla), 
    Upazilla (name of the upazilla), 
    Thana (name of the thana without the word 'থানা'), 
    District (name of the district). 

    3) Do not include suffix words like 'এলাকা', 'থানা', or 'উপজেলা' in the extracted names—keep only the core name. 
    CRITICAL RULE FOR GENERIC NAMES: If the core name is a generic administrative term like 'সদর' (Sadar) or 'সদর থানা' or 'সদর উপজেলা', it is highly ambiguous on its own. You MUST COMPLETELY PREVENT extracting just 'সদর' or 'সদর থানা' alone. You MUST prepend the District/Zilla name to it to ensure it is unambiguous (e.g., extract 'গাজীপুর সদর' or 'নাটোর সদর' instead of just 'সদর'). If the district cannot be determined from the news, do NOT extract 'সদর' at all.

    4) After structuring the data, generate a list of possible Google Maps search hit strings. Each string should contain at most two levels of administrative areas. 
    Arrange them so that lower-level areas (Landmark, Union) come before higher-level areas (Upazilla, Zilla, District). 
    Example: 'Landmark + Upazilla', 'Landmark + District', 'Road + Landmark'. 
    Provide both Bengali and English search hit strings.
    WARNING: When generating search hit strings (`<sug_str>`), NEVER use 'সদর' (Sadar) or 'সদর উপজেলা' (Sadar Upazila) or 'সদর থানা' without its accompanying District name. 'সদর' MUST always be prefixed by the District (e.g. 'নাটোর সদর'). If you cannot determine the district, do not use 'সদর' in any `<sug_str>`.

    ───────────────────────────────────────────────
    🔍 **MAPS DIVERSITY & FUZZY VARIANT RULES**
    ───────────────────────────────────────────────
    To maximize Google Maps match accuracy, follow these additional generation rules when producing <sug_str> entries:

    1️⃣ **Short + Long Forms**
    - Always include both short (single-token) and long (compound) search variants.  
    Example: output both  
    <sug_str> তেরো মাইল <sug_str>  
    and  
    <sug_str> তেরো মাইল মোড়, মহাদেবপুর <sug_str>  

    2️⃣ **Fused and Separated Word Variants**
    - If a Bangla word combines a number and a unit (e.g., “তেরোমাইল”),  
    also generate a separated version (e.g., “তেরো মাইল”).  
    Example:  
    <sug_str> তেরোমাইল <sug_str>  
    <sug_str> তেরো মাইল <sug_str>  
    <sug_str> Tero Mile <sug_str>  

    3️⃣ **Root-Token Fallbacks for POIs**
    - If a landmark ends with a generic facility name such as  
    “পেট্রোলপাম্প”, “ফিলিং স্টেশন”, “মোড়”, “বাজার”, “মসজিদ”, “কলেজ”,  
    also include a shorter variant with only its root token.  
    Example:  
    “ইলিয়াস পেট্রোলপাম্প” →  
    <sug_str> ইলিয়াস পেট্রোলপাম্প <sug_str>  
    <sug_str> ইলিয়াস <sug_str>  
    <sug_str> Elias Refueling Station N1 Kumira <sug_str>  

    4️⃣ **Cross-Language Expansion**
    - Provide both Bengali and English transliterations for every variant.  
    Example:  
    <sug_str> তেরো মাইল <sug_str>  
    <sug_str> Tero Mile <sug_str>  

    5️⃣ **Granularity Levels**
    - Include progressively broader combinations:  
    (a) Landmark only  
    (b) Landmark + Upazilla  
    (c) Landmark + District  
    (d) Road + Landmark  
    Example:  
    <sug_str> তেরো মাইল <sug_str>  
    <sug_str> তেরো মাইল, মহাদেবপুর <sug_str>  
    <sug_str> তেরো মাইল, নওগাঁ <sug_str>  
    <sug_str> নওহাটা-মহাদেবপুর সড়ক, তেরো মাইল <sug_str>

    6️⃣ **Semantic Synonym Expansion for Better Map Matching**
    - Google Maps may use different English or standardized facility terms than the ones mentioned in the news. 
    Therefore, also generate semantic variants that capture the same place type but with Google Maps–style words.
    For example:
    - “পেট্রোলপাম্প”, “ফিলিং স্টেশন” → “Refueling Station”, “Filling Station”, “Fuel Station”
    - “মোড়”, “চৌরাস্ত”, “চক” → “Junction”, “Intersection”, “Crossing”
    - “বাজার” → “Market”, “Bazaar”
    - “কলেজ” → “College”
    - “স্কুল” → “School”
    - “হাসপাতাল” → “Hospital”
    - “মসজিদ” → “Mosque”
    - “মন্দির” → “Temple”
    - “ব্রিজ” → “Bridge”
    - “ঘাট” → “Ghat”
    - You should generate multiple such search variants combining these English equivalents with local names.
    - Example:
    - “ইলিয়াস পেট্রোলপাম্প” → “Elias Refueling Station”, “Elias Filling Station”, “Elias Fuel Station”
    - “তেরো মাইল মোড়” → “Tero Mile Junction”, “Tero Mile Crossing”
    - “আলমবাজার” → “Alam Market”, “Alam Bazaar”  

    ───────────────────────────────────────────────
    🧩 **Goal**
    ───────────────────────────────────────────────
    The <sug_str> list should be rich, semantically diverse, and contain both short, long, Bengali, and English forms of the same landmark.  
    Prefer realistic spellings that Google Maps is likely to recognize directly. Include a few strings without the suffix words like মোড়, চৌরাস্ত etc.  

    ───────────────────────────────────────────────

    5) The output should include: Structured location information (organized in the specified categories) and a list of possible Google Maps search hit strings arranged from most specific to broader scope. Provide both Bengali and English search hit strings. Generate a maximum of 20 suggestions: 12 Bangla, 8 English.

    6) Finally, list all the place names that appear in the news article. The place names must be in both English and Bangla. Only extract proper place names that refer to administrative or settlement units (districts, upazilas, cities, towns, villages, or unions).
    ✅ Example: ["Dhaka", "ঢাকা", "Sylhet", "সিলেট", "Feni", "ফেনী"]
    Exclude descriptive or geographic region labels that are not official administrative places.
    ❌ Do not include: "Hill Tracts", "Division", "Province", "Highway", "River", "Bridge", "Station", etc.

    7) You MUST respond ONLY with a valid JSON object. Do NOT include any text outside the JSON.
    The JSON schema is:
    {{
      "road_name": "Actual Road Name or Not Available",
      "road_type": "Actual Road Type or Not Available",
      "landmark": "Actual Landmark or Not Available",
      "union": "Actual Union or Not Available",
      "zilla": "Actual Zilla Name or Not Available",
      "upazilla": "Actual Upazilla Name or Not Available",
      "thana": "Actual Thana Name or Not Available",
      "district": "Actual District Name or Not Available",
      "sug_str": ["suggestion 1", "suggestion 2", ...],
      "place_list": ["Place1", "প্লেস১", "Place2", "প্লেস২", ...]
    }}

    If any of the above information is not mentioned or cannot be confidently inferred from the news article, write "Not Available" in that field instead of leaving it blank.

    News Article:
    {news_string}
    """


    llm_agent.set_stage("ner")
    import re

    # Use JSON structured output for NER extraction
    ner_result = get_gemini_response_json(prompt_1, Gemini_API_Keys, NER_SCHEMA)
    ner_parsed = ner_result.get("parsed")
    response_string_1 = ner_result.get("text", "")

    if ner_parsed:
        # Direct JSON access — no regex needed!
        matches = ner_parsed.get("sug_str", [])
        # Strip whitespace from each suggestion
        matches = [s.strip() for s in matches if s.strip()]
        # Deduplicate while preserving order
        seen = set()
        matches = [x for x in matches if not (x in seen or seen.add(x))]
        print("✅ sug_str extracted via JSON:", matches)

        places = ner_parsed.get("place_list", [])
        places = [p.strip() for p in places if p.strip()]
        print("✅ place_list extracted via JSON:", places)

        # Build extracted_text for road lookup (simulate the old <place> separated format)
        extracted_text = "<place>".join(places)
    else:
        # Fallback: regex parsing if JSON failed
        print("⚠️ JSON parsing failed, falling back to regex extraction.")
        text = response_string_1 or ""
        matches = re.findall(r"<sug_str>(.*?)</?sug_str>", text)
        seen = set()
        matches = [x.strip() for x in matches if not (x.strip() in seen or seen.add(x.strip()))]
        print(matches)

        matches2 = re.findall(r"<place_list>(.*?)</?place_list>", text, flags=re.DOTALL)
        if matches2:
            extracted_text = matches2[0]
            print(extracted_text.strip())
        else:
            extracted_text = ""
            print("No match found.")
        places = [p.strip() for p in extracted_text.split("<place>") if p.strip()]
        print(places)

    import json
    from difflib import get_close_matches
    # 🔹 Load your scraped road data
    with open("bd_roads.json", "r", encoding="utf-8") as f:
        road_data = json.load(f)

    # 🔹 Alias map (expandable)
    alias_map = {
        "chattogram": "chittagong",
        "cumilla": "comilla",
        "barishal": "barisal",
        "jashore": "jessore",
        "bogura": "bogra",
        "sirajganj": "sirajgonj"
    }

    def normalize_place(place):
        """Normalize place names with alias + fuzzy alias check."""
        key = place.lower().strip()
        if key in alias_map:
            return alias_map[key]
        close = get_close_matches(key, alias_map.keys(), n=1, cutoff=0.8)
        if close:
            return alias_map[close[0]]
        return place

    def find_roads_fuzzy(input_str, road_data, cutoff=0.7):
        """Find all roads containing or fuzzily matching the place name."""
        places = [p.strip() for p in input_str.split("<place>") if p.strip()]
        results = []

        for place in places:
            norm_place = normalize_place(place)

            for code, info in road_data.items():
                coverage = info["coverage"]
                category = info["category"]

                # Direct substring match
                if norm_place.lower() in coverage.lower():
                    results.append(f"{code}\t{coverage}")
                else:
                    # Fuzzy match against words in coverage
                    words = [w.strip() for w in coverage.replace("–", "-").split("-")]
                    close = get_close_matches(norm_place, words, n=1, cutoff=cutoff)
                    if close:
                        results.append(f"{code}\t{coverage})")

        return "\n".join(results)


    # 🔹 Example usage
    input_text = extracted_text
    road_data_fuzzy = find_roads_fuzzy(input_text, road_data)
    print(road_data_fuzzy)

    import re
    import time
    import google.generativeai as genai
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    def GetGoogleMapsSuggestions(SEARCH_QUERY, max_wait=8):
        """
        Returns all visible autocomplete suggestions from Google Maps for a given query.
        Does NOT click anything.
        """
        print(f"🔍 Collecting Google Maps suggestions for: {SEARCH_QUERY}")

        options = webdriver.ChromeOptions()
        if SELENIUM_HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=options)
        driver.set_window_size(1920, 1080)

        try:
            with _SeleniumTimer():
                driver.get("https://www.google.com/maps")
            search_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='q']"))
            )
            search_box.clear()
            search_box.send_keys(SEARCH_QUERY)

            # Wait for suggestions to appear
            suggestion_elems = WebDriverWait(driver, max_wait).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[data-suggestion-index]'))
            )
            time.sleep(2)
            suggestions = [elem.text.strip() for elem in suggestion_elems if elem.text.strip()]
            print(f"✅ Found {len(suggestions)} suggestions for '{SEARCH_QUERY}'.")
            return suggestions

        except Exception as e:
            print(f"⚠️ Suggestion collection failed for '{SEARCH_QUERY}': {e}")
            return []
        finally:
            driver.quit()


    def filter_invalid_suggestions(suggestions):
        """
        Filters out generic fallback suggestions like
        'Google Maps-এ অনুপস্থিত ব্যবসা বা ল্যান্ডমার্ক যোগ করুন' etc.
        """
        invalid_phrases = [
            "Google Maps-এ অনুপস্থিত ব্যবসা",
            "ল্যান্ডমার্ক যোগ করুন",
            "Add a missing business or landmark",
        ]
        filtered = [
            s for s in suggestions
            if not any(phrase in s for phrase in invalid_phrases)
        ]
        return filtered


    def enhanced_search_pipeline_batch(news_string, Gemini_API_Keys, response_string_1, sug_str_list=None):
        """
        Optimized pipeline:
        1️⃣ Collect Google Maps suggestions for all sug_str first.
        2️⃣ Make ONE LLM call (JSON mode) to rerank them all together.
        3️⃣ Parse the JSON output and return only valid best suggestions per group.
        """
        # Step 1: Use pre-extracted sug_str list (from JSON), or fallback to regex
        if sug_str_list:
            search_strings = sug_str_list
        else:
            search_strings = re.findall(r"<sug_str>(.*?)</?sug_str>", response_string_1)
            search_strings = [s.strip() for s in search_strings if s.strip()]
        sug_map = {}

        print("\n🧭 Step 1: Collecting Google Maps suggestions for all search strings...")
        for q in search_strings:
            print(f"🔍 Fetching suggestions for: {q}")
            suggestions = GetGoogleMapsSuggestions(q)
            suggestions = filter_invalid_suggestions(suggestions)
            sug_map[q] = suggestions or []
            time.sleep(1.5)

        if not sug_map:
            print("⚠️ No valid suggestions found for any sug_str.")
            return []

        # Step 2: Build one large prompt for batch reranking (JSON mode)
        print("\n🧠 Step 2: Preparing batch reranking prompt (JSON mode)...")
        group_blocks = []
        for idx, (query, sug_list) in enumerate(sug_map.items(), start=1):
            sug_block = "\n".join(sug_list) if sug_list else "No valid suggestions found"
            group_blocks.append(
                f"Group {idx}:\nOriginal Query: {query}\nSuggestions:\n{sug_block}\n"
            )

        big_prompt = f"""
    You are given a Bangladeshi accident news article and multiple groups of Google Maps autocomplete suggestions.
    Each group corresponds to one search query. For each group, select the SINGLE suggestion that most
    accurately represents the intended accident location mentioned in the news.

    RULES:
    - Consider the geographic context of the accident described in the news.
    - Ignore generic fallback suggestions.
    - If none of the suggestions are relevant, use "Not Valid" as the best.
    - Do not include any explanation or reasoning.

    📰 NEWS ARTICLE:
    {news_string}

    Groups to process:
    {chr(10).join(group_blocks)}

    You MUST respond ONLY with a valid JSON object following this schema:
    {{
      "best_suggestions": [
        {{"group": 1, "best": "Best suggestion text or Not Valid"}},
        {{"group": 2, "best": "Best suggestion text or Not Valid"}},
        ...
      ]
    }}
    """

        # Step 3: Send one LLM request with JSON mode
        print("\n⚙️ Step 3: Sending batch reranking request to LLM (JSON mode)...")
        llm_agent.set_stage("rerank")
        rerank_result = get_gemini_response_json(big_prompt, Gemini_API_Keys, RERANK_SCHEMA)
        rerank_parsed = rerank_result.get("parsed")

        if not rerank_parsed:
            # Fallback: try regex on raw text
            print("⚠️ JSON reranking failed, falling back to regex.")
            raw_response = rerank_result.get("text", "")
            text = raw_response.strip() if raw_response else None
            if not text:
                print("❌ All LLM keys failed.")
                return []

            best_suggestions = []
            invalid_terms = ["Not Valid", "Not Available", "No valid", "None"]
            for i in range(1, len(sug_map) + 1):
                match_obj = re.search(rf"<best_{i}>(.*?)</?best_{i}>", text, re.DOTALL)
                if match_obj:
                    suggestion = match_obj.group(1).strip()
                    if suggestion and not any(term.lower() in suggestion.lower() for term in invalid_terms):
                        best_suggestions.append(suggestion)
                else:
                    key_q = list(sug_map.keys())[i - 1]
                    if sug_map[key_q]:
                        fallback = sug_map[key_q][0]
                        if not any(term.lower() in fallback.lower() for term in invalid_terms):
                            best_suggestions.append(fallback)
            print("\n📋 ✅ Final Valid Best Suggestions (regex fallback):")
            for idx, s in enumerate(best_suggestions, start=1):
                print(f" {idx}. {s}")
            return best_suggestions

        # Step 4: Parse JSON results
        print("\n🧩 Step 4: Parsing reranked results from JSON...")
        best_suggestions = []
        invalid_terms = ["Not Valid", "Not Available", "No valid", "None"]

        for entry in rerank_parsed.get("best_suggestions", []):
            suggestion = entry.get("best", "").strip()
            if suggestion and not any(term.lower() in suggestion.lower() for term in invalid_terms):
                best_suggestions.append(suggestion)

        print("\n📋 ✅ Final Valid Best Suggestions (JSON):")
        for idx, s in enumerate(best_suggestions, start=1):
            print(f" {idx}. {s}")

        return best_suggestions

    # Example call (assuming the variables above are defined):
    best_suggestions = enhanced_search_pipeline_batch(news_string, Gemini_API_Keys, response_string_1, sug_str_list=matches)
    print("\n✅ Use these for map verification or screenshot generation:")
    print(best_suggestions)
    matches = best_suggestions

    def GoogleMapsSearch(SEARCH_QUERY, filename):
        # --- Main Script ---

        print("Setting up WebDriver...")
        # Using webdriver-manager to handle the driver automatically
        options = webdriver.ChromeOptions()
        if SELENIUM_HEADLESS:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)

        # 🔹 Force exact screen metrics (1920x1080)
        driver.set_window_size(1920, 1080)
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 1920,
            "height": 1080, # 857 in calibration
            "deviceScaleFactor": 1,
            "mobile": False
        })

        print("WebDriver setup complete.")


        # 1) Go to the Google Maps website.
        # Using the standard URL for better reliability
        url = "https://www.google.com/maps"
        print(f"Navigating to: {url}")
        with _SeleniumTimer():
            driver.get(url)
        driver.maximize_window()

        # 2) Find the search bar and paste the search string.
        print(f"Searching for: '{SEARCH_QUERY}'")
        search_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='q']"))
        )
        search_box.clear()
        search_box.send_keys(SEARCH_QUERY)

        # 3) Wait for the first suggestion to be clickable and then click it.
        # --- MODIFIED SECTION AS REQUESTED ---
        print("Waiting for the first suggestion to appear and become clickable...")

        # Define the CSS selector for the first suggestion.
        first_suggestion_selector = 'div[data-suggestion-index="0"]'

        # Use WebDriverWait to robustly wait for the element to be clickable.
        try:
            first_suggestion = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, first_suggestion_selector))
            )
            print("Clicking the first suggestion...")
            with _SeleniumTimer():
                first_suggestion.click()

            # --- END OF MODIFIED SECTION ---

            print("Search successful! The map is now showing the location.")
            time.sleep(10)
            with _SeleniumTimer():
                driver.save_screenshot(filename)
            driver.quit()
        except:
            print("No first suggestion Exists")
            driver.quit()
            pass

    def GetLocationURL(SEARCH_QUERY):
        # --- Main Script ---

        print("Setting up WebDriver...")
        # Using webdriver-manager to handle the driver automatically
        options = webdriver.ChromeOptions()
        if SELENIUM_HEADLESS:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)

        # 🔹 Force exact screen metrics (1920x1080)
        driver.set_window_size(1920, 1080)
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 1920,
            "height": 1080,
            "deviceScaleFactor": 1,
            "mobile": False
        })

        print("WebDriver setup complete.")


        # 1) Go to the Google Maps website.
        # Using the standard URL for better reliability
        url = "https://www.google.com/maps"
        print(f"Navigating to: {url}")
        with _SeleniumTimer():
            driver.get(url)
        driver.maximize_window()
        # 2) Find the search bar and paste the search string.
        print(f"Searching for: '{SEARCH_QUERY}'")
        search_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='q']"))
        )
        search_box.clear()
        search_box.send_keys(SEARCH_QUERY)

        # 3) Wait for the first suggestion to be clickable and then click it.
        # --- MODIFIED SECTION AS REQUESTED ---
        print("Waiting for the first suggestion to appear and become clickable...")

        # Define the CSS selector for the first suggestion.
        first_suggestion_selector = 'div[data-suggestion-index="0"]'

        # Use WebDriverWait to robustly wait for the element to be clickable.
        try:
            first_suggestion = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, first_suggestion_selector))
            )
            print("Clicking the first suggestion...")
            with _SeleniumTimer():
                first_suggestion.click()

            # --- END OF MODIFIED SECTION ---

            print("Search successful! The map is now showing the location.")
            # Get the current URL
            time.sleep(5)
            current_url = driver.current_url
            driver.quit()
            return current_url
        except:
            print("No first suggestion Exists")
            driver.quit()
            pass
    import os

    def get_gemini_response_with_screenshots(api_keys: list[str], prompt: str, image_paths: list[str], OCR_texts: list[str]):
        """Multimodal LLM call. Delegates to llm_agent.get_response_with_images()."""
        result = llm_agent.get_response_with_images(api_keys, prompt, image_paths, OCR_texts)
        return result["text"]

    def get_gemini_response_with_screenshots_json(api_keys: list[str], prompt: str, image_paths: list[str], OCR_texts: list[str], json_schema: dict = None):
        """Multimodal LLM call with JSON structured output. Delegates to llm_agent.get_response_with_images_json()."""
        result = llm_agent.get_response_with_images_json(api_keys, prompt, image_paths, OCR_texts, json_schema)
        return result

    def ss_checking_agent(news_string, Gemini_API_Keys, image_paths: list[str], OCR_texts: list[str]):
        # The prompt is now updated to refer to filenames instead of ordered indices.
        prompt_2 = f"""
    You will be given:
    • Multiple screenshots of Google Maps views. Each screenshot will be preceded by its filename (e.g., "--- START OF IMAGE: filename.png ---").
    • One news article text describing a road accident location.

    Your task: for **each screenshot independently**, decide if that map view shows the **same location as the accident site** described in the article. Do not combine evidence across screenshots—judge each one on its own.

    ────────────────────────────────────────────────────────────────
    IMPORTANT VIEW RULES
    ────────────────────────────────────────────────────────────────
    - Treat only the **map canvas labels** as evidence (ignore side panels/photos/UI).
    - **You must ignore all text outside the main map canvas area.**  
    This includes:
    - Left or right sidebar panels (place info, reviews, addresses, etc.)
    - Top or bottom search bars, popups, and info cards
    - Photo thumbnails, ratings, or any non-map overlay text.
    - Use visible text **only from the central map area** (the portion that contains place pins, roads, and landmarks).
    - Use visible text exactly as shown on the map (Bengali/English). No external inference.

    ────────────────────────────────────────────────────────────────
    Boundary Detection Clarification
    ────────────────────────────────────────────────────────────────
    When determining whether the map shows a specific pinned place or a region outline:

    • <isRedBounded> Yes <isRedBounded>  
    Use this if the map includes any **red dashed or solid border lines** enclosing a large area (e.g., upazila, union, thana, district).  
    Example: the screenshot shows an administrative area like “সুনামগঞ্জ সদর উপজেলা” with a red dashed outline around a broad region containing many towns and road codes.

    • <isRedBounded> No <isRedBounded>  
    Use this if the map shows a **single red location pin** marking a specific spot (mosque, school, shop) without a red dashed boundary line.

    Heuristic:
    - Red pins = small, teardrop icons with a white dot.
    - Red outlines = irregular polygons/dashed lines around administrative regions.
    - If both appear, prioritize the **outline** as the dominant map type (treat as a region).

    Fail-safe:
    If any extracted map label contains the term “উপজেলা”, “Thana”, “District”, “Union”, or “Subdistrict”, **and** the view includes multiple road codes or towns, mark <isRedBounded> Yes <isRedBounded> automatically.

    Before you output the boundary tag, briefly show **Boundary Reasoning** (2–4 bullet points, citing only visible visual cues and map-canvas labels—no sidebar text, no hidden chain-of-thought).

    Multi-Pin Auto-Reject Rule:
    If ≥2 red location pins appear on the map canvas (including cluster bubbles), the screenshot represents a search results view.
    Immediately output <isSame> No <isSame> without extraction or reasoning.

    ────────────────────────────────────────────────────────────────
    MANDATORY EXTRACTION GATE (applies to every screenshot)
    ────────────────────────────────────────────────────────────────
    1) **First, extract ALL readable map labels you can see** (places, roads, bridges, neighborhoods). 
    - Copy labels **as they appear** on the map when possible.
    - If uncertain about a letter/diacritic, write your **best literal copy** and add a bracketed note like `[uncertain]`. Do NOT invent new labels.

    2) **OCR Priority Rule (Landmark-only):**
    - The OCR-extracted text list represents the most direct reading of **place and landmark names** visible on the map, even if partially distorted.
    - When verifying **Incident Landmarks**, you must prioritize the OCR list over your own visual extraction.
    - For **road labels, highway codes, or route verification**, rely exclusively on your own extracted visual labels — not on OCR.
    - You may use Soft-Match Tolerance to interpret distorted OCR text, but do **not** assume or correct labels that have no semantic support from OCR evidence.
    - If a landmark appears in your extracted list but has **no remotely similar item in the OCR text**, you must:
        (i) double-check carefully whether OCR might have missed or distorted it,
        (ii) explicitly mention this uncertainty, and
        (iii) if still doubtful, treat the OCR as **ground truth** and mark that landmark as **not confirmed**.
    - In summary: **OCR governs landmark validation only; road detection stays visual.**

    3) **All subsequent reasoning MUST reference only these extracted labels** (plus the road equivalence rule below). 
    - If an item (e.g., an Incident Landmark) is **not found** among the extracted labels under the **Soft-Match Tolerance** rules below, treat it as **not present**.

    ────────────────────────────────────────────────────────────────
    Soft-Match Tolerance (to avoid over-strictness with OCR)
    ────────────────────────────────────────────────────────────────
    ### A. Landmarks (Standard Soft-Match)
    Consider two strings a match if **any** of the following holds:
    - Minor punctuation/spacing differences (hyphen vs en dash, extra spaces).
    - Common suffix/prefix variants (e.g., “Rd” vs “Road”, “Br.” vs “Bridge”, Bengali vs English transliteration of the **same proper name**).
    - Single-character OCR slips that don’t change the name materially (e.g., similar-looking Bengali glyphs or common Latin confusions like O/0, l/1).
    - Obvious plural/singular or case differences.
    **Do NOT** match across different places (e.g., different mosques/markets) if the core name differs, even if the road matches.

    ### B. Roads (Stricter Soft-Match)
    Two road strings are considered equivalent **only if one of the following holds**:

    1. **Exact bilingual match:**  
    One is the direct translation or transliteration of the other  
    (e.g., “Sylhet–Sunamganj Road” ↔ “সিলেট–সুনামগঞ্জ সড়ক”),  
    and they contain the same endpoint pair (in either order).

    2. **Route-table equivalence verified:**  
    A mapping (e.g., R280 ↔ Sylhet–Sunamganj Road) exists in the provided *Route Coverage Information*.

    3. **Both endpoints explicitly visible:**  
    The shorter name (e.g., “Sunamganj Road”) includes **both** endpoint tokens from the longer name (e.g., “Sunamganj” and “Sylhet”).  
    If only one endpoint overlaps, treat as **not equivalent**.

    ────────────────────────────────────────────────────────────────
    No Guessing Rule
    ────────────────────────────────────────────────────────────────
    If you are unsure whether a label is present after extraction, assume **not present**. 
    Never claim a label is visible unless it appears in your extracted list or the OCR list (for landmarks only, with Soft-Match Tolerance).

    ────────────────────────────────────────────────────────────────
    Global Instructions (apply to every screenshot)
    ────────────────────────────────────────────────────────────────
    Step 0 — Boundary & Pin Detection (do this before extraction)
    - Visually determine whether the map shows:
    (a) a red pin for a specific place, or
    (b) a red dashed/solid outline for a region.
    - Show **Boundary Reasoning** first (2–4 bullets citing only visible cues).  
    - Then output the boundary tag:
    - <isRedBounded> No <isRedBounded> for a pinned place (no red boundary).
    - <isRedBounded> Yes <isRedBounded> for a red-outlined region.

    Step 1 — Identify Map Type  
    (Already captured via Step 0 output.)

    Step 2 — Evidence-Based Location Verification  
    Work only from the **Extracted Map Labels**, the **OCR-Extracted Landmark Text**, and the article text.

    A) Extract article place mentions and classify them:
        - **Incident Landmarks (MANDATORY set):** only places explicitly tied to where the **crash happened** (e.g., “in front of …”, “near … where the accident occurred”, “at … on the highway”). Quote the **exact Bengali/English phrase** from the article for each item.  
        - **Non-incident Mentions:** places connected to other actions (e.g., where the victim refueled, departed from, hospital names, police stations, protest spots). Also quote the exact phrase.  
        - If both exist, **you must prioritize Incident Landmarks** for matching. If none are given, fall back to the most specific remaining place **and state that no incident landmark exists**.

    B) Road verification rule:
        - A visible **road label or code** must appear among the **Extracted Map Labels** (e.g., R280, N2, “Sylhet–Sunamganj Road”).

        **Road Code Priority (added):**
        - If a visible **road code** (e.g., N1, R140, Z1031, etc.) appears on the map, always **prioritize the code** over any road name.
          • If the article mentions a corresponding **name** (e.g., “ঢাকা–চট্টগ্রাম মহাসড়ক”) and the visible map shows its **code** (e.g., N1), treat them as equivalent immediately using the Route Coverage Information.  
          • You do **not** need to verify a local segment name (e.g., “City Bypass”, “Service Road”, “Old Highway”) once the code match is established.
        - **Fallback to Name:** If **no road code is visible**, use road names (Bangla/English) with the Roads (Stricter Soft-Match) rules above.
        - **Segment Equivalence (optional):** If the visible name includes “Bypass”, “Flyover”, or “Highway” and lies within a district the code passes through, you may also treat it as equivalent.

        - You may equate a **code ↔ name** **only if**:
        (i) that mapping exists in the provided *Route Coverage Information* (cite the code/name used), **or**  
        (ii) **both** the code **and** the name appear in your **Extracted Map Labels** list.  
        - **Do not use OCR text or sidebar text** for road name or code verification — this must be derived **only from the map canvas.**  
        - If the article mentions only a **name** and the map shows only a **code**, you **can** claim equivalence using the **Road Code Priority** and route table.  
        - If the article mentions only a **name** and the map shows only a **segment label** (e.g., “City Bypass”) with **no code**, you **cannot** claim equivalence unless (i) or (ii) holds, or the Segment Equivalence condition is satisfied.

    C) Required visual matches (both must be satisfied):
        1) **Incident Landmark Requirement (MANDATORY):**  
        At least one **Incident Landmark** extracted in (A) must **Soft-Match** an item in the **OCR Text list** or the **Extracted Map Labels**.  
        District/city/division names do **not** satisfy this if the article names a more specific incident place.  
        2) **Road Verification Requirement (MANDATORY):**  
        A qualifying road label/name per (B) must appear in the **Extracted Map Labels** and correspond to the article.

    D) MUST-FAIL conditions (answer <isSame> No <isSame> if any apply):
        - Road label/code is visible, but **no Incident Landmark** from (A) **Soft-Matches** any extracted or OCR landmark label.  
        - A Non-incident place Soft-Matches, but **no Incident Landmark** does.  
        - Incident Landmark Soft-Matches, but the qualifying road label/name per (B) is **not** in the extracted list.  
        - Only broad region names match while a more specific Incident Landmark exists in the article.  
        - The visible landmark clearly refers to a different locality than the incident site.

    ────────────────────────────────────────────────────────────────
    Per-Screenshot Output Format (repeat this block for each provided screenshot)
    Per-Screenshot Output Format
    ────────────────────────────────────────────────────────────────────
    You MUST respond ONLY with a valid JSON object. Do NOT include any text outside the JSON.
    The JSON must follow this schema exactly:

    {{
      "screenshots": [
        {{
          "filename": "screenshot_1.png",
          "boundary_reasoning": "2-4 bullets describing visible cues",
          "isRedBounded": "Yes or No",
          "extracted_map_labels": ["label1", "label2"],
          "incident_landmarks": "Incident landmarks quoted from article",
          "non_incident_mentions": "Non-incident mentions quoted",
          "map_labels_used": "Map labels used for matching",
          "road_equivalence_used": "Yes/No and basis",
          "requirement_check": "Incident Landmark = Pass/Fail; Road = Pass/Fail",
          "justification": "Brief 1-3 line justification",
          "isSame": "Yes or No",
          "landmark_match": "Matching landmark text if isSame=Yes, else empty"
        }}
      ]
    }}

    ────────────────────────────────────────────────────────────────────
    Example of Correct JSON Output
    ────────────────────────────────────────────────────────────────────
    {{
      "screenshots": [
        {{
          "filename": "NE_1.8km_lat25.0800_lon91.3927.png",
          "boundary_reasoning": "Single red teardrop pin. No red dashed or solid border lines. No admin terms visible.",
          "isRedBounded": "No",
          "extracted_map_labels": ["উত্তর পাড়া জামে মসজিদ"],
          "incident_landmarks": "বাহাদুরপুর গ্রামের পাশে",
          "non_incident_mentions": "সিলেটের বিশ্বনাথ উপজেলার লামাকাজী এলাকায়",
          "map_labels_used": "No matching labels found",
          "road_equivalence_used": "No. Basis: Not used",
          "requirement_check": "Incident Landmark = Fail; Road = Fail",
          "justification": "The map displays উত্তর পাড়া জামে মসজিদ but lacks labels for বাহাদুরপুর গ্রাম.",
          "isSame": "No",
          "landmark_match": ""
        }}
      ]
    }}


    ────────────────────────────────────────────────────────────────
    OCR-Extracted Text Labels (for landmarks only)
    ────────────────────────────────────────────────────────────────
    These are the landmark or place names actually detected by OCR.  
    They represent the most reliable reading of **visible landmarks** on the map, even if distorted or partially misspelled.  
    Use them **only** for verifying landmarks (not roads).  
    You must prioritize these OCR landmark labels over your own extracted ones when judging incident landmark visibility.  
    You may use Soft-Match tolerance (minor spelling or spacing differences), but do NOT add new labels that are not semantically supported by these items.  
    If any label from your extracted list is not even remotely represented in this OCR landmark set, treat that label as **unconfirmed** and prefer the OCR.

    ────────────────────────────────────────────────────────────────
    ────────────────────────────────────────────────────────────────
    Route Coverage Information
    ────────────────────────────────────────────────────────────────
    {road_data_fuzzy}

    ────────────────────────────────────────────────────────────────
    News Article
    ────────────────────────────────────────────────────────────────
    {news_string}
    """

        llm_agent.set_stage("vlm")
        model_response = get_gemini_response_with_screenshots_json(
            Gemini_API_Keys,
            prompt_2,
            image_paths,
            OCR_texts,
            json_schema=VLM_SCHEMA
        )
        return model_response
    # ------------------- Vagueness Check ---------------------
    def GetCoordinatesFromURL(url):
        if not url: return None, None
        match = re.search(r"@([-0-9.]+),([-0-9.]+)", url)
        return (float(match.group(1)), float(match.group(2))) if match else (None, None)
    def handle_slightly_vague_location(news_string, Gemini_API_Keys, response_string_1, GetLocationURL, GoogleMapsSearch, get_gemini_response_with_screenshots, ner_parsed=None):
        """
        Handles cases where either the road or landmark is missing (slightly vague).
        Attempts multiple search refinements until a satisfactory location is confirmed.
        Returns: [latitude, longitude, isVague]
        """
        import re
        isVague = True
        print("\n⚠️ Analysis Result: Slightly Vague Location (road or landmark is missing).")
        print("---------- Stage 2: Vague Location Inference ----------")

        search_suggestions = best_suggestions
        if not search_suggestions:
            print("No search strings generated from initial analysis. Cannot proceed with vague mapping.")
            return ['Not Available', 'Not Available', isVague]

        current_query = search_suggestions[0].strip()
        previous_search_strings = current_query + "\n"

        for i in range(5):  # Limit to 5 retries
            print(f"\nAttempt {i + 1}/5 with query: '{current_query}'")
            temp_ss_path = "temp_vague_ss.png"
            GoogleMapsSearch(current_query, temp_ss_path)
            vague_url = GetLocationURL(current_query)

            # Extract coordinates from the URL
            coord_match = re.search(r"@([-0-9.]+),([-0-9.]+)", vague_url or "")
            lat = float(coord_match.group(1)) if coord_match else None
            lon = float(coord_match.group(2)) if coord_match else None

            vague_prompt = f"""
            You are given:
1) A Bangladeshi accident news article (below).
2) A screenshot from Google Maps search results (image).

Your task:
    Judge whether this map screenshot shows a location that **reasonably corresponds** to the described accident location in the article.

────────────────────────────
MATCHING RULES
────────────────────────────
- A "reasonable correspondence" means the location name(s) and surrounding context plausibly align with the described accident site.
- UI EXCLUSION (CRITICAL): Reject the image (Confirmation: No) if it displays a sidebar list of multiple search results or suggestions on the left. The screenshot must show a single, selected location (usually indicated by one specific red pin and a single info card), not a generic search menu.
- Use map labels only as evidence. Ignore UI panels, photos, or sidebar text except to identify if a specific location is selected.

────────────────────────────
SEARCH STRING STRATEGY
────────────────────────────
When suggesting a new Google Maps search string in the <sug_str> section, follow this hierarchy **strictly**.
At each attempt, output **exactly one** search string **inside a single <sug_str> tag**.

**STEP 1 (First attempt):** Use the main **landmark name** + **exactly one administrative zone** (either a union OR an upazila).
- Example output:
  <justification>
  • Visible labels show “তেরোমাইল” not near explicit union markers.
  • Adjacent labels reference মহাদেবপুর corridor.
  </justification>
  <confirmation> No <confirmation>
  <sug_str> তেরোমাইল, মহাদেবপুর <sug_str>

**STEP 2 (Only if STEP 1 failed):** Use **only the union name** OR **only the upazila name** (pick one).
- Example output:
  <justification>
  • Map labels cluster around মহাদেবপুর township.
  • No specific landmark alignment visible.
  </justification>
  <confirmation> No <confirmation>
  <sug_str> মহাদেবপুর <sug_str>

**STEP 3 (Only if STEP 2 failed):** Suggest **one** new alternative search string that is **different from all previously failed ones**.
This can include a zilla name, a road name, or a nearby locality.
- Example output:
  <justification>
  • Regional labels reference নওগাঁ district contexts.
  • Road hints suggest broader zilla search.
  </justification>
  <confirmation> No <confirmation>
  <sug_str> নওগাঁ <sug_str>

SPECIAL RULE: INSTITUTIONAL LANDMARKS
If the described landmark is an institution, hospital, university, or organization (e.g., "বাংলাদেশ ধান গবেষণা ইনস্টিউট"), you must expand your search variants to include:

Its English translation (e.g., "Bangladesh Rice Research Institute").

Its common abbreviation/acronym (e.g., "BRRI").
Use these English variants either alone or paired with the administrative zone (upazila/zilla) as part of your STEP 3 or CONTINUATION attempts.

**CONTINUATION (Attempts beyond STEP 3):**
If the result still does not reasonably correspond, **keep retrying** for the remaining attempts by proposing **one best new search string** each time that:
- Is **not** in the list of **Previous Failed Search Strings**,
- Follows a plausible escalation: try zilla names, major roads/highways, well-known nearby localities/markets/intersections, disambiguating qualifiers (e.g., upazila/union appended), and common **Bangla↔English transliteration variants**,
- Avoids redundancy and trivial variants that only add/remove whitespace or punctuation,
- Maintains brevity and clarity (no more than one comma).

Examples of continuation-stage outputs:
- Example D:
  <justification>
  • Label shows নওহাটা corridor linked to মহাদেবপুর.
  • Screenshot lacks exact মোড় indicator.
  </justification>
  <confirmation> No <confirmation>
  <sug_str> নওহাটা-মহাদেবপুর সড়ক <sug_str>

- Example E:
  <justification>
  • Nearby locality “নওহাটা” appears on-map; pairing with upazila to narrow.
  </justification>
  <confirmation> No <confirmation>
  <sug_str> নওহাটা, মহাদেবপুর <sug_str>

- Example F:
  <justification>
  • Likely transliteration variant of তেরোমাইল found in user queries.
  </justification>
  <confirmation> No <confirmation>
  <sug_str> Teromail, Mohadevpur <sug_str>

⚠️ Strict constraints:
- **Exactly one** suggestion per <sug_str>. **Never** include multiple suggestions or semicolons.
- **Never** repeat any string listed in **Previous Failed Search Strings**.
- Keep the hierarchy order: **Landmark+Admin → Admin only → Broader context → Continuation best-candidates**.

────────────────────────────
OUTPUT FORMAT (must use this exact order)
────────────────────────────
1) A short justification block (2–4 concise bullets based only on map labels):
<justification>
• bullet 1
• bullet 2
(2–4 bullets total)
</justification>

2) Then the decision:
<confirmation> Yes/No <confirmation>

3) Then exactly one new search string:
<sug_str> the single new search string <sug_str>

No extra text before or after these tags.

────────────────────────────
EXAMPLES (for clarity)
────────────────────────────
Example A (first attempt, STEP 1):
<justification>
• “গুনাইহাটি” appears on map; admin label unclear.
• Nearby “বড়াইগ্রাম” corridor visible.
</justification>
<confirmation> No <confirmation>
<sug_str> গুনাইহাটি, বড়াইগ্রাম <sug_str>

Example B (second attempt, STEP 2):
<justification>
• Township labels emphasize বড়াইগ্রাম.
• No exact landmark alignment on canvas.
</justification>
<confirmation> No <confirmation>
<sug_str> বড়াইগ্রাম <sug_str>

Example C (third attempt, STEP 3):
<justification>
• Major highway label visible near prior focus area.
• Likely to refine approach to accident corridor.
</justification>
<confirmation> Yes <confirmation>
<sug_str> নাটোর-পাবনা মহাসড়ক, বড়াইগ্রাম <sug_str>

Example D (continuation, later attempt):
<justification>
• Nearby market name appears on-map.
• Could disambiguate local segment.
</justification>
<confirmation> No <confirmation>
<sug_str> বনপাড়া, বড়াইগ্রাম <sug_str>

Example E (Institutional Landmark attempt):
<justification>
• Article mentions "বাংলাদেশ ধান গবেষণা ইনস্টিউট" in গাজীপুর.
• Standard Bangla map labels yielded no clear match; shifting to English abbreviation.
</justification>
<confirmation> No <confirmation>
<sug_str> BRRI, Gazipur <sug_str>

────────────────────────────
Previous Failed Search Strings
(format each line exactly as: "Attempt K: <string>")
{previous_search_strings.strip()}
(Current attempt: {i + 1}/5)
────────────────────────────
News Article:
{news_string}
            """

            llm_agent.set_stage("vague")
            response_vague = get_gemini_response_with_screenshots(Gemini_API_Keys, vague_prompt, [temp_ss_path], [""])

            if re.search(r"<confirmation>\s*Yes\s*</?confirmation>", response_vague, re.IGNORECASE):
                print(f"✅ Gemini confirmed the vague location as satisfactory. Coordinates: {lat}, {lon}")
                llm_agent.set_success_stage("Stage_Fallback")
                return [lat, lon, isVague]

            new_suggestions = re.findall(r"<sug_str>(.*?)</?sug_str>", response_vague, re.DOTALL | re.IGNORECASE)
            if not new_suggestions or not new_suggestions[0].strip():
                print("⚠️ No new search strings provided by Gemini. Exiting vague handler.")
                llm_agent.set_success_stage("Stage_Fallback")
                return [lat, lon, isVague]

            current_query = new_suggestions[0].strip()
            previous_search_strings += "\n".join(new_suggestions) + "\n"
            print(f"🔁 Retrying with new suggestion: {current_query}")

        print("❌ Could not obtain satisfactory confirmation after multiple attempts.")
        return ['Not Available', 'Not Available', isVague]

    # --- Vagueness Assessment ---
    if ner_parsed:
        is_road_missing = ner_parsed.get("road_name", "Not Available").strip().lower() == "not available"
        is_landmark_missing = ner_parsed.get("landmark", "Not Available").strip().lower() == "not available"
    else:
        is_road_missing = "<road_name> Not Available <road_name>" in response_string_1
        is_landmark_missing = "<landmark> Not Available <landmark>" in response_string_1

    isVague = False

    # Case 1: Extremely Vague
    if is_road_missing and is_landmark_missing:
        print("\n❌ Analysis Result: Extremely Vague Location (both road and landmark are missing).")
        isVague = True
        new_lat = 'Not Available'
        new_lon = 'Not Available'
        return [new_lat, new_lon, isVague]
    # Case 2: Slightly Vague
    elif is_landmark_missing: # elif is_road_missing or is_landmark_missing:
        return handle_slightly_vague_location(
            news_string, 
            Gemini_API_Keys, 
            response_string_1, 
            GetLocationURL, 
            GoogleMapsSearch, 
            get_gemini_response_with_screenshots,
            ner_parsed
        )
    else:
        # --- Case 3: Not Vague ---
        print("\n✅ Analysis Result: Sufficient location data extracted.")
        import re
        import os
        import OCR_ss_test

        # --- Global variables ---
        redbounded = []
        filename_to_search = {}
        match_found = False  # Flag to stop processing once a match is found
        batch_size = 5       # Set your desired batch size (e.g., 3 or 5)

        # --- Helper function (Must be defined before it's used) ---
        def process_batch(batch_files, OCR_texts):
            """
            Processes a batch of screenshots using VLM JSON output.
            Includes early stopping once a match (isSame=Yes) is found.
            """
            nonlocal match_found
            new_lat, new_lon = 'Not Available', 'Not Available'

            print(f"\nProcessing batch: {batch_files}")
            vlm_result = ss_checking_agent(news_string, Gemini_API_Keys, batch_files, OCR_texts)

            # vlm_result is a dict from get_response_with_images_json()
            vlm_parsed = vlm_result.get("parsed") if isinstance(vlm_result, dict) else None
            model_response = vlm_result.get("text", "") if isinstance(vlm_result, dict) else (vlm_result or "")

            if vlm_parsed and "screenshots" in vlm_parsed:
                # ✅ JSON mode: parse structured output directly
                print("✅ VLM response parsed via JSON mode.")
                for ss in vlm_parsed["screenshots"]:
                    fname = ss.get("filename", "")
                    is_same = ss.get("isSame", "No")
                    is_red = ss.get("isRedBounded", "No")
                    landmark_match = ss.get("landmark_match", "")

                    print(f"  🖼️ {fname}: isSame={is_same}, isRedBounded={is_red}")

                    if is_same == "Yes":
                        corresponding_search = filename_to_search.get(fname, "Unknown")

                        if is_red == "Yes":
                            redbounded.append(corresponding_search)
                            print("🔴 Red Bounded Area:", corresponding_search)
                            continue

                        # Confirmed pinpoint
                        match_found = True
                        Location_URL_1 = GetLocationURL(corresponding_search)
                        print("Location URL:", Location_URL_1)

                        if Location_URL_1:
                            start_url = Location_URL_1.strip()
                            coord_pattern = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+),(\d+)z")
                            re_match = coord_pattern.search(start_url)

                            if re_match:
                                new_lat = float(re_match.group(1))
                                new_lon = float(re_match.group(2))
                                print(f"✅ Coordinates: {new_lat}, {new_lon}")
                            else:
                                print("⚠️ Could not extract coordinates from URL.")
                                new_lat, new_lon = 'Not Available', 'Not Available'
                        else:
                            print(f"⚠️ GetLocationURL returned None for '{corresponding_search}'.")
                            new_lat, new_lon = 'Not Available', 'Not Available'

                        break  # Early stop
            else:
                # ⚠️ Fallback: regex parsing (same as original)
                print("⚠️ JSON parsing failed for VLM response. Falling back to XML/Markdown parsing.")
                pattern = r"<([^>]+\.png)>(.*?)</\1>"
                matches_xml = re.findall(pattern, model_response, flags=re.DOTALL)
                results = {filename: content.strip() for filename, content in matches_xml}

                if not results:
                    print("⚠️ XML wrapper tags not found. Falling back to Markdown header parsing.")
                    for img in batch_files:
                        fname = os.path.basename(img)
                        header_pat = rf"####\s+{re.escape(fname)}\s*\n(.*?)(?=####\s+\S|$)"
                        all_matches = re.findall(header_pat, model_response, re.DOTALL)
                        if all_matches:
                            results[fname] = all_matches[-1].strip()

                for captured_filename, content in results.items():
                    if re.search(r"<isSame>\s*Yes\s*</?isSame>", content, re.IGNORECASE):
                        corresponding_search = filename_to_search.get(captured_filename, "Unknown")

                        if re.search(r"<isRedBounded>\s*Yes\s*</?isRedBounded>", content, re.IGNORECASE):
                            redbounded.append(corresponding_search)
                            print("🔴 Red Bounded Area:", corresponding_search)
                            continue

                        match_found = True
                        Location_URL_1 = GetLocationURL(corresponding_search)
                        print("Location URL:", Location_URL_1)

                        if Location_URL_1:
                            start_url = Location_URL_1.strip()
                            coord_pattern = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+),(\d+)z")
                            re_match = coord_pattern.search(start_url)

                            if re_match:
                                new_lat = float(re_match.group(1))
                                new_lon = float(re_match.group(2))
                                print(f"✅ Coordinates: {new_lat}, {new_lon}")
                            else:
                                print("⚠️ Could not extract coordinates from URL.")
                                new_lat, new_lon = 'Not Available', 'Not Available'
                        else:
                            print(f"⚠️ GetLocationURL returned None for '{corresponding_search}'.")
                            new_lat, new_lon = 'Not Available', 'Not Available'

                        break

            if not match_found:
                print("⚠️ No confirmed matches found in this batch.")

            if match_found:
                llm_agent.set_success_stage("Stage_2_Visual")
            return [new_lat, new_lon, match_found]

        # --- Main processing loop ---

        # Temporary lists to hold screenshots for the current batch
        temp_batch_files = []
        temp_OCR_texts = []

        print(f"Starting screenshot generation and processing with batch size {batch_size}...")

        # 1️⃣ Loop to generate screenshots AND process them in batches
        for i, match in enumerate(matches, start=1):
            filename = f'screenshots_first/screenshot_{i}.png'
            GoogleMapsSearch(match.strip(), filename)
            
            found, OCR_text = OCR_ss_test.chunkwise_OCR_agent(
                places=places,
                image_path=filename,
                crop_height=400,
                crop_width=600,
                overlap=50,
                similarity_threshold=75
            )
            
            if found:
                print(f"Screenshot {filename} passed OCR. Adding to batch.")
                # Add the qualified screenshot to the temporary batch
                temp_batch_files.append(filename)
                temp_OCR_texts.append(OCR_text)
                
                # Store the mapping from basename to the original search query
                basename = os.path.basename(filename)
                filename_to_search[basename] = match.strip()

                # 2️⃣ Check if the batch is full and process it
                if len(temp_batch_files) == batch_size:
                    process_batch_results = process_batch(temp_batch_files, temp_OCR_texts)
                    print(process_batch_results)
                    if match_found:
                        llm_agent.set_success_stage("Stage_2_Visual")
                        return [process_batch_results[0], process_batch_results[1], False]    
                    # Reset the temporary batch lists for the next set
                    temp_batch_files = []
                    temp_OCR_texts = []

        # 3️⃣ Process any remaining screenshots
        # This code runs only if the loop finished *without* finding a match
        # AND if there are any screenshots left in the temporary batch.
        if not match_found and len(temp_batch_files) > 0:
            print(f"\nProcessing remaining {len(temp_batch_files)} screenshots...")
            process_batch_results = process_batch(temp_batch_files, temp_OCR_texts)

        if match_found:
            print("\n✅ Processing complete: Match found.")
            llm_agent.set_success_stage("Stage_2_Visual")
            return [process_batch_results[0], process_batch_results[1], False]
        elif redbounded:
            print(f"\nℹ️ Processing complete: No exact match found, but found {len(redbounded)} red-bounded areas.")
        else:
            print("\n❌ Processing complete: No matches found.")


        # --------------------2nd degree reasoning--------------------
        import re
        import time
        import os
        import math
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        # from webdriver_manager.chrome import ChromeDriverManager

        # --- Utility Functions ---

        def move_coordinates(lat, lon, km_lat, km_lon, conv_factor=0.01):
            """
            Move given km north/south (km_lat) and east/west (km_lon).
            """
            return lat + km_lat * conv_factor, lon + km_lon * conv_factor

        def haversine(lat1, lon1, lat2, lon2):
            """
            Calculate great-circle distance (in km) between two coordinates.
            """
            R = 6371.0  # Earth radius in km
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (math.sin(dlat/2)**2 +
                math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                math.sin(dlon/2)**2)
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        def wait_for_captcha(driver):
            """
            Detect captcha on Google Maps page.
            If detected, wait for user to manually solve it.
            """
            try:
                # Captcha is usually inside <iframe> or contains "captcha" in URL
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'captcha')]"))
                )
                print("⚠️ Captcha detected. Please solve it manually in the browser...")
                # Wait until captcha iframe disappears
                WebDriverWait(driver, 999999).until_not(
                    EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'captcha')]"))
                )
                print("✅ Captcha solved. Continuing...")
            except:
                # No captcha found
                pass
        def get_direction(i, j):
            if i == 0 and j == 0:
                return "C"  # Center
            direction = ""
            if i > 0:
                direction += "N"
            elif i < 0:
                direction += "S"
            if j > 0:
                direction += "E"
            elif j < 0:
                direction += "W"
            return direction

        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time


        def check_place_exists(place_name: str) -> bool:
            options = webdriver.ChromeOptions()
            if SELENIUM_HEADLESS:
                options.add_argument("--headless=new")
            driver = webdriver.Chrome(options=options)

            # 🔹 Force exact screen metrics (1920x1080)
            driver.set_window_size(1920, 1080)
            driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": 1920,
                "height": 1080,
                "deviceScaleFactor": 1,
                "mobile": False
            })


            try:
                # Force English version
                with _SeleniumTimer():
                    driver.get("https://www.google.com/maps")
                wait = WebDriverWait(driver, 10)

                # Type into the search box (no enter)
                search_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='q']")))
                search_box.clear()
                search_box.send_keys(place_name)

                # Wait for the first suggestion
                first_suggestion = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//div[@data-suggestion-index='0']"))
                )

                # Extract text of the first suggestion
                suggestion_text = first_suggestion.text.strip()

                # Debug (optional)
                # print("First suggestion:", suggestion_text)

                # Decide based on the first suggestion
                if "Add a missing place to Google Maps" in suggestion_text:
                    return False
                else:
                    return True

            finally:
                driver.quit()

        # Assume all helper functions (GoogleMapsSearch, OCR, get_gemini_response_with_screenshots, etc.)
        # and imports (re, os, time, math, webdriver, etc.) are defined elsewhere.

        # match_found = False
        if not match_found:
            print("-------------- Pinpointing Pivot Location -----------------")
            text = response_string_1
            
            if ner_parsed:
                union_matches = [ner_parsed.get("union", "Not Available")]
                thana_matches = [ner_parsed.get("thana", "Not Available")]
                upazilla_matches = [ner_parsed.get("upazilla", "Not Available")]
                district_matches = [ner_parsed.get("district", "Not Available")]
                if not union_matches[0]: union_matches = []
                if not thana_matches[0]: thana_matches = []
                if not upazilla_matches[0]: upazilla_matches = []
                if not district_matches[0]: district_matches = []
            else:
                union_matches = re.findall(r"<union>(.*?)<union>", text)
                thana_matches = re.findall(r"<thana>(.*?)<thana>", text)
                upazilla_matches = re.findall(r"<upazilla>(.*?)<upazilla>", text)
                district_matches = re.findall(r"<district>(.*?)<district>", text)

            # --- MODIFIED LOGIC START ---
            # Priority: 1. Union, 2. Thana, 3. Upazilla
            pivot_search_term = None  # Initialize
            
            district_name = ""
            if district_matches and 'Not Available' not in district_matches[0]:
                district_name = district_matches[0].strip()

            if union_matches and 'Not Available' not in union_matches[0]:
                pivot_search_term = union_matches[0].strip() + " ইউনিয়ন"
                print(f"Extracted Union, using search term: {pivot_search_term}")
            elif thana_matches and 'Not Available' not in thana_matches[0]:
                thana_text = thana_matches[0].strip()
                if thana_text in ["সদর", "সদর থানা", "সদর উপজেলা"] and district_name:
                    pivot_search_term = f"{district_name} {thana_text}"
                else:
                    pivot_search_term = thana_text
                print(f"No Union found. Extracted Thana: {pivot_search_term}")
            elif upazilla_matches and 'Not Available' not in upazilla_matches[0]:
                upz_text = upazilla_matches[0].strip()
                if upz_text in ["সদর", "সদর থানা", "সদর উপজেলা"] and district_name:
                    pivot_search_term = f"{district_name} {upz_text}"
                else:
                    pivot_search_term = upz_text
                print(f"No Union or Thana found. Extracted Upazilla: {pivot_search_term}")
            else:
                print("❌ Error: Could not extract Union, Thana, or Upazilla from the initial analysis.")
            # --- MODIFIED LOGIC END ---

            # Proceed only if a pivot search term was successfully determined
            if pivot_search_term:
                Location_URL = None
                GoogleMapsSearch(pivot_search_term, 'screenshot.png')

                prompt_3 = """
You are analyzing a Google Maps screenshot.
Your task is to determine whether the view shows:

Your task is to determine whether the view shows:

A specific pinned place, or

A general red-bounded area (e.g., district, upazila, division), or

Multiple scattered red pins (e.g., generic search results or missing place).

────────────────────────────────────────────
INSTRUCTIONS
────────────────────────────────────────────

If it shows a specific pinned place, output only:
<isRedBounded> No <isRedBounded>

If it shows multiple scattered red pins (a search results view) or an error/missing place, output:
<isRedBounded> Invalid <isRedBounded>

If it shows a red-bounded area, output:
<isRedBounded> Yes <isRedBounded>
<PlaceName> [Provide the name of a specific landmark near the center of this bounded region in Bangla] <PlaceName>

Rules for choosing <PlaceName>:

The landmark must be one of the following types:
• Railway Station
• Thana (Police Station)
• Government High School
• Government Hospital
• Administrative Offices (Upazila Office, Union Parishad Office, etc.)

It must lie inside the bounded area, preferably near its center.

The name must be directly searchable on Google Maps as a pinned place.

Do NOT use the name of the bounded area itself (e.g., "Sunamganj", "Dhaka District").

Generate at least 10 place names, each in its own <PlaceName> tag.

────────────────────────────────────────────
OUTPUT FORMAT
────────────────────────────────────────────
If specific pinned place:
<isRedBounded> No <isRedBounded>

If red-bounded area:
<isRedBounded> Yes <isRedBounded>
<PlaceName> ... <PlaceName>
<PlaceName> ... <PlaceName>
... (at least 10 total)

────────────────────────────────────────────
EXAMPLE 1: PINNED PLACE
────────────────────────────────────────────
Screenshot View: Showing “Rajshahi University” with a single location pin.
Expected Output:
<isRedBounded> No <isRedBounded>

────────────────────────────────────────────
EXAMPLE 2: MULTIPLE SCATTERED PINS
────────────────────────────────────────────
Screenshot View: Showing ≥2 red location pins on the map (like a search results view) or an error prompt indicating a missing place.
Expected Output:
<isRedBounded> Invalid <isRedBounded>

────────────────────────────────────────────
EXAMPLE 3: RED-BOUNDED AREA (Bogra District)
────────────────────────────────────────────
Screenshot View: The red boundary clearly outlines Bogra District.
Expected Output:
<isRedBounded> Yes <isRedBounded>
<PlaceName> বগুড়া রেলওয়ে স্টেশন <PlaceName>
<PlaceName> বগুড়া সদর থানা <PlaceName>
<PlaceName> বগুড়া সরকারি আজিজুল হক কলেজ <PlaceName>
<PlaceName> বগুড়া জেলা হাসপাতাল <PlaceName>
<PlaceName> বগুড়া সরকারি বালিকা উচ্চ বিদ্যালয় <PlaceName>
<PlaceName> জেলা প্রশাসকের কার্যালয়, বগুড়া <PlaceName>
<PlaceName> বগুড়া পৌরসভা অফিস <PlaceName>
<PlaceName> সদর উপজেলা পরিষদ, বগুড়া <PlaceName>
<PlaceName> বগুড়া সরকারি মহিলা কলেজ <PlaceName>
<PlaceName> বগুড়া রেলওয়ে পুলিশ স্টেশন <PlaceName>

────────────────────────────────────────────
EXAMPLE 3: RED-BOUNDED AREA (Jessore Upazila)
────────────────────────────────────────────
Screenshot View: Red boundary enclosing Jessore Sadar Upazila.
Expected Output:
<isRedBounded> Yes <isRedBounded>
<PlaceName> যশোর রেলওয়ে স্টেশন <PlaceName>
<PlaceName> যশোর সদর থানা <PlaceName>
<PlaceName> যশোর সরকারি উচ্চ বিদ্যালয় <PlaceName>
<PlaceName> যশোর ২৫০ শয্যা জেনারেল হাসপাতাল <PlaceName>
<PlaceName> যশোর সরকারি মহিলা কলেজ <PlaceName>
<PlaceName> জেলা প্রশাসকের কার্যালয়, যশোর <PlaceName>
<PlaceName> সদর উপজেলা পরিষদ, যশোর <PlaceName>
<PlaceName> যশোর পলিটেকনিক ইনস্টিটিউট <PlaceName>
<PlaceName> যশোর পৌরসভা ভবন <PlaceName>
<PlaceName> যশোর রেলওয়ে পুলিশ স্টেশন <PlaceName>
                """

                temp_ss_filename = 'screenshot.png'
                temp_ss_OCR_text = OCR_ss_test.chunkwise_OCR_agent(
                    places=places, image_path=temp_ss_filename, crop_height=400,
                    crop_width=600, overlap=50, similarity_threshold=75
                )[1]
                llm_agent.set_stage("grid")
                Query_on_Location = get_gemini_response_with_screenshots(Gemini_API_Keys, prompt_3, [temp_ss_filename], [temp_ss_OCR_text])

                if re.search(r"<isRedBounded>\s*Yes\s*</?isRedBounded>", Query_on_Location, re.IGNORECASE):
                    suggested_landmarks = re.findall(r"<PlaceName>(.*?)</?PlaceName>", Query_on_Location, re.DOTALL | re.IGNORECASE)
                    print(f"Suggested landmarks: {suggested_landmarks}")
                    for landmark in suggested_landmarks:
                        landmark = landmark.strip()
                        print(f"Trying landmark: {landmark}")
                        GoogleMapsSearch(landmark, 'screenshot.png')
                        temp_ss_filename = 'screenshot.png'
                        temp_ss_OCR_text = OCR_ss_test.chunkwise_OCR_agent(
                            places=places, image_path=temp_ss_filename, crop_height=400,
                            crop_width=600, overlap=50, similarity_threshold=75
                        )[1]
                        llm_agent.set_stage("grid")
                        check_query = get_gemini_response_with_screenshots(Gemini_API_Keys, prompt_3, [temp_ss_filename], [temp_ss_OCR_text])
                        if re.search(r"<isRedBounded>\s*No\s*</?isRedBounded>", check_query, re.IGNORECASE):
                            print(f"✅ Valid pinned place found: {landmark}")
                            Location_URL = GetLocationURL(landmark)
                            break
                        elif re.search(r"<isRedBounded>\s*Invalid\s*</?isRedBounded>", check_query, re.IGNORECASE):
                            print(f"❌ Place '{landmark}' gives scattered results.")
                else:
                    if re.search(r"<isRedBounded>\s*Invalid\s*</?isRedBounded>", Query_on_Location, re.IGNORECASE):
                        print("❌ LLM identified scene as scattered/invalid search.")
                        Location_URL = None
                    else:
                        print(f"✅ Initial search '{pivot_search_term}' is a valid pinned place.")
                        Location_URL = GetLocationURL(pivot_search_term)

                if not Location_URL:
                    print("❌ Error: Could not establish a valid pivot location URL. Exiting.")
                else:
                    print(f"Final pivot location URL: {Location_URL}")
                    start_url = Location_URL.strip()
                    coord_pattern = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+),(\d+)z")
                    match = coord_pattern.search(start_url)
                    if not match:
                        print("❌ Error: Could not extract coordinates from the pivot URL.")
                    else:
                        start_lat, start_lon = float(match.group(1)), float(match.group(2))
                        zoom_level = 17 # previously was 17
                        print(f"Pivot Coordinates: {start_lat}, {start_lon}, zoom={zoom_level}z")

                        RADIUS_KM = 6 # previously was 6
                        SHOT_WIDTH_KM = 1.2
                        SHOT_HEIGHT_KM = 0.65
                        STEP_LON_KM = SHOT_WIDTH_KM * 0.9
                        STEP_LAT_KM = SHOT_HEIGHT_KM * 0.9
                        CONVERSION_FACTOR = 0.01
                        lat_steps = int(math.ceil(RADIUS_KM / STEP_LAT_KM))
                        lon_steps = int(math.ceil(RADIUS_KM / STEP_LON_KM))
                        total_shots = (2 * lat_steps + 1) * (2 * lon_steps + 1)

                        print(f"Capturing area within {RADIUS_KM} km radius (~{total_shots} screenshots expected)")
                        os.makedirs("screenshots", exist_ok=True)
                        options = webdriver.ChromeOptions()
                        if SELENIUM_HEADLESS:
                            options.add_argument("--headless=new")
                        driver = webdriver.Chrome(options=options)

                        # 🔹 Force exact screen metrics (1920x1080)
                        driver.set_window_size(1920, 1080)
                        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                            "width": 1920,
                            "height": 1080, # 857 in calibration
                            "deviceScaleFactor": 1,
                            "mobile": False
                        })

                        ocr_passed_batch = []

                        # --- FIXED LOGIC IS IN THE TRY/FINALLY BLOCK BELOW ---
                        final_lat = 'Not Available'
                        final_lon = 'Not Available'
                        try:
                            for i in range(-lat_steps, lat_steps + 1):
                                for j in range(-lon_steps, lon_steps + 1):
                                    offset_lat_km = i * STEP_LAT_KM
                                    offset_lon_km = j * STEP_LON_KM
                                    new_lat, new_lon = move_coordinates(start_lat, start_lon, offset_lat_km, offset_lon_km, CONVERSION_FACTOR)

                                    if haversine(start_lat, start_lon, new_lat, new_lon) <= RADIUS_KM:
                                        direction = get_direction(i, j)
                                        dist = haversine(start_lat, start_lon, new_lat, new_lon)
                                        filename = f"screenshots/{direction}_{dist:.1f}km_lat{new_lat:.4f}_lon{new_lon:.4f}.png"

                                        new_url = f"https://www.google.com/maps/@{new_lat:.4f},{new_lon:.4f},{zoom_level}z"
                                        print(f"📸 Capturing: {filename}")
                                        with _SeleniumTimer():
                                            driver.get(new_url)
                                        wait_for_captcha(driver)
                                        time.sleep(2)
                                        with _SeleniumTimer():
                                            driver.save_screenshot(filename)

                                        found, OCR_text = OCR_ss_test.chunkwise_OCR_agent(
                                            places=places, image_path=filename, crop_height=400,
                                            crop_width=600, overlap=50, similarity_threshold=75
                                        )
                                        print(f"OCR test result: {found}")

                                        if found:
                                            ocr_passed_batch.append({'filename': filename, 'lat': new_lat, 'lon': new_lon, 'OCR_text': OCR_text})

                                        if len(ocr_passed_batch) == 5:
                                            print("\n🧠 Sending batch of 5 screenshots to Gemini...\n")
                                            batch_files = [item['filename'] for item in ocr_passed_batch]
                                            batch_ocr_texts = [item['OCR_text'] for item in ocr_passed_batch]
                                            batch_file_info = {os.path.basename(item['filename']): item for item in ocr_passed_batch}

                                            vlm_result = ss_checking_agent(news_string, Gemini_API_Keys, batch_files, batch_ocr_texts)

                                            # Extract parsed JSON and raw text from dict response
                                            vlm_parsed = vlm_result.get("parsed") if isinstance(vlm_result, dict) else None
                                            model_response = vlm_result.get("text", "") if isinstance(vlm_result, dict) else (vlm_result or "")

                                            print("-------------------- Debugging Batch File Info --------------------")
                                            print("batch file info")
                                            print(batch_file_info)
                                            print("-------------------- Debugging Batch File Info --------------------")

                                            if vlm_parsed and "screenshots" in vlm_parsed:
                                                # ✅ JSON mode: parse structured output directly
                                                for ss in vlm_parsed["screenshots"]:
                                                    fname = ss.get("filename", "")
                                                    is_same = ss.get("isSame", "No")
                                                    is_red = ss.get("isRedBounded", "No")
                                                    print(f"  🖼️ {fname}: isSame={is_same}, isRedBounded={is_red}")

                                                    if is_same == "Yes" and is_red != "Yes" and fname in batch_file_info:
                                                        match_info = batch_file_info[fname]
                                                        final_lat, final_lon = match_info['lat'], match_info['lon']

                                                        print("="*50)
                                                        print(f"✅✅✅ MATCH FOUND in {match_info['filename']}! ✅✅✅")
                                                        print(f"Final Accident Location Coordinates: Latitude={final_lat}, Longitude={final_lon}")
                                                        print("="*50)

                                                        match_found = True
                                                        break
                                            else:
                                                # ⚠️ Fallback: regex parsing on raw text
                                                pattern = r"<([^>]+.png)>(.*?)</\1>"
                                                results = re.findall(pattern, model_response, re.DOTALL)
                                                for captured_filename, content in results:
                                                    if captured_filename in batch_file_info and re.search(r"<isRedBounded>\s*No\s*</?isRedBounded>", content, re.IGNORECASE) and re.search(r"<isSame>\s*Yes\s*</?isSame>", content, re.IGNORECASE):
                                                        match_info = batch_file_info[captured_filename]
                                                        final_lat, final_lon = match_info['lat'], match_info['lon']

                                                        print("="*50)
                                                        print(f"✅✅✅ MATCH FOUND in {match_info['filename']}! ✅✅✅")
                                                        print(f"Final Accident Location Coordinates: Latitude={final_lat}, Longitude={final_lon}")
                                                        print("="*50)

                                                        match_found = True
                                                        break  # Break from the 'results' loop 
                                            

                                            ocr_passed_batch = []  # Clear the batch after processing

                                    # **FIX**: Check for the flag after every step of the inner loop.
                                    if match_found:
                                        break  # This will break the inner 'j' (longitude) loop.

                                # **FIX**: Check for the flag after the inner loop finishes or breaks.
                                if match_found:
                                    break  # This will break the outer 'i' (latitude) loop.
                        finally:
                            # The finally block correctly handles any remaining items in the batch
                            if not match_found and ocr_passed_batch:
                                print(f"\n🧠 Sending final batch of {len(ocr_passed_batch)} screenshots to Gemini...\n")
                                batch_files = [item['filename'] for item in ocr_passed_batch]
                                batch_ocr_texts = [item['OCR_text'] for item in ocr_passed_batch]
                                batch_file_info = {os.path.basename(item['filename']): item for item in ocr_passed_batch}

                                vlm_result = ss_checking_agent(news_string, Gemini_API_Keys, batch_files, batch_ocr_texts)

                                # Extract parsed JSON and raw text from dict response
                                vlm_parsed = vlm_result.get("parsed") if isinstance(vlm_result, dict) else None
                                model_response = vlm_result.get("text", "") if isinstance(vlm_result, dict) else (vlm_result or "")

                                if vlm_parsed and "screenshots" in vlm_parsed:
                                    for ss in vlm_parsed["screenshots"]:
                                        fname = ss.get("filename", "")
                                        is_same = ss.get("isSame", "No")
                                        is_red = ss.get("isRedBounded", "No")
                                        print(f"  🖼️ {fname}: isSame={is_same}, isRedBounded={is_red}")

                                        if is_same == "Yes" and is_red != "Yes" and fname in batch_file_info:
                                            match_info = batch_file_info[fname]
                                            final_lat, final_lon = match_info['lat'], match_info['lon']

                                            print("="*50)
                                            print(f"✅✅✅ MATCH FOUND in {match_info['filename']}! ✅✅✅")
                                            print(f"Final Accident Location Coordinates: Latitude={final_lat}, Longitude={final_lon}")
                                            print("="*50)

                                            match_found = True
                                            break
                                else:
                                    pattern = r"<([^>]+.png)>(.*?)</\1>"
                                    results = re.findall(pattern, model_response, re.DOTALL)
                                    for captured_filename, content in results:
                                        if captured_filename in batch_file_info and re.search(r"<isRedBounded>\s*No\s*</?isRedBounded>", content, re.IGNORECASE) and re.search(r"<isSame>\s*Yes\s*</?isSame>", content, re.IGNORECASE):
                                            match_info = batch_file_info[captured_filename]
                                            final_lat, final_lon = match_info['lat'], match_info['lon']

                                            print("="*50)
                                            print(f"✅✅✅ MATCH FOUND in {match_info['filename']}! ✅✅✅")
                                            print(f"Final Accident Location Coordinates: Latitude={final_lat}, Longitude={final_lon}")
                                            print("="*50)

                                            match_found = True
                                            break
                            driver.quit()
                            if not match_found:
                                print("\n❌ No definitive match found after scanning the entire area.")
                                print("Attempting to apply slightly vague location extraction strategy...")
                                try:
                                    lat_lon_vague = handle_slightly_vague_location(
                                        news_string, 
                                        Gemini_API_Keys, 
                                        response_string_1, 
                                        GetLocationURL, 
                                        GoogleMapsSearch, 
                                        get_gemini_response_with_screenshots,
                                        ner_parsed
                                    )
                                except Exception as e:
                                    print(f"❌ Vague handler failed: {e}")
                                    lat_lon_vague = ['Could not locate', 'Could not locate', False]

                                print("✅ Finished process.")
                                return lat_lon_vague
                            llm_agent.set_success_stage("Stage_3_Grid")
                            return [final_lat, final_lon, isVague]
    
