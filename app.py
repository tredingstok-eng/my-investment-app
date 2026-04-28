import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime, timedelta

# --- הגדרות ליבה ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1489351"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

# --- עיצוב ממשק Elite ---
st.set_page_config(page_title="RC Capital", page_icon="🏦", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; }
    .main { background-color: #050505; color: white; }
    
    /* כפתור התנתקות קטן בצד */
    .stButton>button { 
        background-color: transparent; 
        color: #8b949e; 
        border: 1px solid #30363d; 
        border-radius: 20px;
        padding: 2px 15px;
        font-size: 12px;
    }
    .stButton>button:hover { color: #ff4b4b; border-color: #ff4b4b; }

    /* כרטיסי מידע */
    .metric-card {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 15px;
        padding: 25px;
        text-align: center;
    }
    .metric-val { font-size: 35px; font-weight: 700; color: #d4af37; margin-bottom: 5px; }
    .metric-lbl { font-size: 14px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }

    /* הסתרת אלמנטים של Streamlit */
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {padding-top: 2rem;}
    .modebar { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

# --- פונקציות ---
def safe_n(v):
    try:
        if pd.isna(v): return 0.0
        return float(str(v).replace('$', '').replace('%', '').replace(',', '').strip())
    except: return 0.0

@st.cache_data(ttl=60)
def load_all():
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

# --- לוגיקה ---
df, total_nav = load_all()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    # דף כניסה נקי
    _, col2, _ = st.columns([1, 1, 1])
    with col2:
        st.markdown("<div style='height:150px;'></div>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center; color:#d4af37;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("PIN", type="password", label_visibility="collapsed")
        if st.button("LOGIN"):
            if pin == "0000":
                st.session_state.logged_in, st.session_state.role = True, "admin"
                st.rerun()
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.logged_in, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("Access Denied")
else:
    # כפתור התנתקות קטן בפינה
    top_left, top_right = st.columns([9, 1])
    with top_right:
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()

    if st.session_state.role == "admin":
        st.title("Admin Dashboard")
        st.table(df.iloc[:, [0, 2, 3]])
    else:
        user = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share, acts = user.iloc[0], safe_n(user.iloc[2]), safe_n(user.iloc[3]), safe_n(user.iloc[4])
        
        # חישובי מס ועמלות
        gross = total_nav * (share / 100.0)
        broker_costs = (acts + 1) * 1.0
        profit_raw = gross - inv - broker_costs
        
        tax = profit_raw * 0.25 if profit_raw > 0 and name != "רפאל כהן" else 0
        success_fee = (profit_raw - tax) * 0.20 if profit_raw > 0 and name != "רפאל כהן" else 0
        net = gross - tax - success_fee

        st.markdown(f"<h3>שלום, {name}</h3>", unsafe_allow_html=True)
        
        # כרטיסי מידע רחבים
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"<div class='metric-card'><div class='metric-lbl'>יתרה נטו</div><div class='metric-val'>${net:,.2f}</div></div>", unsafe_allow_html=True)
        with c2:
            p_net = net - inv
            color = "#00ff88" if p_net >= 0 else "#ff4b4b"
            st.markdown(f"<div class='metric-card'><div class='metric-lbl'>רווח/הפסד</div><div class='metric-val' style='color:{color}'>${p_net:,.2f}</div></div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='metric-card'><div class='metric-lbl'>תשואה</div><div class='metric-val'>{(p_net/inv*100):.2f}%</div></div>", unsafe_allow_html=True)

        st.write("<br>", unsafe_allow_html=True)

        # גרף הון מרכזי
        st.subheader("ביצועי תיק")
        dates = [datetime.now() - timedelta(days=30), datetime.now()]
        points = [inv, net]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=points, mode='lines+markers',
            line=dict(color='#d4af37', width=5),
            fill='tozeroy', fillcolor='rgba(212, 175, 55, 0.05)',
            marker=dict(size=12, borderwidth=2, bordercolor='white')
        ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=10, b=0), height=400,
            xaxis=dict(showgrid=False, fixedrange=True),
            yaxis=dict(showgrid=True, gridcolor='#1c2128', side="right", fixedrange=True),
            dragmode=False
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # פירוט עמלות נקי למטה
        st.write("<br>---", unsafe_allow_html=True)
        st.subheader("שקיפות עמלות ומיסים")
        f1, f2, f3 = st.columns(3)
        f1.write(f"**מס רווח הון (25%):** ${tax:,.2f}")
        f2.write(f"**עמלת הצלחה (20%):** ${success_fee:,.2f}")
        f3.write(f"**עלויות ברוקר:** ${broker_costs:,.2f}")
