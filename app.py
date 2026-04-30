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
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    </style>
    """, unsafe_allow_html=True)

def get_ibkr_nav_safe():
    """מנגנון משיכה עם המתנה אקטיבית למניעת ערכי אפס"""
    try:
        # שלב א: בקשת הדו"ח
        base_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
        r = requests.get(f"{base_url}?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            code = root.find('ReferenceCode').text
            url = root.find('Url').text
            
            # שלב ב: לולאת המתנה (Retry Loop)
            # אינטראקטיב צריכים זמן לייצר את הדו"ח. ננסה 5 פעמים עם הפסקות.
            for attempt in range(5):
                time.sleep(4) # המתנה של 4 שניות בין ניסיון לניסיון
                data_r = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
                
                if b"NetAssetValue" in data_r.content:
                    data_root = ET.fromstring(data_r.content)
                    # מחפש את ה-NAV הכולל (Total) בתוך ה-XML
                    nav_elements = data_root.findall(".//NetAssetValue")
                    for elem in nav_elements:
                        total = elem.get("total")
                        # אנחנו מוודאים שהערך קיים והוא גדול מ-0 כדי לא להרוס את הגרף
                        if total and float(total) > 0:
                            return float(total)
        return None
    except Exception as e:
        return None

# ניהול מצב (Session State) - זה המוח של האפליקציה
if 'auth' not in st.session_state: st.session_state.auth = False
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72 # ערך התחלה בטוח
if 'df' not in st.session_state: st.session_state.df = None

def refresh_all_data():
    """פונקציה לרענון כל הנתונים מכל המקורות"""
    # 1. טעינת גוגל שיטס (עם מנגנון מניעת Cache)
    try:
        t_stamp = str(int(time.time()))
        st.session_state.df = pd.read_csv(f"{SHEET_URL}&cb={t_stamp}")
    except:
        pass
    
    # 2. טעינת IBKR
    new_nav = get_ibkr_nav_safe()
    if new_nav and new_nav > 0:
        st.session_state.total_nav = new_nav

# טעינה ראשונית רק פעם אחת
if st.session_state.df is None:
    refresh_all_data()

# --- מסך כניסה ---
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("<br><br><h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("קוד PIN", type="password")
        if st.button("כניסה"):
            if pin == "0000":
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else:
                st.error("קוד לא תקין")
else:
    # --- דאשבורד ---
    with st.sidebar:
        st.subheader("ניהול")
        if st.button("🔄 רענון נתונים חי"):
            with st.spinner("מתחבר לבורסה (זה לוקח כ-20 שניות)..."):
                refresh_all_data()
                st.rerun()
        
        st.write("---")
        st.write("שווי תיק ברוקר:")
        st.markdown(f"### ${st.session_state.total_nav:,.2f}")
        
        if st.button("🚪 התנתק"):
            st.session_state.auth = False
            st.rerun()

    if st.session_state.role == "user":
        # שליפת נתוני משתמש
        user_row = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name = user_row.iloc[0]
        investment = float(str(user_row.iloc[2]).replace('$', '').replace(',', ''))
        share_pct = float(str(user_row.iloc[3]).replace('%', ''))
        commissions = float(user_row.iloc[4])
        
        # חישובים לפי ה-NAV המעודכן
        user_gross = st.session_state.total_nav * (share_pct / 100.0)
        profit_before_tax = user_gross - investment - ((commissions + 1) * 1.0)
        
        # מיסוי ועמלות (פטור לרפאל)
        tax = profit_before_tax * 0.25 if profit_before_tax > 0 and "רפאל" not in name else 0
        perf_fee = (profit_before_tax - tax) * 0.20 if profit_before_tax > 0 and "רפאל" not in name else 0
        user_net = user_gross - tax - perf_fee

        st.title(f"שלום, {name}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${user_net:,.2f}")
        c2.metric("רווח/הפסד", f"${(user_net-investment):,.2f}", delta=f"{((user_net-investment)/investment*100):.2f}%")
        c3.metric("נתח בקרן", f"{share_pct}%")

        # גרף יציב
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=["הפקדה", "נוכחי"], y=[investment, user_net],
            mode='lines+markers+text',
            text=[f"${investment:,.0f}", f"${user_net:,.0f}"], textposition="top center",
            line=dict(color='#d4af37', width=4),
            marker=dict(size=10, color='#d4af37')
        ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=40, b=0), height=300,
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="#1c2128", side="right")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.title("ניהול קרן - מבט על")
        st.dataframe(st.session_state.df)
