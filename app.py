# app.py
import os
import time
import random
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st
import docx
from PyPDF2 import PdfReader

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from prompt import PROMPT_FTE  # ต้องมีไฟล์ prompt.py ที่ประกาศ PROMPT_FTE

# =========================
# PATHS & DISCOVERY
# =========================
BASE_DIR = Path(__file__).resolve().parent

# ส่วนขยายไฟล์ที่รองรับ
DOC_EXTS = {".docx"}
TABULAR_EXTS = {".csv", ".xlsx", ".xls"}
PDF_EXTS = {".pdf"}

# ไอคอนบอท (ถ้ามี)
AVATAR_PATH = BASE_DIR / "assets" / "green-bot.png"
PAGE_ICON = str(AVATAR_PATH) if AVATAR_PATH.exists() else None

# =========================
# PAGE CONFIG & HEADER
# =========================
st.set_page_config(page_title="FTE Chatbot • KMUTNB", page_icon=PAGE_ICON, layout="centered")
st.title("FTE Chatbot • KMUTNB")

# =========================
# API KEY & MODEL CONFIG
# =========================
api_key = st.secrets.get("GEMINI_APIKEY")
if not api_key:
    st.error("ไม่พบ GEMINI_APIKEY ในไฟล์ .streamlit/secrets.toml โปรดตรวจสอบการตั้งค่า.")
    st.stop()

genai.configure(api_key=api_key)

generation_config = {
    "temperature": 0.1,
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
MODEL_NAME = "gemini-2.0-flash"

model = genai.GenerativeModel(
    model_name=MODEL_NAME,
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
# FILE READERS (CACHED)
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
def load_excel_as_text(excel_path: str, max_rows: int = 120, max_cols: int = 12) -> str:
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
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts_low]

@st.cache_data(show_spinner=False)
def discover_all_files(base_dir: str) -> dict:
    root = Path(base_dir)
    found_docx  = rglob_many(root, DOC_EXTS)
    found_tab   = rglob_many(root, TABULAR_EXTS)
    found_pdf   = rglob_many(root, PDF_EXTS)
    return {
        "docx": sorted(found_docx),
        "tabular": sorted(found_tab),
        "pdf": sorted(found_pdf),
    }

FOUND = discover_all_files(str(BASE_DIR))

# =========================
# BUILD REFERENCE CORPUS + SIDEBAR STATUS
# =========================
@st.cache_data(show_spinner=False)
def build_reference_corpus_from_all_files(
    docx_files: list[Path],
    tabular_files: list[Path],
    pdf_files: list[Path],
    total_max_chars: int = 90_000,
    per_docx_max_chars: int = 16_000,
    per_pdf_max_chars: int = 8_000,
    per_tabular_rows: int = 160,
    per_tabular_cols: int = 12,
) -> tuple[str, dict]:
    """
    อ่านทุกไฟล์ตามชนิด แล้วรวมข้อความเป็นคอร์ปัสสำหรับโมเดล
    คืนค่า: (corpus_text, status_dict)
    """
    parts = []
    status = {"docx": [], "pdf": [], "tabular": []}
    total_chars = 0

    # DOCX
    for p in docx_files:
        try:
            txt = extract_text_from_docx(str(p))[:per_docx_max_chars]
            if txt.strip():
                frag = f"[DOCX] {p.name}\n" + txt
                if total_chars + len(frag) <= total_max_chars:
                    parts.append(frag)
                    total_chars += len(frag)
                status["docx"].append((p.name, "โหลดสำเร็จ"))
            else:
                status["docx"].append((p.name, "ไฟล์ว่างหรืออ่านไม่ได้"))
        except Exception as e:
            status["docx"].append((p.name, f"ผิดพลาด: {e}"))

    # TABULAR (CSV/XLSX/XLS)
    for p in tabular_files:
        try:
            if p.suffix.lower() == ".csv":
                txt = load_csv_as_text(str(p), max_rows=per_tabular_rows, max_cols=per_tabular_cols)
            else:
                txt = load_excel_as_text(str(p), max_rows=per_tabular_rows, max_cols=per_tabular_cols)
            if txt.strip():
                frag = f"[TABLE] {p.name}\n" + txt
                if total_chars + len(frag) <= total_max_chars:
                    parts.append(frag)
                    total_chars += len(frag)
                status["tabular"].append((p.name, "โหลดสำเร็จ"))
            else:
                status["tabular"].append((p.name, "ไฟล์ว่างหรืออ่านไม่ได้"))
        except Exception as e:
            status["tabular"].append((p.name, f"ผิดพลาด: {e}"))

    # PDF
    for p in pdf_files:
        try:
            txt = extract_text_from_pdf(str(p))[:per_pdf_max_chars]
            if txt.strip():
                frag = f"[PDF] {p.name}\n" + txt
                if total_chars + len(frag) <= total_max_chars:
                    parts.append(frag)
                    total_chars += len(frag)
                status["pdf"].append((p.name, "โหลดสำเร็จ"))
            else:
                status["pdf"].append((p.name, "ไฟล์ว่างหรืออ่านไม่ได้"))
        except Exception as e:
            status["pdf"].append((p.name, f"ผิดพลาด: {e}"))

    corpus = "\n\n".join(parts)
    if len(corpus) > total_max_chars:
        corpus = corpus[:total_max_chars] + "\n\n[TRUNCATED]"
    return corpus, status

REFERENCE_BLOB, LOAD_STATUS = build_reference_corpus_from_all_files(
    FOUND["docx"], FOUND["tabular"], FOUND["pdf"]
)

# =========================
# SESSION STATE (MESSAGES)
# =========================
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "คุณต้องการสอบถามข้อมูลของคณะครุศาสตร์อุตสาหกรรมเรื่องใดคะ"}
    ]
if "previous_messages" not in st.session_state:
    st.session_state["previous_messages"] = []

# =========================
# SIDEBAR (CLEAR/RESTORE + สถานะไฟล์)
# =========================
with st.sidebar:
    st.header("การจัดการแชท")
    col1, col2 = st.columns(2)
    if col1.button("Clear History"):
        clear_history()
    if col2.button("Restore"):
        restore_history()

    st.markdown("---")
    st.header("ไฟล์ที่พบในโปรเจ็กต์")
    st.write(f"- DOCX: {len(FOUND['docx'])} ไฟล์")
    st.write(f"- ตาราง (CSV/XLSX/XLS): {len(FOUND['tabular'])} ไฟล์")
    st.write(f"- PDF: {len(FOUND['pdf'])} ไฟล์")

    with st.expander("สถานะการโหลด DOCX"):
        for name, s in LOAD_STATUS["docx"]:
            st.info(f"{name} : {s}")
    with st.expander("สถานะการโหลดตาราง (CSV/XLSX/XLS)"):
        for name, s in LOAD_STATUS["tabular"]:
            st.info(f"{name} : {s}")
    with st.expander("สถานะการโหลด PDF"):
        for name, s in LOAD_STATUS["pdf"]:
            st.info(f"{name} : {s}")

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
# BUILD HISTORY FOR GEMINI
# =========================
def build_history_for_gemini(messages):
    history = []
    if REFERENCE_BLOB:
        # ไม่แสดงเนื้อหาไฟล์ให้ผู้ใช้เห็นโดยตรง แต่ส่งเป็นบริบทให้โมเดล
        history.append({"role": "user", "parts": [{"text": "ข้อมูลอ้างอิง:\n" + REFERENCE_BLOB}]})
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [{"text": m["content"]}]})
    return history

# =========================
# TYPING-EFFECT STREAMING
# =========================
def stream_typing_response(chat_session, prompt_text: str, typing_delay: float = 0.004) -> str:
    status = st.empty()
    placeholder = st.empty()
    status.write("กำลังค้นหาคำตอบ...")

    full_text = ""
    first_char_written = False
    try:
        for chunk in chat_session.send_message(prompt_text, stream=True):
            text = getattr(chunk, "text", "") or ""
            for ch in text:
                if not first_char_written:
                    status.empty()
                    first_char_written = True
                full_text += ch
                placeholder.markdown(full_text)
                time.sleep(typing_delay)
        status.empty()
    except Exception as e:
        status.empty()
        placeholder.markdown(f"เกิดข้อผิดพลาดระหว่างสตรีมคำตอบ: {e}")
    return full_text

# =========================
# CHAT INPUT & RESPONSE
# =========================
prompt = st.chat_input("พิมพ์คำถามของคุณที่นี่...")
if prompt:
    # ผู้ใช้
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # ประวัติ + เริ่มแชทกับโมเดล
    history_payload = build_history_for_gemini(st.session_state["messages"][:-1])
    chat_session = model.start_chat(history=history_payload)

    # ผู้ช่วย
    with st.chat_message("assistant", avatar=assistant_avatar):
        normalized = prompt.strip().lower()

        if normalized == "history":
            history_text = "\n".join(
                [f"{m['role'].capitalize()}: {m['content']}" for m in st.session_state["messages"]]
            )
            tmp_session = genai.GenerativeModel(
                model_name=MODEL_NAME,
                safety_settings=SAFETY_SETTINGS,
                generation_config=generation_config,
                system_instruction=PROMPT_FTE,
            ).start_chat(history=[])
            reply = stream_typing_response(
                chat_session=tmp_session,
                prompt_text=f"สรุปประวัติการสนทนานี้ให้อ่านง่าย กระชับ และเป็นกันเอง:\n\n{history_text}",
                typing_delay=0.003
            )
        else:
            reply = stream_typing_response(chat_session, prompt_text=prompt, typing_delay=0.004)

    # ปิดท้ายทุกคำตอบด้วยประโยคสุภาพแบบสุ่ม (ไม่มีอีโมจิ)
    followups = [
        "\n\nมีอะไรเพิ่มเติมที่ต้องการให้ฉันช่วยอีกไหมคะ",
        "\n\nต้องการข้อมูลส่วนไหนเพิ่มเติมอีกไหมคะ",
        "\n\nอยากให้ช่วยตรวจสอบรายละเอียดอื่นเพิ่มเติมไหมคะ",
        "\n\nมีหัวข้ออื่นของคณะครุศาสตร์อุตสาหกรรมที่อยากทราบอีกไหมคะ",
        "\n\nหากต้องการข้อมูลเชิงลึก ระบุรหัสวิชา/ชื่อหลักสูตรเพิ่มเติมได้เลยนะคะ",
    ]
    reply_with_followup = reply + random.choice(followups)

    # เก็บลงประวัติ
    st.session_state["messages"].append({"role": "assistant", "content": reply_with_followup})
