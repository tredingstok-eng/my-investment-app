import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
import random

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital Live", layout="wide")

def get_real_live_nav():
    """משיכת נתונים עם פקודה להביא קובץ חדש בלבד"""
    try:
        # הוספת מספר אקראי לבקשה כדי למנוע קבלת קובץ ישן מהזיכרון
        t_stamp = int(time.time())
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3&t_stamp={t_stamp}", timeout=15)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            url, code = root.find('Url').text, root.find('ReferenceCode').text
            # המתנה שהשרת יסיים לעבד את הנתון החדש
            time.sleep(12)
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
            d_root = ET.fromstring(res.content)
            
            # חיפוש הערך הכי מעודכן בדו"ח
            nav_elements = d_root.findall(".//EquitySummaryByReportDateInBase")
            vals = [float(el.get("total")) for el in nav_elements if el.get("total")]
            if vals:
                return max(vals)
        return None
    except: return None

# ניהול מצב האפליקציה
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72
if 'df' not in st.session_state: st.session_state.df = None

def full_refresh():
    # רענון גוגל שיטס
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        for col in df.columns[2:]:
            df[col] = df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = df
    except: pass
    
    # רענון אינטראקטיב
    new_val = get_real_live_nav()
    if new_val:
        st.session_state.total_nav = new_val

# טעינה ראשונית
if st.session_state.df is None: full_refresh()

# --- ממשק ---
st.markdown("<style> * { direction: rtl; text-align: right; } </style>", unsafe_allow_html=True)

with st.sidebar:
    if st.button("🔄 רענון נתונים מהבורסה"):
        with st.spinner("מושך נתונים עדכניים..."):
            full_refresh()
        st.rerun()
    st.write(f"שווי תיק כולל: **${st.session_state.total_nav:,.2f}**")

# דף המשתמש (למשל קובי)
if st.session_state.df is not None:
    # כאן נניח שאנחנו בדף של קובי (לפי ה-PIN שלו)
    # נשתמש בנתונים מה-DataFrame שנטען
    st.title("מרכז השקעות")
    
    # החישוב שאתה מחפש:
    total = st.session_state.total_nav
    share = 7.81 # האחוז של קובי
    kobi_value = total * (share / 100)
    
    st.metric("החלק שלך בתיק", f"${kobi_value:,.2f}")
    st.write(f"מבוסס על שווי תיק כולל של: ${total:,.2f}")
