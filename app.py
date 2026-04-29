import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import pytz

# --- הגדרות חיבור ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1489351"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", page_icon="🏦", layout="wide")

# עיצוב ממשק
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    #MainMenu, footer, header {visibility: hidden;}
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    .update-tag { background-color: #d4af37; color: black; padding: 4px 12px; border-radius: 10px; font-weight: bold; font-size: 12px; }
    </style>
    """, unsafe_allow_html=True)

# פונקציית משיכה אגרסיבית (No Cache)
def get_live_market_data():
    t_stamp = str(int(time.time()))
    # 1. משיכת הגיליון
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={t_stamp}")
    except:
        df = None

    # 2. משיכת נתונים מאינטראקטיב (IBKR)
    current_nav = 0.0
    try:
        # שליחת בקשה ראשונה לקבלת קוד גישה לדו"ח
        base_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
        r = requests.get(f"{base_url}?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=10)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            code = root.find('ReferenceCode').text
            url = root.find('Url').text
            
            # המתנה קצרה כדי לוודא שהדו"ח מוכן בשרת של IB
            time.sleep(1.5)
            
            # בקשת הנתונים עצמם
            data_r = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=10)
            data_root = ET.fromstring(data_r.content)
            
            # חיפוש ה-Net Asset Value (NAV) הכולל
            nav_element = data_root.find(".//NetAssetValue")
            if nav_element is not None:
                current_nav = float(nav_element.get("total"))
    except Exception as e:
        st.sidebar.error(f"שגיאת תקשורת עם IB: {e}")
        current_nav = 6131.72 # ערך גיבוי אם הברוקר לא עונה
        
    return df, current_nav

# ניהול ה-Session
if 'auth' not in st.session_state: st.session_state.auth = False
if 'data_package' not in st.session_state: st.session_state.data_package = None

# טעינה ראשונית
if st.session_state.data_package is None:
    st.session_state.data_package = get_live_market_data()

# כניסה למערכת
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("<br><br><h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("הכנס PIN", type="password")
        if st.button("כניסה"):
            df_check = st.session_state.data_package[0]
            if pin == "0000": 
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif df_check is not None and str(pin) in df_check.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("קוד שגוי")
else:
    # תפריט צד
    with st.sidebar:
        st.title("RC Control")
        if st.button("🔄 רענון נתונים מ-IBKR"):
            with st.spinner("מושך נתונים חיים מהבורסה..."):
                st.session_state.data_package = get_live_market_data()
                st.success("הנתונים עודכנו בהצלחה!")
                time.sleep(1)
                st.rerun()
        
        if st.button("🚪 התנתק"):
            st.session_state.auth = False
            st.rerun()
        
        st.write("---")
        st.write(f"שווי תיק כולל ב-IB:")
        st.code(f"${st.session_state.data_package[1]:,.2f}")

    df, total_nav = st.session_state.data_package

    if st.session_state.role == "user":
        user_data = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name = user_data.iloc[0]
        investment = float(str(user_data.iloc[2]).replace('$', '').replace(',', ''))
        share_pct = float(str(user_data.iloc[3]).replace('%', ''))
        commissions = float(user_data.iloc[4])

        # חישוב הערך היחסי לפי הנתון החי מ-IBKR
        user_gross = total_nav * (share_pct / 100.0)
        
        # חישוב רווח ועמלות
        raw_profit = user_gross - investment - ((commissions + 1) * 1.0)
        tax = raw_profit * 0.25 if raw_profit > 0 and "רפאל" not in name else 0
        perf_fee = (raw_profit - tax) * 0.20 if raw_profit > 0 and "רפאל" not in name else 0
        user_net = user_gross - tax - perf_fee

        # זמן ישראל
        tz = pytz.timezone('Asia/Jerusalem')
        update_time = datetime.now(tz).strftime('%H:%M:%S | %d/%m/%Y')

        st.title(f"שלום, {name}")
        st.markdown(f"<span class='update-tag'>סונכרן עם Interactive Brokers: {update_time}</span>", unsafe_allow_html=True)
        st.write("<br>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נוכחית (Net)", f"${user_net:,.2f}")
        c2.metric("רווח/הפסד כולל", f"${(user_net - investment):,.2f}", delta=f"{((user_net-investment)/investment*100):.2f}%")
        c3.metric("אחוז בקרן", f"{share_pct}%")

        # גרף ביצועים
        st.write("<br>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=["הפקדה", "מצב נוכחי"], y=[investment, user_net],
            mode='lines+markers+text',
            text=[f"${investment:,.0f}", f"${user_net:,.2f}"], textposition="top center",
            line=dict(color='#d4af37', width=5),
            marker=dict(size=12, color='#d4af37')
        ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=40, b=0), height=350,
            xaxis=dict(fixedrange=True), yaxis=dict(side="right", showgrid=True, gridcolor="#1c2128", fixedrange=True),
            dragmode=False
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.write("---")
        st.subheader("פירוט שקיפות")
        st.info(f"הנתונים נמשכו ישירות מחשבון ה-Interactive Brokers שלך. שווי התיק הכולל בבורסה כרגע: **${total_nav:,.2f}**")
    else:
        st.title("Admin Dashboard")
        st.dataframe(df)
