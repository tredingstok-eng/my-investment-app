import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="Debug Mode", layout="wide")
st.markdown("<style> * { direction: rtl; text-align: right; } </style>", unsafe_allow_html=True)

# משתנה הזיכרון
if 'total_nav' not in st.session_state: 
    st.session_state.total_nav = 6131.72 # ערך התחלה

def debug_fetch():
    """פונקציה שמדפיסה הכל כדי שנבין למה זה לא זז"""
    try:
        st.write("📡 שולח בקשה לאינטראקטיב...")
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3")
        
        # הדפסת תגובה ראשונית
        if "ErrorCode" in r.text:
            st.error(f"שגיאה מאינטראקטיב: {r.text}")
            return None
            
        root = ET.fromstring(r.content)
        if root.find("Status").text == "Success":
            code = root.find('ReferenceCode').text
            url = root.find('Url').text
            st.info(f"קוד דו"ח התקבל: {code}. מחכה 10 שניות לייצור הקובץ...")
            
            time.sleep(10)
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}")
            
            if b"NetAssetValue" in res.content:
                d_root = ET.fromstring(res.content)
                navs = [float(n.get("total")) for n in d_root.findall(".//NetAssetValue") if n.get("total")]
                if navs:
                    new_val = max(navs)
                    st.success(f"הצלחתי! המספר החדש הוא: ${new_val:,.2f}")
                    return new_val
                else:
                    st.warning("הקובץ הגיע אבל הוא ריק מנתוני NAV. בדוק את הגדרות ה-Query ב-IBKR.")
            else:
                st.error("התקבל קובץ לא תקין (לא XML של נתונים).")
        else:
            st.error(f"סטטוס נכשל: {r.text}")
    except Exception as e:
        st.error(f"שגיאה טכנית: {str(e)}")
    return None

# ממשק פשוט
st.title("בדיקת חיבור RC Capital")

if st.button("לחץ כאן לבדיקת נתונים בזמן אמת"):
    val = debug_fetch()
    if val:
        st.session_state.total_nav = val
    st.rerun()

st.write("---")
st.header(f"המספר כרגע במערכת: ${st.session_state.total_nav:,.2f}")

# טעינת גוגל שיטס רק לראות שזה עובד
if st.checkbox("הצג נתונים מגוגל שיטס"):
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        st.dataframe(df)
    except:
        st.error("לא מצליח לקרוא את גוגל שיטס")
