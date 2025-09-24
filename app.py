
import io
import re
import json
import time
import base64
import zipfile
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Tuple

import pandas as pd
import streamlit as st

# Optional PDF stack
try:
    import pdfplumber
except Exception as e:
    pdfplumber = None

# Optional OCR stack (requires tesseract installed in the environment)
try:
    import pytesseract
    from PIL import Image
    import pdf2image
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

st.set_page_config(page_title="Case Data Tracker", page_icon="📄", layout="wide")
st.title("📄 Case Data Tracker — Bulk Upload + PDF Parsing")

with st.expander("About this tool", expanded=False):
    st.write("""
    This app lets you bulk upload case data via CSV/XLSX and parse one or more PDFs
    (text-based or—if your system has Tesseract—image-based using OCR).
    You can define extraction rules (regex patterns) to pull out:
    - Case Number
    - Claimant/Owner Name
    - Amount (USD)
    - Address (if present)
    Then review, clean, dedupe, filter, and export your results.
    """)

# -----------------------------
# Helpers
# -----------------------------

DEFAULT_RULES = {
    "case_number": [
        r"(?i)case(?:\s*no\.?| number)?\s*[:\-]?\s*([A-Z0-9\-]{4,})",
        r"(?i)\b(\d{2,4}\-?[A-Z]?\-?\d{3,6}\-?\d{0,4})\b"
    ],
    "name": [
        r"(?i)(?:claimant|owner|defendant|plaintiff)\s*[:\-]\s*([A-Z][A-Za-z'\-\. ]{1,80})",
        r"(?i)\b([A-Z][A-Za-z'\-\.]+(?:\s+[A-Z][A-Za-z'\-\.]+){0,3})\b"
    ],
    "amount": [
        r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)",
        r"(?i)amount\s*[:\-]?\s*\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)"
    ],
    "address": [
        r"(?i)\b(\d{1,5}\s+[A-Za-z0-9'\.\- ]+,\s*[A-Za-z\.\- ]+,\s*[A-Z]{2}\s*\d{5}(?:-\d{4})?)\b"
    ]
}

def parse_amount_to_float(s: str) -> float:
    if pd.isna(s):
        return None
    s = str(s).strip().replace("$", "").replace(",", "")
    try:
        return float(s)
    except Exception:
        return None

def extract_with_rules(text: str, rules: Dict[str, List[str]]) -> Dict[str, Any]:
    out = {"case_number": None, "name": None, "amount_raw": None, "address": None}
    for key, patterns in rules.items():
        for pat in patterns:
            m = re.search(pat, text, re.MULTILINE)
            if m:
                out[key] = m.group(1).strip()
                break
    out["amount"] = parse_amount_to_float(out["amount_raw"])
    return out

def pdf_to_texts(file_bytes: bytes, use_ocr: bool=False) -> List[str]:
    """
    Returns a list of page texts.
    If use_ocr is True and OCR stack is available, uses OCR per page image.
    Otherwise uses pdfplumber for text extraction (when available).
    """
    texts = []
    if use_ocr and OCR_AVAILABLE:
        # Convert PDF to images and OCR each page
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tf:
            tf.write(file_bytes)
            tf.flush()
            images = pdf2image.convert_from_path(tf.name)
            for im in images:
                text = pytesseract.image_to_string(im)
                texts.append(text or "")
        return texts

    # Text-based extraction via pdfplumber
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    texts.append(page.extract_text() or "")
            return texts
        except Exception:
            pass

    # Fallback: raw bytes decode best-effort
    try:
        texts.append(file_bytes.decode("utf-8", errors="ignore"))
    except Exception:
        texts.append("")
    return texts

def make_download_link(df: pd.DataFrame, filename: str, label: str) -> None:
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label=label, data=csv, file_name=filename, mime="text/csv")

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Try to normalize typical columns after CSV/XLSX import
    rename_map = {}
    cols = {c.lower(): c for c in df.columns}
    if "case" in cols: rename_map[cols["case"]] = "case_number"
    if "case_number" in cols: rename_map[cols["case_number"]] = "case_number"
    if "caseno" in cols: rename_map[cols["caseno"]] = "case_number"
    if "name" in cols: rename_map[cols["name"]] = "name"
    if "claimant" in cols: rename_map[cols["claimant"]] = "name"
    if "owner" in cols: rename_map[cols["owner"]] = "name"
    if "amount" in cols: rename_map[cols["amount"]] = "amount_raw"
    if "excess" in cols: rename_map[cols["excess"]] = "amount_raw"
    if "address" in cols: rename_map[cols["address"]] = "address"

    df = df.rename(columns=rename_map)
    if "amount" not in df.columns and "amount_raw" in df.columns:
        df["amount"] = df["amount_raw"].apply(parse_amount_to_float)
    return df

# -----------------------------
# Sidebar — Config
# -----------------------------
st.sidebar.header("Settings")
min_amount = st.sidebar.number_input("Filter: minimum amount (USD)", min_value=0, value=0, step=1000)
dedupe_on_case = st.sidebar.checkbox("Dedupe by case number", value=True)
rules_json = st.sidebar.text_area("Extraction rules (regex JSON)", value=json.dumps(DEFAULT_RULES, indent=2), height=250)

try:
    rules = json.loads(rules_json)
except Exception as e:
    st.sidebar.error(f"Invalid JSON for rules: {e}")
    rules = DEFAULT_RULES

# -----------------------------
# Bulk Upload — CSV/XLSX
# -----------------------------
st.header("1) Bulk upload tabular data (CSV or Excel)")
tab_files = st.file_uploader("Upload one or more CSV/XLSX files", type=["csv", "xlsx", "xls"], accept_multiple_files=True)
tab_rows = []
for f in tab_files or []:
    try:
        if f.name.lower().endswith(".csv"):
            df = pd.read_csv(f)
        else:
            df = pd.read_excel(f)
        df["__source"] = f.name
        df = normalize_columns(df)
        tab_rows.append(df)
    except Exception as e:
        st.warning(f"Could not read {f.name}: {e}")

tab_df = pd.concat(tab_rows, ignore_index=True) if tab_rows else pd.DataFrame()

# -----------------------------
# Parse PDFs
# -----------------------------
st.header("2) Parse one or more PDFs")
use_ocr = st.checkbox("Use OCR if needed (requires Tesseract available)", value=False)
pdf_files = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)

parsed_records = []
for pf in pdf_files or []:
    b = pf.read()
    pages = pdf_to_texts(b, use_ocr=use_ocr)
    for i, page_text in enumerate(pages):
        rec = extract_with_rules(page_text, rules)
        rec["page"] = i + 1
        rec["__source"] = pf.name
        rec["__extracted_text"] = page_text[:2000]  # preview
        parsed_records.append(rec)

pdf_df = pd.DataFrame(parsed_records)

# -----------------------------
# Merge & Clean
# -----------------------------
st.header("3) Review, clean, and filter")
merged = pd.concat([tab_df, pdf_df], ignore_index=True) if not tab_df.empty or not pdf_df.empty else pd.DataFrame(
    columns=["case_number", "name", "amount", "address", "__source", "page", "__extracted_text"]
)

# Standardize key columns
for col in ["case_number", "name", "address"]:
    if col not in merged.columns:
        merged[col] = None
if "amount" not in merged.columns and "amount_raw" in merged.columns:
    merged["amount"] = merged["amount_raw"].apply(parse_amount_to_float)
if "amount" not in merged.columns:
    merged["amount"] = None

# Filter by minimum amount
merged = merged.copy()
merged["amount_num"] = merged["amount"].apply(parse_amount_to_float)
merged = merged[ (merged["amount_num"].fillna(0) >= float(min_amount)) ]

# Dedupe if needed
if dedupe_on_case and "case_number" in merged.columns:
    merged = merged.sort_values(by=["amount_num"], ascending=False).drop_duplicates(subset=["case_number"], keep="first")

# Pretty columns
display_cols = ["case_number", "name", "amount_num", "address", "__source", "page"]
display_cols = [c for c in display_cols if c in merged.columns]
st.dataframe(merged[display_cols].rename(columns={"amount_num":"amount"}), use_container_width=True, height=400)

# Quick filters
high_10k = merged[ merged["amount_num"].fillna(0) >= 10000 ]
st.caption(f"Records ≥ $10,000: {len(high_10k)}")
make_download_link(merged.drop(columns=["amount_num"]), "case_data_all.csv", "⬇️ Download CSV (all)")
make_download_link(high_10k.drop(columns=["amount_num"]), "case_data_over_10k.csv", "⬇️ Download CSV (≥ $10k)")

# -----------------------------
# Export a ZIP of raw parsed texts (optional)
# -----------------------------
st.header("4) (Optional) Download raw parsed texts")
if not pdf_df.empty:
    if st.button("Create ZIP of extracted page texts"):
        with tempfile.TemporaryDirectory() as td:
            for i, row in pdf_df.iterrows():
                name = f"{row['__source']}_p{int(row['page'])}.txt"
                with open(f"{td}/{name}", "w", encoding="utf-8") as f:
                    f.write(row.get("__extracted_text",""))
            zpath = f"{td}/extracted_texts_{int(time.time())}.zip"
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                for fn in os.listdir(td):
                    if fn.endswith(".txt"):
                        zf.write(f"{td}/{fn}", arcname=fn)
        with open(zpath, "rb") as zf:
            st.download_button("⬇️ Download ZIP of texts", data=zf.read(), file_name="extracted_texts.zip", mime="application/zip")
else:
    st.caption("Upload PDFs above to enable this option.")

st.success("Ready. Upload data above to get started.")
