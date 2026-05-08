import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 

st.set_page_config(page_title="IBKR Debugger", layout="wide")
st.markdown("<style> * { direction: rtl; text-align: right; } </style>", unsafe_allow_html=True)

# משתני זיכרון שלא נמחקים ברענון
if 'error_log' not in st.session_state: st.session_state.error_log = ""
if 'debug_status' not in st.session_state: st.session_state.debug_status = "מוכן לבדיקה"

def run_capture_debug():
    st.session_state.error_log = "" # איפוס לוג
    try:
        st.session_state.debug_status = "שולח בקשה ראשונה ל-IBKR..."
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        
        if r.status_code != 200:
            st.session_state.error_log = f"שגיאת שרת (HTTP {r.status_code}): {r.text}"
            return

        if "ErrorCode" in r.text:
            st.session_state.error_log = f"אינטראקטיב החזיר קוד שגיאה: {r.text}"
            return

        root = ET.fromstring(r.content)
        status = root.find("Status").text if root.find("Status") is not None else "Unknown"
        
        if status == "Success":
            code = root.find('ReferenceCode').text
            url = root.find('Url').text
            st.session_state.debug_status = f"הבקשה התקבלה (קוד {code}). מחכה לקובץ..."
            
            # בדיקה אם הקובץ מוכן
            time.sleep(12)
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
            
            if b"NetAssetValue" in res.content:
                st.session_state.debug_status = "הקובץ התקבל בהצלחה!"
                st.balloons()
            else:
                st.session_state.error_log = f"התקבל קובץ, אבל הוא לא מכיל נתוני NAV. תוכן: {res.text[:500]}"
        else:
            st.session_state.error_log = f"סטטוס לא תקין ב-XML: {r.text}"

    except Exception as e:
        st.session_state.error_log = f"שגיאת קוד (Crash): {str(e)}"

st.title("מערכת אבחון תקלות IBKR")

if st.button("הפעל בדיקה ותפוס שגיאה"):
    run_capture_debug()

st.write("---")

# הצגת סטטוס
st.subheader("סטטוס נוכחי:")
st.info(st.session_state.debug_status)

# הצגת שגיאה (אם קיימת - היא לא תיעלם!)
if st.session_state.error_log:
    st.subheader("⚠️ השגיאה שנתפסה:")
    st.error(st.session_state.error_log)
    st.warning("אם השגיאה היא 'ErrorCode: 1019', זה אומר שצריך לחכות 3 דקות בין לחיצה ללחיצה.")

st.write("---")
st.write("גרסת אבחון 1.1 - השגיאה תישאר על המסך עד ללחיצה הבאה.")
