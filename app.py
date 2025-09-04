# app.py
import os
import time
import random
import pandas as pd
import streamlit as st
import docx
from PyPDF2 import PdfReader
from pathlib import Path

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from prompt import PROMPT_FTE  # ต้องมีไฟล์ prompt.py ที่ประกาศ PROMPT_FTE

# =========================
# PATHS (GitHub/Streamlit Cloud friendly)
# =========================
BASE_DIR = Path(__file__).resolve().parent

# ไฟล์อยู่ที่รากรีโป (ตามภาพ GitHub ที่ให้มา)
EXCEL_CANDIDATES = [
    BASE_DIR / "FTE-DATASET.xlsx",
    BASE_DIR / "workaw_data.xlsx",   # เผื่อใช้ไฟล์นี้ด้วย
]
DOCX_CANDIDATES  = [BASE_DIR / "Data Set No Question docx.docx"]
PDF_CANDIDATES   = [BASE_DIR / "Data Set No Question pdf.pdf"]

AVATAR_CANDIDATES = [BASE_DIR / "assets" / "green-bot.png"]  # ถ้าไม่มีจะไม่ใช้

def pick_first_existing(paths):
    for p in paths:
        if p.exists():
            return p
    return None

EXCEL_PATH  = pick_first_existing(EXCEL_CANDIDATES)
DOCX_PATH   = pick_first_existing(DOCX_CANDIDATES)
PDF_PATH    = pick_first_existing(PDF_CANDIDATES)
AVATAR_PATH = pick_first_existing(AVATAR_CANDIDATES)

PAGE_ICON = str(AVATAR_PATH) if AVATAR_PATH else None

# =========================
# Page config & Header
# =========================
st.set_page_config(page_title="FTE Chatbot • KMUTNB", page_icon=PAGE_ICON, layout="centered")
st.title("💬 Welcome to Faculty of Technical Education, KMUTNB")

# =========================
# API Key & Model config
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
# Chat history utils
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
# File readers (path-based) + cache
# =========================
@st.cache_data(show_spinner=False)
def extract_text_from_docx(docx_path: str) -> str:
    try:
        d = docx.Document(docx_path)
        return "\n".join([p.text for p in d.paragraphs])
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
def load_excel_as_text(excel_path: str, max_rows: int = 80) -> str:
    try:
        if not os.path.exists(excel_path):
            return ""
        df = pd.read_excel(excel_path)
        # ลด payload
        if df.shape[1] > 8:
            df = df.iloc[:, :8]
        if len(df) > max_rows:
            df = df.head(max_rows)
        return df.to_csv(index=False)
    except Exception as e:
        st.error(f"Error reading Excel file '{excel_path}': {e}")
        return ""

# =========================
# Build reference corpus + Sidebar status
# =========================
def build_reference_corpus_with_sidebar_status(
    excel_file: Path | None = EXCEL_PATH,
    word_file: Path | None = DOCX_PATH,
    pdf_file:  Path | None = PDF_PATH,
    max_chars: int = 45_000,
) -> str:
    def _name(p: Path | None) -> str:
        return p.name if isinstance(p, Path) else "N/A"

    st.session_state["excel_file_name"] = _name(excel_file)
    st.session_state["word_file_name"]  = _name(word_file)
    st.session_state["pdf_file_name"]   = _name(pdf_file)

    st.session_state.setdefault("excel_status", "ยังไม่ได้โหลด")
    st.session_state.setdefault("word_status",  "ยังไม่ได้โหลด")
    st.session_state.setdefault("pdf_status",   "ยังไม่ได้โหลด")

    parts = []

    # Excel
    if isinstance(excel_file, Path) and excel_file.exists():
        try:
            st.session_state["excel_status"] = "กำลังโหลด..."
            txt = load_excel_as_text(str(excel_file))
            if txt:
                parts.append("ข้อมูลจากไฟล์ Excel (CSV):\n" + txt)
            st.session_state["excel_status"] = "โหลดสำเร็จ"
        except Exception as e:
            st.session_state["excel_status"] = f"ผิดพลาด: {e}"
    else:
        st.session_state["excel_status"] = "ไม่พบไฟล์"

    # Word
    if isinstance(word_file, Path) and word_file.exists():
        try:
            st.session_state["word_status"] = "กำลังโหลด..."
            txt = extract_text_from_docx(str(word_file))
            if txt:
                parts.append("ข้อมูลจากไฟล์ Word:\n" + txt)
            st.session_state["word_status"] = "โหลดสำเร็จ"
        except Exception as e:
            st.session_state["word_status"] = f"ผิดพลาด: {e}"
    else:
        st.session_state["word_status"] = "ไม่พบไฟล์"

    # PDF
    if isinstance(pdf_file, Path) and pdf_file.exists():
        try:
            st.session_state["pdf_status"] = "กำลังโหลด..."
            txt = extract_text_from_pdf(str(pdf_file))
            if txt:
                parts.append("ข้อมูลจากไฟล์ PDF:\n" + txt)
            st.session_state["pdf_status"] = "โหลดสำเร็จ"
        except Exception as e:
            st.session_state["pdf_status"] = f"ผิดพลาด: {e}"
    else:
        st.session_state["pdf_status"] = "ไม่พบไฟล์"

    blob = "\n\n".join(parts).strip()
    if len(blob) > max_chars:
        blob = blob[:max_chars] + "\n\n[TRUNCATED]"
    return blob

# โหลดคอร์ปัส (ก่อน Render Sidebar)
REFERENCE_BLOB = build_reference_corpus_with_sidebar_status()

# =========================
# Session State (messages)
# =========================
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "คุณต้องการสอบถามข้อมูลของคณะครุศาสตร์อุตสาหกรรมเรื่องใดคะ"}
    ]
if "previous_messages" not in st.session_state:
    st.session_state["previous_messages"] = []

# =========================
# Sidebar (Clear/Restore + สถานะไฟล์)
# =========================
with st.sidebar:
    st.header("การจัดการแชท")
    if st.button("Clear History"):
        clear_history()
    if st.button("Restore Last History"):
        restore_history()

    st.markdown("---")
    st.header("สถานะการโหลดไฟล์ข้อมูล")
    st.info(f"Excel ({st.session_state.get('excel_file_name', 'N/A')}): {st.session_state.get('excel_status', 'ยังไม่ได้โหลด')}")
    st.info(f"Word ({st.session_state.get('word_file_name', 'N/A')}): {st.session_state.get('word_status', 'ยังไม่ได้โหลด')}")
    st.info(f"PDF ({st.session_state.get('pdf_file_name', 'N/A')}): {st.session_state.get('pdf_status', 'ยังไม่ได้โหลด')}")

# =========================
# Render History
# =========================
assistant_avatar = str(AVATAR_PATH) if AVATAR_PATH else None

for msg in st.session_state["messages"]:
    if msg["role"] == "assistant":
        st.chat_message("assistant", avatar=assistant_avatar).write(msg["content"])
    else:
        st.chat_message(msg["role"]).write(msg["content"])

# =========================
# Build history for Gemini
# =========================
def build_history_for_gemini(messages):
    history = []
    if REFERENCE_BLOB:
        history.append({"role": "user", "parts": [{"text": "ข้อมูลอ้างอิง:\n" + REFERENCE_BLOB}]})
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [{"text": m["content"]}]})
    return history

# =========================
# Typing-effect streaming
# =========================
def stream_typing_response(chat_session, prompt_text: str, typing_delay: float = 0.004) -> str:
    status = st.empty()      # แสดงสถานะชั่วคราว
    placeholder = st.empty() # ที่ใส่ข้อความพิมพ์ไหล ๆ
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
# Chat input & response
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
