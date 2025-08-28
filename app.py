import os
import google.generativeai as genai
import pandas as pd
import streamlit as st
import docx  # สำหรับอ่านไฟล์ .docx
from PyPDF2 import PdfReader  # สำหรับอ่านไฟล์ .pdf
# ไม่จำเป็นต้องใช้ BytesIO เมื่ออ่านไฟล์โดยตรงจาก disk
# from io import BytesIO 
from prompt import PROMPT_FTE 
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# 🔐 ตั้งค่า API Key จาก st.secrets
# ตรวจสอบว่ามีคีย์ 'GEMINI_APIKEY' ใน st.secrets หรือไม่
if "GEMINI_APIKEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_APIKEY"])
else:
    st.error("ไม่พบ GEMINI_APIKEY ในไฟล์ .streamlit/secrets.toml โปรดตรวจสอบการตั้งค่า.")
    st.stop() # หยุดการทำงานของแอปหากไม่มี API Key

# ⚙️ การตั้งค่า Model
generation_config = {
    "temperature": 0.1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 1024,
    "response_mime_type": "text/plain",
}

# 🔐 ตั้งค่าความปลอดภัยของเนื้อหา
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# 🔍 เลือกโมเดล Gemini
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    safety_settings=SAFETY_SETTINGS,
    generation_config=generation_config,
    system_instruction=PROMPT_FTE,
)

# 🔁 ฟังก์ชันล้างแชท
def clear_history():
    st.session_state["previous_messages"] = st.session_state["messages"].copy()
    st.session_state["messages"] = [
        {"role": "model", "content": "ประวัติการเเชทของท่าน"}
    ]
    # รีเซ็ตสถานะการโหลดไฟล์เมื่อล้างประวัติ
    st.session_state["excel_status"] = "ยังไม่ได้โหลด"
    st.session_state["word_status"] = "ยังไม่ได้โหลด"
    st.session_state["pdf_status"] = "ยังไม่ได้โหลด"
    st.rerun()

# ฟังก์ชันเรียกคืนประวัติแชท
def restore_history():
    if "previous_messages" in st.session_state and st.session_state["previous_messages"]:
        st.session_state["messages"] = st.session_state["previous_messages"].copy()
    else:
        st.warning("ไม่พบประวัติที่สามารถเรียกคืนได้")
    st.rerun()

# *** ฟังก์ชันใหม่: อ่านข้อความจากไฟล์ .docx (รับ path แทน file object) ***
def extract_text_from_docx(docx_path):
    try:
        doc = docx.Document(docx_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return "\n".join(full_text)
    except Exception as e:
        st.error(f"Error reading Word file '{docx_path}': {e}")
        return ""

# *** ฟังก์ชันใหม่: อ่านข้อความจากไฟล์ .pdf (รับ path แทน file object) ***
def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        st.error(f"Error reading PDF file '{pdf_path}': {e}")
        return ""

# 🔧 Sidebar: ปุ่ม Clear และ Restore เท่านั้น (ไม่มี File Uploader แล้ว)
with st.sidebar:
    st.header("การจัดการแชท")
    if st.button("🧹 Clear History"):
        clear_history()
    if st.button("🔄 Restore Last History"):
        restore_history()

    st.markdown("---")
    st.header("สถานะการโหลดไฟล์ข้อมูล")
    # *** แสดงสถานะการโหลดไฟล์ใน Sidebar ***
    st.info(f"Excel ({st.session_state.get('excel_file_name', 'N/A')}): {st.session_state.get('excel_status', 'ยังไม่ได้โหลด')}")
    st.info(f"Word ({st.session_state.get('word_file_name', 'N/A')}): {st.session_state.get('word_status', 'ยังไม่ได้โหลด')}")
    st.info(f"PDF ({st.session_state.get('pdf_file_name', 'N/A')}): {st.session_state.get('pdf_status', 'ยังไม่ได้โหลด')}")


# 🧾 ชื่อแอปบนหน้า
st.title("💬 Welcome to Faculty of Technical Education, KMUTNB")

# 🔃 เริ่มต้น session state ถ้ายังไม่มี
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "model",
            "content": "ท่านสนใจสอบถามข้อมูลเกี่ยวกับคณะครุศาสตร์อุตสาหกรรม มจพ. ด้านใดคะ",
        }
    ]
if "previous_messages" not in st.session_state:
    st.session_state["previous_messages"] = []

# *** เพิ่ม: เริ่มต้นสถานะการโหลดไฟล์ใน session_state ถ้ายังไม่มี ***
if "excel_status" not in st.session_state:
    st.session_state["excel_status"] = "กำลังตรวจสอบ..."
if "word_status" not in st.session_state:
    st.session_state["word_status"] = "กำลังตรวจสอบ..."
if "pdf_status" not in st.session_state:
    st.session_state["pdf_status"] = "กำลังตรวจสอบ..."
if "excel_file_name" not in st.session_state:
    st.session_state["excel_file_name"] = "FTE-DATASET.xlsx"
if "word_file_name" not in st.session_state:
    st.session_state["word_file_name"] = "Data Set chatbotfte.docx"
if "pdf_file_name" not in st.session_state:
    st.session_state["pdf_file_name"] = "Data Set chatbotfte.pdf"

# 📂 โหลดและประมวลผลไฟล์ข้อมูลจากโฟลเดอร์เดียวกัน
all_file_content = ""

# กำหนดชื่อไฟล์ Excel, Word, PDF ที่คาดว่าจะอยู่ในโฟลเดอร์เดียวกันกับ app.py
excel_file_name = st.session_state["excel_file_name"]
word_file_name = st.session_state["word_file_name"] 
pdf_file_name = st.session_state["pdf_file_name"]   

# โหลดไฟล์ Excel
if os.path.exists(excel_file_name):
    try:
        df = pd.read_excel(excel_file_name)
        all_file_content += "\nข้อมูลจากไฟล์ Excel:\n" + df.to_string(index=False)
        st.session_state["excel_status"] = f"โหลดสำเร็จ ({len(df)} แถว)"
        # st.success(f"โหลดไฟล์ Excel '{excel_file_name}' สำเร็จ.") # ลบข้อความนี้ออกเพื่อย้ายสถานะไป Sidebar
    except Exception as e:
        st.session_state["excel_status"] = f"ข้อผิดพลาด: {e}"
        st.error(f"Error reading Excel file '{excel_file_name}': {e}")
else:
    st.session_state["excel_status"] = "ไม่พบไฟล์"
    st.warning(f"ไม่พบไฟล์ Excel '{excel_file_name}' ใน GitHub repository โปรดตรวจสอบ.")

# โหลดไฟล์ Word
if os.path.exists(word_file_name):
    word_text = extract_text_from_docx(word_file_name)
    if word_text:
        all_file_content += "\nข้อมูลจากไฟล์ Word:\n" + word_text
        st.session_state["word_status"] = f"โหลดสำเร็จ ({len(word_text.splitlines())} บรรทัด)"
        # st.success(f"โหลดและอ่านไฟล์ Word '{word_file_name}' สำเร็จ.") # ลบข้อความนี้ออก
    else:
        st.session_state["word_status"] = "ไฟล์ว่างเปล่า/อ่านไม่ได้"
else:
    st.session_state["word_status"] = "ไม่พบไฟล์"
    st.warning(f"ไม่พบไฟล์ Word '{word_file_name}' ใน GitHub repository โปรดตรวจสอบชื่อและตำแหน่ง.")

# โหลดไฟล์ PDF
if os.path.exists(pdf_file_name):
    pdf_text = extract_text_from_pdf(pdf_file_name)
    if pdf_text:
        all_file_content += "\nข้อมูลจากไฟล์ PDF:\n" + pdf_text
        st.session_state["pdf_status"] = f"โหลดสำเร็จ ({len(pdf_text.splitlines())} บรรทัด)"
        # st.success(f"โหลดและอ่านไฟล์ PDF '{pdf_file_name}' สำเร็จ.") # ลบข้อความนี้ออก
    else:
        st.session_state["pdf_status"] = "ไฟล์ว่างเปล่า/อ่านไม่ได้"
else:
    st.session_state["pdf_status"] = "ไม่พบไฟล์"
    st.warning(f"ไม่พบไฟล์ PDF '{pdf_file_name}' ใน GitHub repository โปรดตรวจสอบชื่อและตำแหน่ง.")

# 💬 แสดงข้อความสนทนาเดิม
for msg in st.session_state["messages"]:
    st.chat_message(msg["role"]).write(msg["content"])

# 💡 ถ้ามี prompt ใหม่เข้ามา
if prompt := st.chat_input():
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    def generate_response():
        if prompt.strip().lower() == "history":
            history_text = "\n".join(
                [f"{msg['role'].capitalize()}: {msg['content']}" for msg in st.session_state["messages"]]
            )
            st.chat_message("model").write(f"📜 ประวัติการสนทนา:\n\n{history_text}")
            st.session_state["messages"].append({"role": "model", "content": f"📜 ประวัติการสนทนา:\n\n{history_text}"})
        elif prompt.lower().startswith("add") or prompt.lower().endswith("add"):
            st.chat_message("model").write("ขอบคุณสำหรับคำแนะนำค่ะ")
            st.session_state["messages"].append({"role": "model", "content": "ขอบคุณสำหรับคำแนะนำค่ะ"})
        else:
            history = [
                {"role": msg["role"], "parts": [{"text": msg["content"]}]}
                for msg in st.session_state["messages"]
            ]
            # แทรกเนื้อหาไฟล์ทั้งหมด (Excel, Word, PDF) เป็นบริบทเพิ่มเติมให้กับโมเดล
            if all_file_content:
                history.insert(0, {"role": "user", "parts": [{"text": "ข้อมูลอ้างอิง:\n" + all_file_content}]})
            
            chat_session = model.start_chat(history=history)
            response = chat_session.send_message(prompt)
            st.session_state["messages"].append({"role": "model", "content": response.text})
            st.chat_message("model").write(response.text)

    generate_response()
