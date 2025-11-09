# ALIGN: A Vision–Language Framework for High-Accuracy Accident Location Inference through Geo-Spatial Neural Reasoning
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Authors:**  
MD Thamed Bin Zaman Chowdhury — Bangladesh University of Engineering and Technology (BUET)  
Dr. Moazzem Hossain — BUET  

---

## ⚠️ Critical Performance Warning

🚨 **WARNING:** Running this pipeline on a **CPU-only setup will be extremely slow.**  
In benchmark testing, an **NVIDIA RTX 3060 (6 GB VRAM)** laptop GPU was used to handle the **EasyOCR** stage.  
Without GPU support, OCR will take several minutes **per image**, making the end-to-end pipeline impractically slow.

🧩 **Recommended Setup:**
- Use **Python 3.10.18** (PyTorch is most stable on this version as of 2025).  
- Use a **GPU-enabled Conda environment** with CUDA properly configured (11.8 / 12.1).  
- Follow PyTorch’s official installation instructions for your CUDA version.

---

## 🔍 Overview

ALIGN (Accident Location Inference through Geo-Spatial Neural Reasoning) is a **vision–language AI pipeline** that automatically pinpoints the coordinates of traffic accident locations described in Bangla-language news articles.  
It combines:
- **Gemini 2.5 Flash (VLM)** for multimodal spatial reasoning  
- **Selenium** for automated Google Maps exploration  
- **EasyOCR** for bilingual Bangla + English map text recognition  
- **Fuzzy matching + reasoning logic** for verifying map and article consistency  

---

## 🧩 System Architecture

The figure below illustrates the end-to-end **ALIGN** pipeline integrating textual reasoning, map-based spatial verification, OCR processing, and vision–language inference.

<img width="975" height="1281" alt="image" src="https://github.com/user-attachments/assets/985b5673-8ad3-45a8-bcd3-0f3193ee4abb" />

*Figure: ALIGN multi-stage reasoning pipeline combining text extraction, OCR validation, grid-based spatial search, and Gemini VLM-based verification.*

## 📁 Repository Contents

| File / Folder | Description |
|----------------|-------------|
| `Pipeline Notebook.ipynb` | Main executable notebook for users |
| `Text2Geolocation.py` | Core logic integrating OCR, Gemini reasoning, and coordinate extraction |
| `OCR_ss_test.py` | Custom EasyOCR agent used by the main pipeline |
| `bd_roads.json` | Road code + name mapping for Bangladesh |
| `screenshots/` | Grid-search map screenshots |
| `screenshots_first/` | First-stage map screenshots from autocomplete suggestions |

---

## 🔑 API Requirement

This system requires **your own Google Gemini API keys** to function.  
You must obtain them from your Google AI Studio account:  
👉 [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

- Create multiple API keys for parallel inference (recommended 2–3).  
- Paste them inside the **“User Inputs” cell** of the notebook as a Python list.

Example:
```python
Gemini_API_Keys = [
  "YOUR_API_KEY_1",
  "YOUR_API_KEY_2",
  "YOUR_API_KEY_3"
]
````

Without valid keys, the pipeline will fail when calling Gemini for multimodal reasoning.

---

## 🧰 Environment Setup

### 1️⃣ Create Conda Environment (Python 3.10.18)

```bash
conda create -n align_env python=3.10.18
conda activate align_env
```

### 2️⃣ Install Required Packages

Run these in a terminal (the notebook includes the same commands commented at the top):

```bash
pip install torch torchvision
pip install easyocr
pip install google-generativeai -U
pip install thefuzz python-Levenshtein selenium
```

### 3️⃣ (Optional) GPU Setup

Install the correct PyTorch version for your CUDA:

```bash
# Example for CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

If you only have a CPU (⚠️ very slow):

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

---

## 🚀 How to Run

1. **Open the notebook**

   ```bash
   jupyter notebook "Pipeline Notebook.ipynb"
   ```

2. **Cell 1 — Install Dependencies**
   Uncomment and run the pip commands if your environment doesn’t already include the required libraries.

3. **Cell 2 — User Inputs**

   * Insert your Gemini API keys under `Gemini_API_Keys`.
   * Paste your Bangla or English accident news article inside `news_string` (the sample is already included).

4. **Cell 3 — Run the Pipeline**

   ```python
   import Text2Geolocation
   co_ordinates = Text2Geolocation.geolocation_agent(news_string, Gemini_API_Keys)
   print(co_ordinates)
   ```

   This cell launches the entire ALIGN pipeline:

   * Extracts road / landmark cues from text
   * Searches Google Maps via Selenium
   * Captures screenshots and performs OCR
   * Uses Gemini 2.5 Flash to reason whether the map view matches the article
   * Returns the final inferred coordinates

5. **Cell 4 — Outputs**
   Displays the latitude / longitude pair returned by the model:

   ```python
   co_ordinates
   ```

---

## 📊 Example Output

```
Latitude: 25.025
Longitude: 91.387
```

These correspond to the verified location (Bahadurpur Pur Uttar Para, Sunamganj Highway) from the sample article.

---

## 💻 System Requirements

| Component  | Recommended                                |
| ---------- | ------------------------------------------ |
| OS         | Windows 10/11 or Linux                     |
| Python     | **3.10.18**                                |
| GPU        | NVIDIA RTX 3060 (6 GB VRAM) or higher      |
| RAM        | ≥ 16 GB                                    |
| Browser    | Latest Google Chrome                       |
| API Access | Gemini 2.5 Flash (via google-generativeai) |

---

## 📑 Citation

If you use ALIGN or extend this work, please cite:

```bibtex
@article{Chowdhury2025ALIGN,
  author  = {MD Thamed Bin Zaman Chowdhury and Moazzem Hossain},
  title   = {ALIGN: A Vision–Language Framework for High-Accuracy Accident Location Inference through Geo-Spatial Neural Reasoning},
  journal = {Transportation Research Part C (under review)},
  year    = {2025}
}
```

---

## 🤝 Acknowledgements

* **Logistics and Intelligent Transport Systems (LITS) Lab**, BUET
* **Google Gemini 2.5 Flash** for multimodal reasoning
* **EasyOCR (Jaided AI)** for bilingual text detection
* **Selenium Project** for browser automation

---

## 📜 License

This project is released under the **MIT License** (see `LICENSE` for details).

**Note:** Always comply with Google Maps and Gemini API terms of service when running this pipeline.
