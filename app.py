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

# --- עיצוב ממשק ---
st.set_page_config(page_title="RC Capital", page_icon="🏦", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #0b0e11; color: white; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* כרטיסי מידע */
    .metric-container {
        background-color: #161b22;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #30363d;
        text-align: center;
        margin-bottom: 10px;
    }
    .metric-val { font-size: 28px; font-weight: bold; color: #d4af37; }
    .metric-lbl { font-size: 14px; color: #8b949e; }
    
    /* עמלות - עיצוב עדין יותר */
    .fee-card {
        background-color: #0d1117;
        border-right: 4px solid #d4af37;
        padding: 10px 15px;
        margin: 5px 0;
    }
    
    .modebar { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

# --- מנוע נתונים ---
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

# --- לוגיקת כניסה ---
df, total_nav = load_all()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<div style='height:100px;'></div>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("קוד גישה:", type="password")
        if st.button("כניסה"):
            if pin == "0000":
                st.session_state.logged_in, st.session_state.role = True, "admin"
                st.rerun()
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.logged_in, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("קוד לא תקין")
else:
    # סרגל צד - כפתור התנתקות למטה
    with st.sidebar:
        st.markdown("### RC Capital Management")
        st.write("---")
        st.write(f"מעודכן ל: {datetime.now().strftime('%d/%m/%Y')}")
        st.markdown("<br>"*15, unsafe_allow_html=True) # דחיפה למטה
        if st.button("🚪 התנתק"):
            st.session_state.logged_in = False
            st.rerun()

    if st.session_state.role == "admin":
        st.header("ניהול תיקים כללי")
        st.dataframe(df)
    else:
        # שליפת נתוני משתמש
        user = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share, acts = user.iloc[0], safe_n(user.iloc[2]), safe_n(user.iloc[3]), safe_n(user.iloc[4])
        
        # חישובים
        gross_value = total_nav * (share / 100.0)
        broker_fees = (acts + 1) * 1.0
        profit_before_tax = gross_value - inv - broker_fees
        
        tax = profit_before_tax * 0.25 if profit_before_tax > 0 and name != "רפאל כהן" else 0
        success_fee = (profit_before_tax - tax) * 0.20 if profit_before_tax > 0 and name != "רפאל כהן" else 0
        net_val = gross_value - tax - success_fee

        st.title(f"שלום, {name}")
        
        # כרטיסים עליונים
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"<div class='metric-container'><div class='metric-lbl'>יתרה נטו (USD)</div><div class='metric-val'>${net_val:,.2f}</div></div>", unsafe_allow_html=True)
        with c2:
            profit_net = net_val - inv
            color = "#00ff88" if profit_net >= 0 else "#ff4b4b"
            st.markdown(f"<div class='metric-container'><div class='metric-lbl'>רווח/הפסד נקי</div><div class='metric-val' style='color:{color}'>${profit_net:,.2f}</div></div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='metric-container'><div class='metric-lbl'>תשואה באחוזים</div><div class='metric-val'>{(profit_net/inv*100):.2f}%</div></div>", unsafe_allow_html=True)

        st.write("---")
        
        # גרף צמיחה נקי (ללא זיגזגים)
        st.subheader("מגמת תיק השקעות")
        dates = [datetime.now() - timedelta(days=30), datetime.now()]
        points = [inv, net_val]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=points,
            mode='lines+markers',
            line=dict(color='#d4af37', width=4),
            fill='tozeroy',
            fillcolor='rgba(212, 175, 55, 0.1)',
            marker=dict(size=12, color='#d4af37')
        ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=20, b=0), height=350,
            xaxis=dict(showgrid=False, fixedrange=True),
            yaxis=dict(showgrid=True, gridcolor='#1c2128', side="right", fixedrange=True),
            dragmode=False
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # שורת בחירת זמנים (למראה בלבד כרגע)
        st.columns(5)[2].segmented_control("תקופה", ["1D", "1W", "1M", "1Y", "MAX"], default="1M")

        st.write("---")
        
        # פירוט עמלות למטה
        st.subheader("פירוט עמלות ומיסים")
        f1, f2, f3 = st.columns(3)
        with f1:
            st.markdown(f"<div class='fee-card'><b>מס רווח הון (25%):</b><br>${tax:,.2f}</div>", unsafe_allow_html=True)
        with f2:
            st.markdown(f"<div class='fee-card'><b>עמלת הצלחה (20%):</b><br>${success_fee:,.2f}</div>", unsafe_allow_html=True)
        with f3:
            st.markdown(f"<div class='fee-card'><b>עמלות ברוקר מצטברות:</b><br>${broker_fees:,.2f}</div>", unsafe_allow_html=True)
