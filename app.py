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
    /* הסתרת כל השורות והכותרות המיותרות של Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stMetric { background-color: #161b22; border-radius: 12px; padding: 20px; border: 1px solid #30363d; text-align: center; }
    div[data-testid="stMetricValue"] { font-size: 32px !important; color: #d4af37 !important; text-align: center; }
    div[data-testid="stMetricLabel"] { text-align: center; width: 100%; }
    /* עיצוב כפתורי זמן */
    .stHeader { display: none; }
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
    # קריאת גיליון - שים לב: אין כאן שום פקודת print שתדפיס אותיות למסך
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

# --- לוגיקה ---
df, total_nav = load_all()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<div style='height:100px;'></div>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("קוד כניסה:", type="password")
        if st.button("כניסה למערכת"):
            if pin == "0000":
                st.session_state.logged_in, st.session_state.role = True, "admin"
                st.rerun()
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.logged_in, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("קוד לא תקין")
else:
    if st.sidebar.button("התנתקות"):
        st.session_state.logged_in = False
        st.rerun()

    if st.session_state.role == "admin":
        st.header("ניהול תיקים")
        st.dataframe(df)
    else:
        # שליפת נתוני משתמש
        user = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name = user.iloc[0]
        inv = safe_n(user.iloc[2])
        share = safe_n(user.iloc[3])
        acts = safe_n(user.iloc[4])
        
        # חישוב שווי נוכחי
        current_gross = total_nav * (share / 100.0)
        # חישוב רווח נומינלי (לפני מס)
        nominal_profit = current_gross - inv - ((acts + 1) * 1.0)
        # יתרה נטו (אחרי מס של 25% במידה ויש רווח)
        tax = nominal_profit * 0.25 if nominal_profit > 0 else 0
        net_val = current_gross - tax

        st.title(f"שלום, {name}")
        
        # כרטיסי מידע
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו (USD)", f"${net_val:,.2f}")
        c2.metric("רווח/הפסד", f"${(net_val - inv):,.2f}", delta=f"{((net_val - inv)/inv*100):.2f}%")
        c3.metric("נתח בתיק", f"{share}%")

        st.markdown("<br>", unsafe_allow_html=True)

        # כפתורי תקופה - עיצוב נקי
        period = st.select_slider("", options=["יום", "שבוע", "חודש", "שנה", "MAX"], value="חודש")

        # בניית גרף יציב - ללא זיגזגים אקראיים
        # מכיוון שאין היסטוריה בגיליון, נציג קו ישר מההפקדה לערך הנוכחי
        dates = [datetime.now() - timedelta(days=30), datetime.now()]
        points = [inv, net_val]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=points,
            mode='lines+markers',
            line=dict(color='#d4af37', width=4),
            fill='tozeroy',
            fillcolor='rgba(212, 175, 55, 0.1)',
            marker=dict(size=10)
        ))

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=20, b=0),
            height=400,
            xaxis=dict(showgrid=False, fixedrange=True, tickformat="%d/%m"),
            yaxis=dict(showgrid=True, gridcolor='#1c2128', side="right", fixedrange=True),
            dragmode=False # מונע תזוזה מעצבנת
        )

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        st.write("---")
        st.subheader("ביצועי אחוזים")
        
        # גרף אחוזים פשוט
        fig_p = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = ((net_val - inv) / inv * 100),
            domain = {'x': [0, 1], 'y': [0, 1]},
            number = {'suffix': "%", 'font': {'color': "#d4af37"}},
            gauge = {
                'axis': {'range': [-20, 20], 'tickwidth': 1, 'tickcolor': "white"},
                'bar': {'color': "#d4af37"},
                'bgcolor': "#161b22",
                'borderwidth': 2,
                'bordercolor': "#30363d",
                'steps': [
                    {'range': [-20, 0], 'color': '#ff4b4b'},
                    {'range': [0, 20], 'color': '#00ff88'}]
            }
        ))
        fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', height=250, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_p, use_container_width=True)
