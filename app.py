import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime, timedelta
import numpy as np

# --- הגדרות ליבה ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1489351"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

# --- עיצוב דף (Clean Fintech Look) ---
st.set_page_config(page_title="RC Capital", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; }
    .main { background-color: #0b0e11; }
    .stMetric { background-color: #161b22; border-radius: 12px; padding: 15px; border: 1px solid #30363d; }
    /* הסתרת כל מה שמיותר */
    .modebar { display: none !important; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    .stButton>button { background-color: #1c2128; color: #adbac7; border: 1px solid #444c56; border-radius: 6px; }
    .stButton>button:active, .stButton>button:focus { border-color: #d4af37; color: #d4af37; }
    </style>
    """, unsafe_allow_html=True)

# --- פונקציות נתונים ---
def safe_n(v):
    try:
        if pd.isna(v): return 0.0
        return float(str(v).replace('$', '').replace('%', '').replace(',', '').strip())
    except: return 0.0

@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        nav = 6131.72
        try:
            r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=5)
            root = ET.fromstring(r.content)
            if root.find("Status").text == "Success":
                time.sleep(1)
                d_r = requests.get(f"{root.find('Url').text}?q={root.find('ReferenceCode').text}&t={IB_TOKEN}")
                nav = float(ET.fromstring(d_r.content).find(".//NetAssetValue").get("total"))
        except: pass
        return df, nav
    except: return None, 6131.72

def get_history_data(current_val, days=30):
    """ייצור נתונים היסטוריים מדומים לצורך הגרף (עד שיהיה בסיס נתונים)"""
    dates = [datetime.now() - timedelta(days=x) for x in range(days)]
    dates.reverse()
    # מייצר תנודה אקראית סביב הערך הנוכחי
    values = [current_val * (1 + np.random.uniform(-0.02, 0.02)) for _ in range(days-1)]
    values.append(current_val)
    return dates, values

# --- לוגיקה ---
df, total_nav = load_data()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<div style='text-align:center; padding-top:100px;'>", unsafe_allow_html=True)
        st.title("🏦 RC Capital")
        pin = st.text_input("קוד גישה:", type="password")
        if st.button("כניסה"):
            if pin == "0000":
                st.session_state.logged_in, st.session_state.admin = True, True
                st.rerun()
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.logged_in, st.session_state.admin, st.session_state.user_pin = True, False, str(pin)
                st.rerun()
            else: st.error("קוד לא מזוהה")
        st.markdown("</div>", unsafe_allow_html=True)
else:
    if st.sidebar.button("התנתק"):
        st.session_state.logged_in = False
        st.rerun()

    if st.session_state.admin:
        st.header("ניהול מערכת")
        st.dataframe(df)
    else:
        user = df[df.iloc[:, 1].astype(str) == st.session_state.user_pin].iloc[0]
        name, inv, share, acts = user.iloc[0], safe_n(user.iloc[2]), safe_n(user.iloc[3]), safe_n(user.iloc[4])
        
        # חישובי רווח
        gross = total_nav * (share / 100.0)
        profit = gross - inv - ((acts+1)*1.0)
        net = gross - (profit*0.25 if profit > 0 else 0) # חישוב מס בסיסי בתצוגה

        st.title(f"שלום, {name}")
        
        # מטריקות ראשיות
        c1, c2, c3 = st.columns(3)
        c1.metric("שווי נטו", f"${net:,.2f}")
        c2.metric("רווח/הפסד", f"${profit:,.2f}", delta=f"{(profit/inv*100):.2f}%")
        c3.metric("נתח בקרן", f"{share}%")

        st.markdown("---")
        
        # כפתורי בחירת זמן
        t_col1, t_col2 = st.columns([2, 1])
        with t_col1:
            period = st.radio("", ["יום", "שבוע", "חודש", "שנה", "MAX"], horizontal=True, label_visibility="collapsed")
        
        days_map = {"יום": 2, "שבוע": 7, "חודש": 30, "שנה": 365, "MAX": 500}
        dates, vals = get_history_data(net, days_map[period])

        # הגרף המרכזי - קווי ונקי
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=vals,
            mode='lines',
            line=dict(color='#d4af37', width=3),
            fill='tozeroy',
            fillcolor='rgba(212, 175, 55, 0.1)',
            hovertemplate='<b>שווי:</b> $%{y:,.2f}<extra></extra>'
        ))

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=10, b=0),
            height=400,
            xaxis=dict(showgrid=False, color='#444', fixedrange=True),
            yaxis=dict(showgrid=True, gridcolor='#1c2128', color='#444', side="right", fixedrange=True),
            dragmode=False
        )
        
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # גרף אחוזים (רווח מצטבר)
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("תשואה באחוזים")
        
        # המרה של הערכים לאחוזים יחסיים להפקדה
        perc_vals = [(v - inv) / inv * 100 for v in vals]
        
        fig_perc = go.Figure()
        fig_perc.add_trace(go.Scatter(
            x=dates, y=perc_vals,
            mode='lines',
            line=dict(color='#00ff88' if profit >= 0 else '#ff4b4b', width=2),
            hovertemplate='<b>תשואה:</b> %{y:.2f}%<extra></extra>'
        ))
        
        fig_perc.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=10, b=0),
            height=250,
            xaxis=dict(showgrid=False, visible=False, fixedrange=True),
            yaxis=dict(showgrid=True, gridcolor='#1c2128', side="right", fixedrange=True),
            dragmode=False
        )
        st.plotly_chart(fig_perc, use_container_width=True, config={'displayModeBar': False})
