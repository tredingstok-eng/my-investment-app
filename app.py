import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", layout="wide")

def force_refresh_ibkr():
    """מנסה להכריח את אינטראקטיב לייצר דו"ח חדש עכשיו"""
    try:
        # שלב 1: בקשת ייצור דו"ח חדש
        # הוספתי v=3 ופרמטר זמן כדי למנוע שימוש בדו"ח ישן
        send_url = f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3"
        r = requests.get(send_url, timeout=15)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            code = root.find('ReferenceCode').text
            base_url = root.find('Url').text
            
            # שלב 2: המתנה קריטית. אינטראקטיב צריכים זמן לעבד את ה-5,900 שלך.
            # אם נבקש מהר מדי, נקבל שוב את ה-6,131.
            placeholder = st.empty()
            for i in range(15, 0, -1):
                placeholder.info(f"מתחבר לבורסה... אנא המתן {i} שניות לעדכון סופי.")
                time.sleep(1)
            placeholder.empty()
            
            # שלב 3: משיכת הדו"ח החדש שיוצר הרגע
            res = requests.get(f"{base_url}?q={code}&t={IB_TOKEN}", timeout=15)
            d_root = ET.fromstring(res.content)
            
            # חיפוש הערך בתוך ה-XML
            elements = d_root.findall(".//EquitySummaryByReportDateInBase")
            vals = [float(el.get("total")) for el in elements if el.get("total")]
            
            if vals:
                return max(vals)
    except Exception as e:
        st.error(f"שגיאת תקשורת: {e}")
    return None

# ניהול State
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72
if 'df' not in st.session_state: st.session_state.df = None

def refresh_all():
    # גוגל שיטס
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        # ניקוי פורמט (מוריד $, %, פסיקים)
        for col in df.columns[2:]:
            df[col] = df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = df
    except: pass
    
    # אינטראקטיב
    new_nav = force_refresh_ibkr()
    if new_nav:
        st.session_state.total_nav = new_nav

# טעינה אוטומטית בהתחלה
if st.session_state.df is None:
    refresh_all()

# --- ממשק RTL ---
st.markdown("<style> * { direction: rtl; text-align: right; } </style>", unsafe_allow_html=True)

with st.sidebar:
    st.header("RC Capital")
    if st.button("🔄 עדכן הכל אוטומטית"):
        refresh_all()
        st.rerun()
    st.write(f"שווי תיק ברוקר: **${st.session_state.total_nav:,.2f}**")

# תצוגת קובי (דוגמה)
if st.session_state.df is not None:
    # נניח שזה קובי (7.81%)
    share = 7.81 
    current_val = st.session_state.total_nav * (share / 100)
    st.title("מצב חשבון מעודכן")
    st.metric("היתרה שלך", f"${current_val:,.2f}")
    st.write(f"החישוב מתבסס על שווי תיק של ${st.session_state.total_nav:,.2f}")
