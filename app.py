import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import pytz

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1489351"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", layout="wide")

# עיצוב שחור נקי
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    div[data-testid="stMetricValue"] { color: white !important; }
    </style>
    """, unsafe_allow_html=True)

def fetch_ibkr_data():
    """מנגנון משיכה עקשן - לא חוזר עם 0 לעולם"""
    try:
        # בקשת הדו"ח
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            url = root.find('Url').text
            code = root.find('ReferenceCode').text
            
            # ניסיונות משיכה עם המתנה
            for i in range(6): # ננסה 6 פעמים (חצי דקה סה"כ)
                time.sleep(5)
                resp = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
                
                if b"NetAssetValue" in resp.content:
                    d_root = ET.fromstring(resp.content)
                    # מחפש את שורת ה-NAV הכוללת
                    nav_items = d_root.findall(".//NetAssetValue")
                    for item in nav_items:
                        val = item.get("total")
                        if val and float(val) > 1000: # אם זה פחות מ-1000$, זה כנראה טעות בטעינה
                            return float(val)
        return None
    except:
        return None

# ניהול הזיכרון של האפליקציה
if 'auth' not in st.session_state: st.session_state.auth = False
if 'nav' not in st.session_state: st.session_state.nav = 6131.72 # ערך מגן ראשוני
if 'df' not in st.session_state: st.session_state.df = None

def full_refresh():
    # רענון גוגל
    try:
        st.session_state.df = pd.read_csv(f"{SHEET_URL}&cache={time.time()}")
    except: pass
    
    # רענון אינטראקטיב
    new_val = fetch_ibkr_data()
    if new_val: # עדכון רק אם המספר תקין!
        st.session_state.nav = new_val

# טעינה ראשונית
if st.session_state.df is None:
    full_refresh()

# --- ממשק משתמש ---
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("<br><br><h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("PIN", type="password")
        if st.button("כניסה"):
            if pin == "0000": 
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("PIN לא תקין")
else:
    with st.sidebar:
        st.header("ניהול חשבון")
        if st.button("🔄 רענון נתונים חי"):
            with st.spinner("מושך נתונים מאינטראקטיב..."):
                full_refresh()
            st.rerun()
        
        st.write("---")
        st.write("שווי תיק ברוקר:")
        st.subheader(f"${st.session_state.nav:,.2f}")
        
        if st.button("🚪 התנתק"):
            st.session_state.auth = False
            st.rerun()

    if st.session_state.role == "user":
        user = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name = user.iloc[0]
        inv = float(str(user.iloc[2]).replace('$', '').replace(',', ''))
        share = float(str(user.iloc[3]).replace('%', ''))
        
        # חישוב יחסי לשווי התיק הנוכחי
        current_total = st.session_state.nav
        my_gross = current_total * (share / 100.0)
        
        # רווח נקי (ללא מס לרפאל)
        profit = my_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        my_net = my_gross - tax

        st.title(f"שלום, {name}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${my_net:,.2f}")
        c2.metric("רווח/הפסד", f"${(my_net-inv):,.2f}", delta=f"{((my_net-inv)/inv*100):.2f}%")
        c3.metric("אחוז בקרן", f"{share}%")

        # גרף
        fig = go.Figure(go.Scatter(
            x=["הפקדה", "מצב נוכחי"], y=[inv, my_net],
            mode='lines+markers+text', text=[f"${inv:,.0f}", f"${my_net:,.0f}"],
            textposition="top center", line=dict(color='#d4af37', width=4)
        ))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400)
        st.plotly_chart(fig, use_container_width=True)
