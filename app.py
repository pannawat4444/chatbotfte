# app.py
import os
import time
import random
from pathlib import Path
from typing import Iterable, List, Dict, Tuple
import pandas as pd
import streamlit as st
import docx
from PyPDF2 import PdfReader

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from prompt import PROMPT_FTE  # ต้องมีไฟล์ prompt.py ที่ประกาศ PROMPT_FTE

from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# =========================
# PATHS & DISCOVERY
# =========================
BASE_DIR = Path(__file__).resolve().parent

DOC_EXTS     = {".docx"}
TABULAR_EXTS = {".csv", ".xlsx", ".xls"}
PDF_EXTS     = {".pdf"}

AVATAR_PATH = BASE_DIR / "assets" / "green-bot.png"
PAGE_ICON = str(AVATAR_PATH) if AVATAR_PATH.exists() else None

# =========================
# PAGE CONFIG & HEADER
# =========================
st.set_page_config(page_title="FTE Chatbot • KMUTNB", page_icon=PAGE_ICON, layout="centered")
st.title("🗨️ Computer Education & Civil Engineering and Education Chatbot • FTE of KMUTNB")

# =========================
# API KEY & MODEL CONFIG
# =========================
api_key = st.secrets.get("GEMINI_APIKEY")
if not api_key:
    st.error("ไม่พบ GEMINI_APIKEY ในไฟล์ .streamlit/secrets.toml โปรดตรวจสอบการตั้งค่า.")
    st.stop()

genai.configure(api_key=api_key)

generation_config = {
    "temperature": 0.5,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 1024,
    "response_mime_type": "text/plain",
}
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}
PRIMARY_MODEL_NAME = "gemini-2.5-flash"
FALLBACK_MODEL_NAME = "gemini-2.0-flash"

def make_model(name: str) -> genai.GenerativeModel:
    return genai.GenerativeModel(
        model_name=name,
        safety_settings=SAFETY_SETTINGS,
        generation_config=generation_config,
        system_instruction=PROMPT_FTE,
    )

# =========================
# CHAT HISTORY UTILS
# =========================
def clear_history():
    st.session_state["previous_messages"] = st.session_state.get("messages", []).copy()
    st.session_state["messages"] = [{"role": "assistant", "content": "ประวัติการเเชทของท่าน"}]
    st.rerun()

def restore_history():
    if st.session_state.get("previous_messages"):
        st.session_state["messages"] = st.session_state["previous_messages"].copy()
    else:
        st.warning("ไม่พบประวัติที่สามารถเรียกคืนได้")
    st.rerun()

# =========================
# FILE READERS (CACHED) PDF & Docx
# =========================
@st.cache_data(show_spinner=False)
def extract_text_from_docx(docx_path: str) -> str:
    try:
        d = docx.Document(docx_path)
        return "\n".join([p.text for p in d.paragraphs if p.text.strip()])
    except Exception as e:
        st.error(f"Error reading Word file '{docx_path}': {e}")
        return ""

@st.cache_data(show_spinner=False)
def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        st.error(f"Error reading PDF file '{pdf_path}': {e}")
        return ""

@st.cache_data(show_spinner=False)
def load_excel_as_text(excel_path: str, max_rows: int = 160, max_cols: int = 12) -> str:
    try:
        if not os.path.exists(excel_path):
            return ""
        df = pd.read_excel(excel_path)
        if df.shape[1] > max_cols:
            df = df.iloc[:, :max_cols]
        if len(df) > max_rows:
            df = df.head(max_rows)
        return df.to_csv(index=False)
    except Exception as e:
        st.error(f"Error reading Excel file '{excel_path}': {e}")
        return ""

@st.cache_data(show_spinner=False)
def load_csv_as_text(csv_path: str, max_rows: int = 200, max_cols: int = 12) -> str:
    try:
        if not os.path.exists(csv_path):
            return ""
        df = pd.read_csv(csv_path, engine="python", encoding_errors="ignore")
        if df.shape[1] > max_cols:
            df = df.iloc[:, :max_cols]
        if len(df) > max_rows:
            df = df.head(max_rows)
        return df.to_csv(index=False)
    except Exception as e:
        st.error(f"Error reading CSV file '{csv_path}': {e}")
        return "" 

# =========================
# DISCOVER FILES (RECURSIVE)
# =========================
def rglob_many(root: Path, exts: Iterable[str]) -> list[Path]:
    exts_low = {e.lower() for e in exts}
    # เพิ่มเงื่อนไข .name.startswith("~$") เพื่อละเว้นไฟล์ชั่วคราว
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts_low and not p.name.startswith("~$")]

@st.cache_data(show_spinner=False)
def discover_all_files(base_dir: str) -> dict:
    root = Path(base_dir)
    found_docx  = rglob_many(root, DOC_EXTS)
    found_tab   = rglob_many(root, TABULAR_EXTS)
    found_pdf   = rglob_many(root, PDF_EXTS)

    dataset_file = root / "workaw" / "Data คำตอบ  ครุล่าสุด.docx"
    if dataset_file.exists():
        found_docx.append(dataset_file)
    return {"docx": sorted(found_docx), "tabular": sorted(found_tab), "pdf": sorted(found_pdf)}

FOUND = discover_all_files(str(BASE_DIR))

# =========================
# NEW: COLLECT & CHUNK TEXTS FOR RETRIEVAL
# =========================
def chunk_text(text: str, size: int = 900, overlap: int = 150) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks, i, n = [], 0, len(text)
    while i < n:
        j = min(i + size, n)
        chunks.append(text[i:j])
        i = j - overlap if j - overlap > i else j
    return [c for c in chunks if c.strip()]

@st.cache_data(show_spinner=False)
def collect_chunks(docx_files: List[Path], tabular_files: List[Path], pdf_files: List[Path]) -> List[Dict]:
    rows = []

    # DOCX
    for p in docx_files:
        try:
            txt = extract_text_from_docx(str(p))
            if txt:  # เพิ่มเงื่อนไขเพื่อตรวจสอบว่ามีข้อความหรือไม่
                for c in chunk_text(txt):
                    rows.append({"source": p.name, "kind": "DOCX", "text": c})
        except Exception:
            pass

    # TABULAR
    for p in tabular_files:
        try:
            if p.suffix.lower() == ".csv":
                txt = load_csv_as_text(str(p))
            else:
                txt = load_excel_as_text(str(p))
            if txt:
                for c in chunk_text(txt):
                    rows.append({"source": p.name, "kind": "TABLE", "text": c})
        except Exception:
            pass

    # PDF
    for p in pdf_files:
        try:
            txt = extract_text_from_pdf(str(p))
            if txt:
                for c in chunk_text(txt):
                    rows.append({"source": p.name, "kind": "PDF", "text": c})
        except Exception:
            pass

    return rows

CHUNKS = collect_chunks(FOUND["docx"], FOUND["tabular"], FOUND["pdf"])

# =========================
# NEW: BUILD TF-IDF INDEX (CHAR N-GRAM → ดีสำหรับภาษาไทย)
# =========================
@st.cache_resource(show_spinner=False)
def build_index(chunks: List[Dict]):
    texts = [r["text"] for r in chunks] or ["dummy"]
    vect = TfidfVectorizer(analyzer="char", ngram_range=(3, 5))
    X = vect.fit_transform(texts)
    return vect, X

VECT, X = build_index(CHUNKS)

def retrieve_context(query: str, top_k: int = 8, max_chars: int = 6000) -> Tuple[str, List[Tuple[int, float]]]:
    if not query.strip() or X.shape[0] == 0:
        return "", []
    qv = VECT.transform([query])
    sims = (X @ qv.T).toarray().ravel()  # cosine sim for tfidf-normalized
    idx = np.argsort(-sims)[:top_k]
    picked = [(int(i), float(sims[i])) for i in idx if sims[i] > 0]
    parts, total = [], 0
    for i, _ in picked:
        seg = CHUNKS[i]
        block = f"[{seg['kind']}] {seg['source']}\n{seg['text']}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block); total += len(block)
    return "\n".join(parts), picked

# =========================
# BUILD REFERENCE STATUS (สำหรับ Sidebar เท่านั้น)
# =========================
LOAD_STATUS = {
    "docx": {},
    "tabular": {},
    "pdf": {},
}
for p in FOUND["docx"]:
    LOAD_STATUS["docx"][p.name] = "โหลดสำเร็จ" if any(r["source"] == p.name for r in CHUNKS) else "ไฟล์ว่างหรืออ่านไม่ได้"
for p in FOUND["tabular"]:
    LOAD_STATUS["tabular"][p.name] = "โหลดสำเร็จ" if any(r["source"] == p.name for r in CHUNKS) else "ไฟล์ว่างหรืออ่านไม่ได้"
for p in FOUND["pdf"]:
    LOAD_STATUS["pdf"][p.name] = "โหลดสำเร็จ" if any(r["source"] == p.name for r in CHUNKS) else "ไฟล์ว่างหรืออ่านไม่ได้"

# =========================
# SESSION STATE (MESSAGES)
# =========================
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "คุณต้องการสอบถามข้อมูลเรื่องใดคะ"}
    ]
if "previous_messages" not in st.session_state:
    st.session_state["previous_messages"] = []

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.header("การจัดการแชท")
    col1, col2 = st.columns(2)
    if col1.button("🧹 Clear History"):
        clear_history()
    if col2.button("🔁 Restore"):
        restore_history()


    st.markdown("---")
    #st.header("ไฟล์ที่พบในโปรเจ็กต์")
    #st.write(f"- DOCX: {len(FOUND['docx'])} ไฟล์")
    #st.write(f"- ตาราง (CSV/XLSX/XLS): {len(FOUND['tabular'])} ไฟล์")
    #st.write(f"- PDF: {len(FOUND['pdf'])} ไฟล์")

    #with st.expander("สถานะการโหลด DOCX"):
      #  for name, s in LOAD_STATUS["docx"].items():
            #st.info(f"{name} : {s}")
    #with st.expander("สถานะการโหลดตาราง (CSV/XLSX/XLS)"):
        #for name, s in LOAD_STATUS["tabular"].items():
           # st.info(f"{name} : {s}")
   # with st.expander("สถานะการโหลด PDF"):
        #for name, s in LOAD_STATUS["pdf"].items():
           # st.info(f"{name} : {s}")

# =========================
# RENDER HISTORY
# =========================
assistant_avatar = str(AVATAR_PATH) if AVATAR_PATH.exists() else None
for msg in st.session_state["messages"]:
    if msg["role"] == "assistant":
        st.chat_message("assistant", avatar=assistant_avatar).write(msg["content"])
    else:
        st.chat_message(msg["role"]).write(msg["content"])

# =========================
# BUILD HISTORY FOR GEMINI (ใช้บริบทที่ดึงมา เฉพาะที่เกี่ยว)
# =========================
def build_history_for_gemini(messages, context_text: str):
    history = []
    if context_text:
        history.append({"role": "user", "parts": [{"text": "บริบทอ้างอิง (ซ่อนจากผู้ใช้):\n" + context_text}]})
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [{"text": m["content"]}]})
    return history

# =========================
# STREAMING + RETRY + FALLBACK
# =========================
def _should_retry(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ["429", "quota", "rate", "exceed", "resource exhausted", "deadline exceeded"])

def stream_typing_with_retry(history_payload, prompt_text: str,
                             typing_delay: float = 0.004,
                             retries: int = 2,
                             backoff: float = 2.0) -> str:
    status = st.empty()
    placeholder = st.empty()
    status.write("กำลังค้นหาคำตอบ...")

    def _stream_from_model(model_name: str) -> str:
        nonlocal status, placeholder
        session = make_model(model_name).start_chat(history=history_payload)
        full_text, first_char_written = "", False
        for chunk in session.send_message(prompt_text, stream=True):
            text = getattr(chunk, "text", "") or ""
            for ch in text:
                if not first_char_written:
                    status.empty()
                    first_char_written = True
                full_text += ch
                placeholder.markdown(full_text)
                time.sleep(typing_delay)
        return full_text

    last_err = None
    for attempt in range(retries):
        try:
            return _stream_from_model(PRIMARY_MODEL_NAME)
        except Exception as e:
            last_err = e
            if _should_retry(e) and attempt < retries - 1:
                time.sleep(backoff); backoff *= 2
            else:
                break

    try:
        placeholder.markdown("**สลับไปใช้โมเดลสำรองชั่วคราวเพื่อให้ได้คำตอบค่ะ...**")
        return _stream_from_model(FALLBACK_MODEL_NAME)
    except Exception:
        status.empty()
        placeholder.markdown("ขออภัยค่ะ ระบบไม่สามารถสร้างคำตอบได้ในขณะนี้ กรุณาลองใหม่ภายหลังค่ะ")
        return ""

# =========================
# CHAT INPUT & RESPONSE
# =========================
prompt = st.chat_input("พิมพ์คำถามของคุณที่นี่...")
if prompt:
    # เก็บข้อความผู้ใช้
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # 1) ดึงบริบทที่เกี่ยวข้องจากดัชนี
    context_text, hits = retrieve_context(prompt, top_k=8, max_chars=6000)

    # 2) สร้าง history ที่รวม 'บริบทอ้างอิง' (จะไม่ถูกแสดงใน UI)
    history_payload = build_history_for_gemini(st.session_state["messages"][:-1], context_text)

    # 3) ส่งถามโมเดล (มี retry + fallback)
    with st.chat_message("assistant", avatar=assistant_avatar):
        reply = stream_typing_with_retry(history_payload, prompt_text=prompt, typing_delay=0.004)

    # ปิดท้ายทุกคำตอบด้วยประโยคสุภาพแบบสุ่ม (ไม่มีอีโมจิ)
    followups = [
        "\n\nต้องการข้อมูลส่วนไหนเพิ่มเติมอีกไหมคะ"
    ]
    reply_with_followup = (reply or "") + random.choice(followups)
    
    st.session_state["messages"].append({"role": "assistant", "content": (reply or "") + random.choice(followups)})
