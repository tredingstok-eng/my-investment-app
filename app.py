import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ליבה (מעודכנות לפי התמונות שלך) ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", layout="wide")

# עיצוב RTL וסטייל
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    </style>
    """, unsafe_allow_html=True)

def fetch_ibkr_live():
    """משיכת הנתון המדויק מהשדה שראינו ב-XML"""
    try:
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        if root.find("Status").text == "Success":
            url, code = root.find('Url').text, root.find('ReferenceCode').text
            time.sleep(12) # זמן ייצור הדו"ח
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
            
            # סריקה של השדה שזיהינו ב-Debug
            if b"EquitySummaryByReportDateInBase" in res.content:
                d_root = ET.fromstring(res.content)
                elements = d_root.findall(".//EquitySummaryByReportDateInBase")
                for el in elements:
                    val = el.get("total")
                    if val and float(val) > 1000:
                        return float(val)
        return None
    except: return None

# ניהול משתני מערכת
if 'auth' not in st.session_state: st.session_state.auth = False
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72
if 'df' not in st.session_state: st.session_state.df = None

def refresh_data():
    # גוגל שיטס - ניקוי וטעינה
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        for col in df.columns[2:]:
            df[col] = df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = df
    except: pass
    
    # אינטראקטיב - עדכון היתרה הכוללת
    new_nav = fetch_ibkr_live()
    if new_nav:
        st.session_state.total_nav = new_nav

if st.session_state.df is None:
    refresh_all = refresh_data()

# --- מסך כניסה ---
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.title("RC Capital")
        pin = st.text_input("PIN", type="password")
        if st.button("כניסה"):
            if pin == "0000": 
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("PIN שגוי")
else:
    # --- דאשבורד ---
    with st.sidebar:
        if st.button("🔄 רענון נתונים"):
            with st.spinner("מתחבר לבורסה..."):
                refresh_data()
            st.rerun()
        st.write("---")
        st.write("שווי תיק ברוקר:")
        st.subheader(f"${st.session_state.total_nav:,.2f}")
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    if st.session_state.role == "user":
        user_row = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share = user_row.iloc[0], user_row.iloc[2], user_row.iloc[3]
        
        # החישוב הקריטי: משתמש אך ורק ב-total_nav מה-Session
        current_nav = st.session_state.total_nav
        u_gross = current_nav * (share / 100.0)
        profit = u_gross - inv
        
        # פטור ממס לרפאל, 25% לאחרים
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        u_net = u_gross - tax

        st.title(f"שלום, {name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${u_net:,.2f}")
        c2.metric("רווח/הפסד", f"${(u_net-inv):,.2f}", delta=f"{((u_net-inv)/inv*100):.2f}%")
        c3.metric("נתח בתיק", f"{share}%")

        fig = go.Figure(go.Scatter(x=["הפקדה", "נוכחי"], y=[inv, u_net], mode='lines+markers+text', 
                                   text=[f"${inv:,.0f}", f"${u_net:,.0f}"], textposition="top center",
                                   line=dict(color='#d4af37', width=4)))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350)
        st.plotly_chart(fig, use_container_width=True)
