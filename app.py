import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1489351"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

# --- עיצוב דף ---
st.set_page_config(page_title="RC Capital", page_icon="💰", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; }
    .main { background-color: #0e1117; }
    /* כרטיסי נתונים */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.5);
    }
    .metric-label { color: #8b949e; font-size: 16px; margin-bottom: 10px; }
    .metric-value { color: #d4af37; font-size: 32px; font-weight: bold; }
    /* הסרת ה-Toolbar של Plotly */
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

def calc_all(name, inv, share, acts, total_nav):
    gross = total_nav * (share / 100.0)
    fees = (acts + 1) * 1.0
    profit = gross - inv - fees
    tax, mgt = (profit * 0.25, (profit * 0.75) * 0.20) if profit > 0 and name != "רפאל כהן" else (0, 0)
    net = gross - tax - mgt - (fees if name != "רפאל כהן" else 0)
    return {"net": net, "profit": net - inv, "perc": (net-inv)/inv*100 if inv>0 else 0}

# --- אפליקציה ---
df, total_nav = load_data()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
        st.title("🏦 כניסה ל-RC Capital")
        pin = st.text_input("הזן קוד זיהוי אישי:", type="password")
        if st.button("התחבר"):
            if pin == "0000":
                st.session_state.logged_in, st.session_state.admin = True, True
                st.rerun()
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.logged_in, st.session_state.admin, st.session_state.user_pin = True, False, str(pin)
                st.rerun()
            else: st.error("קוד שגוי")
        st.markdown("</div>", unsafe_allow_html=True)

else:
    # סרגל צד
    with st.sidebar:
        st.title("RC Capital")
        st.write(f"שווי תיק כולל: **${total_nav:,.2f}**")
        st.write("---")
        # בחירת תקופה
        time_period = st.radio("בחר תקופת תצוגה:", ["חודש", "רבעון", "שנה", "הכל"], index=3)
        if st.button("התנתק"):
            st.session_state.logged_in = False
            st.rerun()

    if st.session_state.admin:
        st.header("ניהול תיק השקעות")
        st.dataframe(df.iloc[:, [0, 2, 3]], use_container_width=True)
    else:
        user = df[df.iloc[:, 1].astype(str) == st.session_state.user_pin].iloc[0]
        name, inv, share, acts = user.iloc[0], safe_n(user.iloc[2]), safe_n(user.iloc[3]), safe_n(user.iloc[4])
        m = calc_all(name, inv, share, acts, total_nav)

        st.title(f"שלום, {name}")
        st.markdown("---")

        # כרטיסים נקיים
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>יתרה נטו (דולר)</div><div class='metric-value'>${m['net']:,.2f}</div></div>", unsafe_allow_html=True)
        with c2:
            color = "#00ff88" if m['profit'] >= 0 else "#ff4b4b"
            st.markdown(f"<div class='metric-card'><div class='metric-label'>רווח/הפסד נקי</div><div class='metric-value' style='color:{color}'>${m['profit']:,.2f}</div></div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='metric-card'><div class='metric-label'>אחוז תשואה</div><div class='metric-value'>{m['perc']:.2f}%</div></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # גרפים יציבים (ללא תזוזה)
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("גרף הון (בכסף)")
            fig_money = go.Figure(go.Bar(
                x=["הפקדה", "יתרה נוכחית"],
                y=[inv, m['net']],
                marker_color=['#30363d', '#d4af37'],
                text=[f"${inv:,.0f}", f"${m['net']:,.0f}"],
                textposition='auto',
            ))
            fig_money.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font_color="white", height=350, margin=dict(l=20, r=20, t=20, b=20),
                dragmode=False, # מבטל הזזה
                xaxis=dict(fixedrange=True), # מבטל Zoom
                yaxis=dict(fixedrange=True)
            )
            st.plotly_chart(fig_money, use_container_width=True, config={'displayModeBar': False})

        with col_g2:
            st.subheader("גרף ביצועים (באחוזים)")
            # גרף פאי פשוט שלא זז
            fig_perc = px.pie(
                values=[share, 100-share],
                names=["החלק שלך", "שאר התיק"],
                hole=0.5,
                color_discrete_sequence=['#d4af37', '#161b22']
            )
            fig_perc.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', font_color="white",
                height=350, showlegend=False,
                dragmode=False
            )
            st.plotly_chart(fig_perc, use_container_width=True, config={'displayModeBar': False})

        st.info(f"הנתונים מוצגים עבור תקופה: {time_period}")
