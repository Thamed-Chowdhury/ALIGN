# ALIGN: A Vision–Language Framework for High-Accuracy Accident Location Inference through Geo-Spatial Neural Reasoning

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/1092781559.svg)](https://doi.org/10.5281/zenodo.18903029)

**Authors:**  
MD Thamed Bin Zaman Chowdhury — Bangladesh University of Engineering and Technology (BUET)  
Dr. Moazzem Hossain — BUET  

---

## 🔍 Overview

ALIGN (Accident Location Inference through Geo-Spatial Neural Reasoning) is a **vision–language AI pipeline** that automatically pinpoints the coordinates of traffic accident locations described in Bangla-language news articles.  
It combines:
- **Multimodal LLMs (VLMs)** for multimodal spatial reasoning  
- **Selenium** for automated Google Maps exploration  
- **EasyOCR** for bilingual Bangla + English map text recognition  
- **Fuzzy matching + reasoning logic** for verifying map and article consistency  

---

## 🧩 System Architecture

The figure below illustrates the end-to-end **ALIGN** pipeline integrating textual reasoning, map-based spatial verification, OCR processing, and vision–language inference.

<img width="975" height="1281" alt="image" src="https://github.com/user-attachments/assets/985b5673-8ad3-45a8-bcd3-0f3193ee4abb" />

*Figure: ALIGN multi-stage reasoning pipeline combining text extraction, OCR validation, grid-based spatial search, and Gemini VLM-based verification.*

---

## ⚠️ Critical Performance Warning

🚨 **WARNING:** Running this pipeline on a **CPU-only setup will be extremely slow.**  
In benchmark testing, an **NVIDIA RTX 3060 (6 GB VRAM)** laptop GPU was used to handle the **EasyOCR** stage.  
Without GPU support, OCR will take several minutes **per image**, making the end-to-end pipeline impractically slow.

🧩 **Recommended Setup:**
- Use **Python 3.10.18** (PyTorch is most stable on this version as of 2025).  
- Use a **GPU-enabled environment** with CUDA properly configured (Tested on CUDA 12.6).  
- Follow PyTorch's official installation instructions for your CUDA version.

---

## 🚀 Setup & Installation

### 1. Requirements Installation
To replicate the environment, run the following:
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. ⚠️ VERY IMPORTANT: PyTorch & CUDA 
If you plan to use **EasyOCR** (which is enabled by default in the `Text2GeolocationV7.py` pipeline), you must install PyTorch based on your specific operating system and hardware. **PyTorch is NOT included in `requirements.txt` to avoid cross-platform installation issues.**

If PyTorch runs purely on CPU, OCR scanning of map screenshots will be *impractically slow* (taking several minutes per image), ultimately causing API timeouts and failed geolocations. A GPU (CUDA-enabled or Mac Silicon) is strongly recommended.

**For Windows/Linux with NVIDIA GPUs (CUDA 12.4/12.6):**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

**For CPU-only (Not Recommended) or Mac:**
```bash
pip install torch torchvision torchaudio
```

*(Find the exact installation command for your system at [PyTorch's website](https://pytorch.org/get-started/locally/).)*

### 3. API Keys Setup
This pipeline can dynamically access LLMs from Together AI, Google Gemini, OpenAI, and Qwen, depending on your configuration. 

You MUST input your API keys directly into the top configuration sections of the benchmark scripts (`run_benchmark.py` and `run_single_benchmark.py`).

Open either script and search for:
```python
# ── API Keys ──────────
GEMINI_API_KEYS = [
  "AIzaSy....", 
  "AIzaSy...."
]

OPENAI_API_KEYS = [
    "sk-proj-...."
]

QWEN_API_KEYS = [
    "sk-...."
]

TOGETHER_API_KEYS = [
    "2c05...."
]
```
Add or replace the placeholder strings with your active API keys. The script dynamically rotates through the list of Gemini API keys to circumvent rate-limiting.

---

## 🛠️ Usage Configurations

The repository houses two main operational scripts to run tests against the LLM Agent pipeline:

### 1. Batch Benchmarking (`run_benchmark.py`)
This script executes the pipeline on consecutive rows from `dataset.xlsx`. 
To run it:
```bash
.venv\Scripts\python.exe run_benchmark.py
```
**Options to adjust inside the script:**
- `INPUT_FILE`: The dataset file (default: `dataset.xlsx`). It must contain the columns `News Title`, `Description`, and `Actual Co-ordinates`.
- `START_ROW`: The 0-indexed integer of which row in the sheet to start testing from.
- `NUM_ROWS`: How many consecutive articles to iterate through.

### 2. Single Article Testing (`run_single_benchmark.py`)
This script tests the pipeline on **one** hardcoded snippet of news text, outputting direct logs and timing info. 
To run it:
```bash
.venv\Scripts\python.exe run_single_benchmark.py --text "Your Bengali news text here..."
```

---

## ⚙️ Understanding the Pipeline Modes

Depending on the nature of the test, the behavior of the geocoder can be configured by toggling boolean variables inside the benchmarking scripts:

```python
# Inside run_benchmark.py or run_single_benchmark.py:
USE_OCR = True        # Uses Text2GeolocationV7.py
USE_ROADS = True      # Loads bd_roads.json
USE_LLAMA_JSON = True # Special JSON mode for Together AI
```

### Script Variations:
By toggling those booleans, the benchmark runners dynamically load one of four core variations of the Geolocation Agent:

1. **`Text2GeolocationV7.py` (`USE_OCR=True, USE_ROADS=True`)**
    *   **The Default Pipeline.** 
    *   Uses EasyOCR to scan the map screenshots to validate whether the extracted pin actually exists on the map.
    *   Injects an exhaustive list of Bangladesh road names from `bd_roads.json` into the LLM context to aid spatial orientation.

2. **`Text2GeolocationV7_OCR_Removed.py` (`USE_OCR=False`)**
    *   **VLM Only Pipeline.** 
    *   Bypasses the computational overhead of EasyOCR.
    *   Relies *strictly* on Vision Language Models (like GPT-4o or Gemini-1.5-Pro Vision) to look at the Google Maps screenshot and determine whether the crosshairs are directly over the suspected location.

3. **`Text2GeolocationV7_no_roads.py` (`USE_ROADS=False`)**
    *   **Context-light Pipeline.**
    *   Discards the injection of `bd_roads.json`. Useful for saving tokens (cutting down on costs) or testing how models perform without extensive road topology hints. 

4. **`Text2GeolocationV7_llama.py` (`USE_LLAMA_JSON=True`)**
    *   **Structured Output Pipeline.**
    *   Specifically engineered for `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` running on Together AI. 
    *   Utilizes Pydantic-enforced strict JSON schema outputs instead of regex scraping, vastly increasing stability for this specific model architecture.

---

## 📊 Outputs & Results

When completing a run (`RESULTS_DIR` = `results/` or `results_single/`):
- **`benchmark_results.csv`**: A dense, one-row-per-article sheet logging predicted lat/lon, calculated error distances vs ground truth (`Actual Co-ordinates`), inference timings, success flags, and detailed token analytics per API call.
- **`benchmark_verbose.txt`**: The full stdout of the console tracing the entire thought process, query generation, and logic fallback of the agents.
- **`benchmark_calls.jsonl`**: A line-by-line JSON record logging every single LLM network call, token costs, and prompt payload.
- **`screenshots/`**: A generated folder containing the Google maps screenshots the VLM/OCR looked at during analysis.

---

## 📑 Citation

If you use ALIGN or extend this work, please cite:

```bibtex
@misc{chowdhury2025alignvisionlanguageframeworkhighaccuracy,
      title={ALIGN: A Vision-Language Framework for High-Accuracy Accident Location Inference through Geo-Spatial Neural Reasoning}, 
      author={MD Thamed Bin Zaman Chowdhury and Moazzem Hossain},
      year={2025},
      eprint={2511.06316},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2511.06316}, 
}
```

---

## 🤝 Acknowledgements

* **Logistics and Intelligent Transport Systems (LITS) Lab**, BUET
* **Google, OpenaAI, TogetherAI** for multimodal reasoning
* **EasyOCR (Jaided AI)** for bilingual text detection
* **Selenium Project** for browser automation

---

## 📜 License

This project is now released under the **Apache License 2.0** (see the [`LICENSE`](LICENSE) file for full details).

> Previously released under the MIT License. As of v2.0, the project has transitioned to the Apache License 2.0 to better support academic and commercial reuse with patent protection clauses.

**Note:** Always comply with Google Maps and Gemini API terms of service when running this pipeline.
