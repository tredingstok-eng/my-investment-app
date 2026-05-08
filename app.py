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
st.markdown("<style> * { direction: rtl; text-align: right; } </style>", unsafe_allow_html=True)

# זיכרון מערכת
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72
if 'df' not in st.session_state: st.session_state.df = None
if 'auth' not in st.session_state: st.session_state.auth = False

def get_ibkr_nav():
    try:
        # שליחת בקשה עם מזהה זמן כדי למנוע Cache
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3&nc={time.time()}", timeout=15)
        root = ET.fromstring(r.content)
        if root.find("Status").text == "Success":
            url, code = root.find('Url').text, root.find('ReferenceCode').text
            time.sleep(10)
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
            d_root = ET.fromstring(res.content)
            # חיפוש הערך הכי גבוה בדו"ח
            vals = [float(el.get("total")) for el in d_root.findall(".//EquitySummaryByReportDateInBase") if el.get("total")]
            if vals: return max(vals)
    except: pass
    return None

def refresh_data():
    # רענון גוגל שיטס
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        for col in df.columns[2:]:
            df[col] = df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = df
    except: pass
    
    # ניסיון רענון אוטומטי מאינטראקטיב
    new_nav = get_ibkr_nav()
    if new_nav:
        st.session_state.total_nav = new_nav

if st.session_state.df is None: refresh_data()

# --- כניסה ---
if not st.session_state.auth:
    st.title("RC Capital")
    pin = st.text_input("PIN", type="password")
    if st.button("כניסה"):
        if pin == "0000": st.session_state.auth, st.session_state.role = True, "admin"
        elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
            st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
        st.rerun()
else:
    # סרגל צד
    with st.sidebar:
        st.write(f"שווי תיק נוכחי: **${st.session_state.total_nav:,.2f}**")
        if st.button("🔄 רענון אוטומטי"):
            refresh_data()
            st.rerun()
            
        # פונקציית "עקיפה ידנית" למנהל
        if st.session_state.role == "admin":
            st.write("---")
            st.write("עדכון ידני (Admin):")
            manual_nav = st.number_input("הזן שווי תיק ידני", value=st.session_state.total_nav)
            if st.button("עדכן לכולם"):
                st.session_state.total_nav = manual_nav
                st.success("עודכן!")
                st.rerun()
        
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    # תצוגת משתמש
    if st.session_state.role == "user":
        user = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share = user.iloc[0], user.iloc[2], user.iloc[3]
        
        # החישוב תמיד מתבסס על ה-total_nav שמופיע בסיידבר
        u_gross = st.session_state.total_nav * (share / 100.0)
        profit = u_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        u_net = u_gross - tax

        st.header(f"שלום, {name}")
        st.metric("היתרה שלך נטו", f"${u_net:,.2f}", delta=f"{u_net-inv:,.2f}")
        
        fig = go.Figure(go.Scatter(x=["הפקדה", "נוכחי"], y=[inv, u_net], mode='lines+markers+text', text=[f"${inv:,.0f}", f"${u_net:,.0f}"], textposition="top center"))
        st.plotly_chart(fig, use_container_width=True)
