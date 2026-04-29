import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import pytz

# --- הגדרות ליבה ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1489351"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", page_icon="🏦", layout="wide")

# עיצוב (Dark Mode)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    #MainMenu, footer, header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

def fetch_ibkr_nav_safe():
    """מנגנון משיכה עקשן עם 5 ניסיונות"""
    try:
        # בקשת דו"ח
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=20)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            url = root.find('Url').text
            code = root.find('ReferenceCode').text
            
            # לולאת ניסיונות - מחכה שאינטראקטיב ייצרו את הקובץ
            for i in range(5): 
                time.sleep(4) # מחכה 4 שניות בין כל ניסיון
                resp = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=20)
                
                if b"NetAssetValue" in resp.content:
                    d_root = ET.fromstring(resp.content)
                    nav_list = []
                    # סורק את כל שורות ה-NAV
                    for nav in d_root.findall(".//NetAssetValue"):
                        val = nav.get("total")
                        if val: nav_list.append(float(val))
                    
                    if nav_list:
                        return max(nav_list) # לוקח את הערך הכי גבוה (התיק הכולל)
        return None
    except:
        return None

# ניהול הנתונים ב-Session
if 'auth' not in st.session_state: st.session_state.auth = False
if 'current_nav' not in st.session_state: st.session_state.current_nav = 6131.72 # ערך גיבוי

# טעינת גוגל
@st.cache_data(ttl=5)
def get_sheet_data():
    return pd.read_csv(f"{SHEET_URL}&nocache={time.time()}")

try:
    df = get_sheet_data()
except:
    df = None

# --- דף כניסה ---
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("<br><br><h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("PIN", type="password")
        if st.button("LOGIN"):
            if pin == "0000": st.session_state.auth, st.session_state.role = True, "admin"
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
            st.rerun()
else:
    # --- סרגל צד ---
    with st.sidebar:
        st.write("### שליטה")
        if st.button("🔄 רענון מ-IBKR (לחיצה אחת)"):
            with st.spinner("מתחבר לאינטראקטיב... זה לוקח כ-20 שניות"):
                new_nav = fetch_ibkr_nav_safe()
                if new_nav:
                    st.session_state.current_nav = new_nav
                    st.success("התעדכן!")
                else:
                    st.error("לא הצלחתי למשוך נתונים. נסה שוב בעוד דקה.")
            st.rerun()
        
        st.write("---")
        st.write("שווי תיק ברוקר:")
        st.title(f"${st.session_state.current_nav:,.2f}")
        
        if st.button("Logout"):
            st.session_state.auth = False
            st.rerun()

    # --- תצוגת משתמש ---
    if st.session_state.role == "user":
        user = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv = user.iloc[0], float(str(user.iloc[2]).replace('$', '').replace(',', ''))
        share = float(str(user.iloc[3]).replace('%', ''))
        acts = float(user.iloc[4])

        # חישוב יחסי
        user_gross = st.session_state.current_nav * (share / 100.0)
        profit = user_gross - inv - ((acts + 1) * 1.0)
        
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        fee = (profit - tax) * 0.20 if profit > 0 and "רפאל" not in name else 0
        net = user_gross - tax - fee

        st.title(f"שלום, {name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${net:,.2f}")
        c2.metric("רווח/הפסד", f"${(net-inv):,.2f}", delta=f"{((net-inv)/inv*100):.2f}%")
        c3.metric("נתח בתיק", f"{share}%")

        # גרף
        fig = go.Figure(go.Scatter(
            x=["הפקדה", "נוכחי"], y=[inv, net],
            mode='lines+markers+text', text=[f"${inv:,.0f}", f"${net:,.0f}"],
            textposition="top center", line=dict(color='#d4af37', width=4)
        ))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350, margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.table(df)
