
# Case Data Tracker — Bulk Upload + PDF Parsing

A lightweight Streamlit web app to ingest case lists (CSV/XLSX) and parse one or more PDFs to extract case number, name, amount, and address using customizable regex rules.

## Features
- Bulk upload CSV/XLSX; normalize common headers
- Upload and parse multiple PDFs
  - Text extraction with `pdfplumber`
  - Optional OCR per page if Tesseract is installed (`Use OCR` checkbox)
- Customizable extraction rules via JSON (regex)
- Filter by minimum amount (e.g., show ≥ $10,000)
- Dedupe by case number
- Preview table and export CSVs (all and ≥$10k)
- Optional ZIP of raw page texts for auditing

## Quickstart (local)
1. Install Python 3.10+
2. Create a virtual environment and install requirements:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. (Optional OCR) Install Tesseract:
   - macOS (brew): `brew install tesseract`
   - Ubuntu: `sudo apt-get install tesseract-ocr`
4. Run:
   ```bash
   streamlit run app.py
   ```
5. Open the local URL printed in your terminal.

## One-click-ish deploys
- **Streamlit Community Cloud**: create a public Git repo with these files and "New app".
- **Replit**: create a new Python Repl, add files, and run `streamlit run app.py`.
- **Railway/Render**: deploy as a web service; set start command to `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.

## Tips
- Tune the regex rules in the sidebar for your county formats.
- If PDFs are scanned, toggle **Use OCR** (requires Tesseract installed on the host).

---

Made for fast, no-drama case data wrangling.
