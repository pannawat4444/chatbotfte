# app.py
import os
import time
import pandas as pd
import streamlit as st
import docx
from PyPDF2 import PdfReader

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from prompt import PROMPT_FTE  # ต้องมีไฟล์ prompt.py ที่ประกาศ PROMPT_FTE

# =========================
# 🔧 หน้าแรก & ตั้งค่าทั่วไป + Avatar
# =========================
AVATAR_PATH = "assets/green-bot.png"   # <<-- วางไฟล์ไอคอนบอทสีเขียวที่นี่
PAGE_ICON = AVATAR_PATH if os.path.exists(AVATAR_PATH) else "🟢"

st.set_page_config(page_title="FTE Chatbot • KMUTNB", page_icon=PAGE_ICON, layout="centered")
st.title("💬 Welcome to Faculty of Technical Education, KMUTNB")

# =========================
# 🔐 API KEY & Model config
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
# 📁 Utilities: Load files (cached)
# =========================
@st.cache_data(show_spinner=False)
def extract_text_from_docx(docx_path: str) -> str:
    try:
        d = docx.Document(docx_path)
        return "\n".join([p.text for p in d.paragraphs if p.text.strip()])
    except Exception as e:
        return f"[WARN] อ่านไฟล์ Word ไม่สำเร็จ: {e}"

@st.cache_data(show_spinner=False)
def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t)
        return "\n".join(parts)
    except Exception as e:
        return f"[WARN] อ่านไฟล์ PDF ไม่สำเร็จ: {e}"

@st.cache_data(show_spinner=False)
def load_excel_as_text(excel_path: str, max_rows: int = 80) -> str:
    try:
        df = pd.read_excel(excel_path)
        # จำกัดคอลัมน์/แถวเพื่อลด payload
        if df.shape[1] > 8:
            df = df.iloc[:, :8]
        if len(df) > max_rows:
            df = df.head(max_rows)
        return df.to_csv(index=False)
    except Exception as e:
        return f"[WARN] อ่านไฟล์ Excel ไม่สำเร็จ: {e}"

@st.cache_data(show_spinner=False)
def build_reference_corpus(
    excel_file="FTE-DATASET.xlsx",
    word_file="Data Set chatbotfte.docx",
    pdf_file="Data Set chatbotfte.pdf",
    max_chars=45_000,
) -> str:
    parts = []
    if os.path.exists(excel_file):
        parts.append("ข้อมูลจากไฟล์ Excel (CSV):\n" + load_excel_as_text(excel_file))
    if os.path.exists(word_file):
        parts.append("ข้อมูลจากไฟล์ Word:\n" + extract_text_from_docx(word_file))
    if os.path.exists(pdf_file):
        parts.append("ข้อมูลจากไฟล์ PDF:\n" + extract_text_from_pdf(pdf_file))

    blob = "\n\n".join(parts).strip()
    if len(blob) > max_chars:
        blob = blob[:max_chars] + "\n\n[TRUNCATED]"
    return blob

REFERENCE_BLOB = build_reference_corpus()

# =========================
# 🧠 Session State
# =========================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "ท่านสนใจสอบถามข้อมูลเกี่ยวกับคณะครุศาสตร์อุตสาหกรรม มจพ. ด้านใดคะ"}
    ]
if "previous_messages" not in st.session_state:
    st.session_state.previous_messages = []

# =========================
# 🧹 Sidebar (ไม่มีสถานะไฟล์อ้างอิง)
# =========================
with st.sidebar:
    st.header("การจัดการแชท")
    col1, col2 = st.columns(2)
    if col1.button("🧹 Clear"):
        st.session_state.previous_messages = st.session_state.messages.copy()
        st.session_state.messages = [{"role": "assistant", "content": "ประวัติการเเชทของท่าน"}]
        st.toast("เคลียร์ประวัติแล้ว", icon="🧹")
        st.rerun()
    if col2.button("🔄 Restore"):
        if st.session_state.previous_messages:
            st.session_state.messages = st.session_state.previous_messages.copy()
            st.toast("เรียกคืนประวัติล่าสุดแล้ว", icon="🔄")
        else:
            st.warning("ไม่พบประวัติที่สามารถเรียกคืนได้")

# =========================
# 🗣️ Render History (assistant avatar = green bot icon if available)
# =========================
assistant_avatar = AVATAR_PATH if os.path.exists(AVATAR_PATH) else "🟢"

for msg in st.session_state.messages:
    if msg["role"] == "assistant":
        st.chat_message("assistant", avatar=assistant_avatar).write(msg["content"])
    else:
        st.chat_message(msg["role"]).write(msg["content"])

# =========================
# 🧩 History builder for Gemini
# =========================
def build_history_for_gemini(messages):
    """
    แปลงประวัติแชทเป็นรูปแบบที่ Gemini เข้าใจ
    - ดันคอร์ปัสอ้างอิงเข้าไปเป็น context แรก (ฝั่ง user)
    - ตามด้วยบทสนทนาก่อนหน้า
    """
    history = []
    if REFERENCE_BLOB:
        history.append({"role": "user", "parts": [{"text": "ข้อมูลอ้างอิง:\n" + REFERENCE_BLOB}]})
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        history.append({"role": role, "parts": [{"text": m["content"]}]})
    return history

# =========================
# 🚀 Typing-effect streaming
# =========================
def stream_typing_response(chat_session, prompt_text: str, typing_delay: float = 0.004) -> str:
    """
    สตรีมคำตอบจาก Gemini แล้วแสดงแบบ 'กำลังพิมพ์'
    - ไม่มี dropdown/expander
    - โชว์ 'กำลังค้นหาคำตอบ…' ระหว่างคิด
    - พิมพ์ทีละตัวอักษรจนจบ
    """
    status = st.empty()         # แสดงสถานะชั่วคราว (ระหว่างเริ่มคิด)
    placeholder = st.empty()    # กล่องข้อความที่ค่อย ๆ เติมคำตอบ
    status.write("กำลังค้นหาคำตอบ…")

    full_text = ""
    first_char_written = False
    try:
        for chunk in chat_session.send_message(prompt_text, stream=True):
            text = getattr(chunk, "text", "") or ""
            for ch in text:
                if not first_char_written:
                    status.empty()           # ลบสถานะทันทีเมื่อเริ่มพิมพ์
                    first_char_written = True
                full_text += ch
                placeholder.markdown(full_text)  # ใช้ markdown ให้จัดรูปสวย
                time.sleep(typing_delay)
        status.empty()
    except Exception as e:
        status.empty()
        placeholder.markdown(f"> [ขออภัย] เกิดข้อผิดพลาดระหว่างสตรีมคำตอบ: `{e}`")
    return full_text

# =========================
# 💬 Chat input & response
# =========================
prompt = st.chat_input("พิมพ์คำถามของคุณที่นี่...")
if prompt:
    # ฝั่งผู้ใช้
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # เตรียมประวัติ + สร้าง chat session
    history_payload = build_history_for_gemini(st.session_state.messages[:-1])  # ไม่รวม prompt ล่าสุดซ้ำ
    chat_session = model.start_chat(history=history_payload)

    # ฝั่งผู้ช่วย — ใช้ไอคอนบอทสีเขียวถ้ามี
    with st.chat_message("assistant", avatar=assistant_avatar):
        normalized = prompt.strip().lower()

        if normalized == "history":
            history_text = "\n".join(
                [f"{m['role'].capitalize()}: {m['content']}" for m in st.session_state.messages]
            )
            # ใช้โมเดลสรุปข้อความให้สวย แล้วแสดงด้วย typing effect
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

        elif normalized.startswith("add") or normalized.endswith("add"):
            # ตอบสั้น ๆ ด้วย typing effect เช่นกัน
            text = "ขอบคุณสำหรับคำแนะนำค่ะ"
            ph = st.empty()
            reply = ""
            for ch in text:
                reply += ch
                ph.markdown(reply)
                time.sleep(0.004)

        else:
            # ตอบหลัก: stream + typing effect
            reply = stream_typing_response(chat_session, prompt_text=prompt, typing_delay=0.004)

    # เก็บลงประวัติ (assistant)
    st.session_state.messages.append({"role": "assistant", "content": reply})
