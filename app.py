import os
import google.generativeai as genai
import pandas as pd
import streamlit as st
from prompt import PROMPT_FTE # สมมติว่าไฟล์ prompt.py อยู่ในตำแหน่งเดียวกัน
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
    st.session_state["messages"] = [
        {"role": "model", "content": "ประวัติการเเชทของท่าน"}
    ]
    st.rerun()

# 🔧 Sidebar: ปุ่ม Clear เท่านั้น
with st.sidebar:
    if st.button("🧹 Clear History"):
        clear_history()

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

# 📂 โหลดไฟล์ Excel
# *** แก้ไข: ใช้ Relative Path (เส้นทางแบบเทียบเคียง) แทน Absolute Path ***
# ไฟล์ FTE-DATASET.xlsx ต้องอยู่ในโฟลเดอร์เดียวกันกับ app.py ใน GitHub repository
file_path = "FTE-DATASET.xlsx" 
try:
    df = pd.read_excel(file_path)
    file_content = df.to_string(index=False)
except Exception as e:
    st.error(f"Error reading file: {e}. โปรดตรวจสอบว่าไฟล์ Excel 'FTE-DATASET.xlsx' อยู่ใน GitHub repository ของคุณในโฟลเดอร์เดียวกับ app.py หรือไม่.")
    st.stop()

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
            # แทรกเนื้อหาไฟล์ Excel เป็นบริบทเพิ่มเติมให้กับโมเดล
            history.insert(0, {"role": "user", "parts": [{"text": "ข้อมูลอ้างอิงจากไฟล์ Excel:\n" + file_content}]})
            
            chat_session = model.start_chat(history=history)
            response = chat_session.send_message(prompt)
            st.session_state["messages"].append({"role": "model", "content": response.text})
            st.chat_message("model").write(response.text)

    generate_response()
