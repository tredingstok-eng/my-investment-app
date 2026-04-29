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

st.set_page_config(page_title="RC Capital", page_icon="🏦", layout="wide")

# --- עיצוב ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    #MainMenu, footer, header {visibility: hidden;}
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    .update-time { color: #8b949e; font-size: 14px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

def safe_float(v):
    try:
        if pd.isna(v): return 0.0
        return float(str(v).replace('$', '').replace('%', '').replace(',', '').strip())
    except: return 0.0

# פונקציה ללא Cache בכלל - תמיד מושכת מחדש
def get_fresh_data():
    try:
        # יצירת מפתח רנדומלי לחלוטין בכל הרצה כדי למנוע שמירת נתונים ישנים ע"י גוגל
        random_key = int(time.time())
        df = pd.read_csv(f"{SHEET_URL}&nocache={random_key}")
        
        # משיכת נתונים מ-IBKR
        nav = 6131.72
        try:
            r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=5)
            root = ET.fromstring(r.content)
            if root.find("Status").text == "Success":
                time.sleep(1)
                d_r = requests.get(f"{root.find('Url').text}?q={root.find('ReferenceCode').text}&t={IB_TOKEN}")
                nav_val = ET.fromstring(d_r.content).find(".//NetAssetValue")
                if nav_val is not None: nav = float(nav_val.get("total"))
        except: pass
        return df, nav
    except: return None, 6131.72

# טעינה ישירה ללא st.cache_data
df, total_nav = get_fresh_data()

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("<br><br><h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("PIN", type="password")
        if st.button("כניסה"):
            if pin == "0000": st.session_state.auth, st.session_state.role = True, "admin"
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
            st.rerun()
else:
    with st.sidebar:
        if st.button("Logout 🚪"):
            st.session_state.auth = False
            st.rerun()
        # כפתור רענון ידני לביטחון
        if st.button("רענן נתונים 🔄"):
            st.rerun()

    if st.session_state.role == "user":
        user_row = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share, acts = user_row.iloc[0], safe_float(user_row.iloc[2]), safe_float(user_row.iloc[3]), safe_float(user_row.iloc[4])
        
        gross = total_nav * (share / 100.0)
        profit_raw = gross - inv - ((acts + 1) * 1.0)
        tax = profit_raw * 0.25 if profit_raw > 0 and "רפאל" not in name else 0
        fee = (profit_raw - tax) * 0.20 if profit_raw > 0 and "רפאל" not in name else 0
        net = gross - tax - fee

        israel_tz = pytz.timezone('Asia/Jerusalem')
        now_israel = datetime.now(israel_tz).strftime('%H:%M:%S | %d/%m/%Y')

        st.title(f"שלום, {name}")
        st.markdown(f"<div class='update-time'>נתונים מעודכנים לזמן ישראל: {now_israel}</div>", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${net:,.2f}")
        c2.metric("רווח/הפסד", f"${(net-inv):,.2f}", delta=f"{((net-inv)/inv*100 if inv>0 else 0):.2f}%")
        c3.metric("נתח בתיק", f"{share}%")

        st.write("<br>", unsafe_allow_html=True)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=["הפקדה", "נוכחי"], y=[inv, net],
            mode='lines+markers',
            line=dict(color='#d4af37', width=4),
            fill='tozeroy', fillcolor='rgba(212, 175, 55, 0.1)'
        ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=10, b=0), height=300,
            xaxis=dict(fixedrange=True), yaxis=dict(side="right", fixedrange=True),
            dragmode=False
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.write("---")
        st.subheader("פירוט עלויות")
        f1, f2, f3 = st.columns(3)
        f1.write(f"**מס:** ${tax:,.2f}")
        f2.write(f"**עמלת הצלחה:** ${fee:,.2f}")
        f3.write(f"**עמלות ברוקר:** ${(acts+1)*1.0:,.2f}")
    else:
        st.title("ניהול מערכת")
        st.table(df)
