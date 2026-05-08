import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", layout="wide")

# עיצוב RTL
st.markdown("<style> * { direction: rtl; text-align: right; } .stMetric { background-color: #0d1117; border-radius: 10px; padding: 10px; border: 1px solid #30363d; } </style>", unsafe_allow_html=True)

def get_live_nav():
    """משיכת השווי הכולל האמיתי מהדו"ח"""
    try:
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        if root.find("Status").text == "Success":
            url, code = root.find('Url').text, root.find('ReferenceCode').text
            time.sleep(12) 
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
            d_root = ET.fromstring(res.content)
            
            # סריקה אגרסיבית של כל שדות השווי - לוקחים את המקסימום כדי למנוע טעות של יתרת מזומן
            nav_elements = d_root.findall(".//EquitySummaryByReportDateInBase")
            vals = [float(el.get("total")) for el in nav_elements if el.get("total")]
            if vals:
                return max(vals)
        return None
    except: return None

# ניהול מצב (State)
if 'auth' not in st.session_state: st.session_state.auth = False
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72
if 'df' not in st.session_state: st.session_state.df = None

def run_refresh():
    # 1. רענון גוגל שיטס
    try:
        new_df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        for col in new_df.columns[2:]:
            new_df[col] = new_df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = new_df
    except: pass
    
    # 2. רענון אינטראקטיב
    val = get_live_nav()
    if val and val > 1000:
        st.session_state.total_nav = val

if st.session_state.df is None:
    run_refresh()

# --- ממשק ---
if not st.session_state.auth:
    st.title("RC Capital")
    pin = st.text_input("הכנס קוד PIN", type="password")
    if st.button("כניסה"):
        if pin == "0000": st.session_state.auth, st.session_state.role = True, "admin"
        elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
            st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
        st.rerun()
else:
    with st.sidebar:
        if st.button("🔄 רענון נתונים"):
            with st.spinner("מושך נתונים..."): run_refresh()
            st.rerun()
        st.write(f"שווי תיק ברוקר: **${st.session_state.total_nav:,.2f}**")
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    if st.session_state.role == "user":
        user = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share = user.iloc[0], user.iloc[2], user.iloc[3]
        
        # חישוב שנגזר *רק* מה-total_nav שמופיע בסיידבר
        u_gross = st.session_state.total_nav * (share / 100.0)
        profit = u_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        u_net = u_gross - tax

        st.title(f"שלום, {name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${u_net:,.2f}")
        c2.metric("רווח/הפסד", f"${(u_net-inv):,.2f}", delta=f"{((u_net-inv)/inv*100):.2f}%")
        c3.metric("נתח בתיק", f"{share}%")

        # גרף
        fig = go.Figure(go.Scatter(x=["הפקדה", "נוכחי"], y=[inv, u_net], mode='lines+markers+text', 
                                   text=[f"${inv:,.0f}", f"${u_net:,.0f}"], textposition="top center",
                                   line=dict(color='#d4af37', width=4)))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
