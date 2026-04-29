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

# עיצוב UI
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    #MainMenu, footer, header {visibility: hidden;}
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    .update-tag { background-color: #d4af37; color: black; padding: 4px 12px; border-radius: 8px; font-weight: bold; font-size: 13px; }
    </style>
    """, unsafe_allow_html=True)

def get_ibkr_nav():
    """משיכה אגרסיבית של שווי התיק מאינטראקטיב"""
    try:
        # שלב א: בקשת הדו"ח
        base_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
        r = requests.get(f"{base_url}?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            code = root.find('ReferenceCode').text
            url = root.find('Url').text
            
            # שלב ב: ניסיונות משיכה (Retry loop) - השרת של IB איטי
            for attempt in range(3):
                time.sleep(2.5) # המתנה משמעותית בין ניסיון לניסיון
                data_r = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
                
                # בדיקה אם קיבלנו XML תקין או הודעת "קובץ לא מוכן"
                if b"NetAssetValue" in data_r.content:
                    data_root = ET.fromstring(data_r.content)
                    # מחפש את ה-NAV בכל מקום אפשרי ב-XML
                    nav_elements = data_root.findall(".//NetAssetValue")
                    for elem in nav_elements:
                        # אנחנו מחפשים את השורה של ה-Total (לפעמים יש פירוט לפי מטבעות)
                        total = elem.get("total")
                        if total and float(total) > 0:
                            return float(total)
        return None
    except:
        return None

def fetch_all_data():
    """טעינת כל המקורות יחד"""
    t_stamp = str(int(time.time()))
    # טעינת גוגל
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={t_stamp}")
    except:
        df = None
    
    # טעינת IBKR
    nav = get_ibkr_nav()
    return df, nav

# ניהול הזיכרון (Session State)
if 'auth' not in st.session_state: st.session_state.auth = False
if 'df' not in st.session_state: st.session_state.df = None
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72 # ערך מחדל

# טעינה ראשונית
if st.session_state.df is None:
    df_new, nav_new = fetch_all_data()
    st.session_state.df = df_new
    if nav_new: st.session_state.total_nav = nav_new

# דף כניסה
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("<br><br><h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("PIN Code", type="password")
        if st.button("כניסה למערכת"):
            if pin == "0000": 
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("קוד לא תקין")
else:
    # Sidebar
    with st.sidebar:
        st.subheader("ניהול חשבון")
        if st.button("🔄 רענון נתונים חי"):
            with st.spinner("מתחבר לבורסה..."):
                df_new, nav_new = fetch_all_data()
                if df_new is not None: st.session_state.df = df_new
                if nav_new and nav_new > 0: 
                    st.session_state.total_nav = nav_new
                    st.success("סונכרן בהצלחה")
                else:
                    st.warning("IBKR לא החזיר נתונים, שומר נתח אחרון")
                st.rerun()
        
        if st.button("🚪 התנתק"):
            st.session_state.auth = False
            st.rerun()
        
        st.write("---")
        st.write("שווי תיק ברוקר:")
        st.markdown(f"### ${st.session_state.total_nav:,.2f}")

    if st.session_state.role == "user":
        # חילוץ נתוני משתמש
        df = st.session_state.df
        user_row = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        
        name = user_row.iloc[0]
        inv = float(str(user_row.iloc[2]).replace('$', '').replace(',', ''))
        share = float(str(user_row.iloc[3]).replace('%', ''))
        acts = float(user_row.iloc[4])
        
        # חישובים מבוססי IBKR NAV
        gross = st.session_state.total_nav * (share / 100.0)
        profit_raw = gross - inv - ((acts + 1) * 1.0)
        
        # חישוב מס ועמלה (רק אם זה לא רפאל)
        tax = profit_raw * 0.25 if profit_raw > 0 and "רפאל" not in name else 0
        fee = (profit_raw - tax) * 0.20 if profit_raw > 0 and "רפאל" not in name else 0
        net_value = gross - tax - fee

        tz = pytz.timezone('Asia/Jerusalem')
        now = datetime.now(tz).strftime('%H:%M:%S | %d/%m/%Y')

        st.title(f"שלום, {name}")
        st.markdown(f"<span class='update-tag'>סנכרון IBKR אחרון: {now}</span>", unsafe_allow_html=True)
        st.write("<br>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${net_value:,.2f}")
        c2.metric("רווח/הפסד", f"${(net_value-inv):,.2f}", delta=f"{((net_value-inv)/inv*100):.2f}%")
        c3.metric("אחוז בקרן", f"{share}%")

        # גרף
        st.write("<br>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=["הפקדה", "נוכחי"], y=[inv, net_value],
            mode='lines+markers+text',
            text=[f"${inv:,.0f}", f"${net_value:,.0f}"], textposition="top center",
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
    else:
        st.title("ניהול")
        st.table(st.session_state.df)
