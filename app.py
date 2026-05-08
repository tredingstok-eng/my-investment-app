import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ליבה ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", layout="wide")

# אתחול משתני זיכרון (Session State)
if 'auth' not in st.session_state: st.session_state.auth = False
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72
if 'df' not in st.session_state: st.session_state.df = None

# עיצוב RTL
st.markdown("<style>* { direction: rtl; text-align: right; }</style>", unsafe_allow_html=True)

def fetch_ibkr_data():
    """משיכת נתונים מאינטראקטיב עם בדיקה כפולה"""
    try:
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        if root.find("Status").text == "Success":
            url, code = root.find('Url').text, root.find('ReferenceCode').text
            for _ in range(5): # ניסיונות המתנה
                time.sleep(5)
                res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
                if b"NetAssetValue" in res.content:
                    d_root = ET.fromstring(res.content)
                    # מחפש את הערך הכי גבוה בדו"ח (כדי לא לקחת רק מזומן בטעות)
                    vals = [float(n.get("total")) for n in d_root.findall(".//NetAssetValue") if n.get("total")]
                    if vals:
                        return max(vals)
        return None
    except: return None

def get_clean_df():
    """טעינה וניקוי נתונים מגוגל שיטס"""
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        # ניקוי תווים מיוחדים מכל העמודות הרלוונטיות
        for col in df.columns[2:]: 
            df[col] = df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        return df
    except: return None

def refresh_logic():
    """רענון מרכזי - מעדכן את הזיכרון של האפליקציה"""
    new_df = get_clean_df()
    if new_df is not None:
        st.session_state.df = new_df
    
    new_nav = fetch_ibkr_data()
    if new_nav and new_nav > 1000: # הגנה מפני נתון חלקי
        st.session_state.total_nav = new_nav

# טעינה אוטומטית בכניסה
if st.session_state.df is None:
    refresh_logic()

# --- ממשק משתמש ---
if not st.session_state.auth:
    st.title("RC Capital - כניסה")
    pin = st.text_input("PIN", type="password")
    if st.button("כניסה"):
        if pin == "0000": 
            st.session_state.auth, st.session_state.role = True, "admin"
            st.rerun()
        elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
            st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
            st.rerun()
        else: st.error("קוד שגוי")
else:
    # Sidebar
    with st.sidebar:
        if st.button("🔄 רענון נתונים"):
            with st.spinner("מעדכן..."): refresh_logic()
            st.rerun()
        st.write(f"שווי תיק ברוקר: **${st.session_state.total_nav:,.2f}**")
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    # דף משתמש
    if st.session_state.role == "user":
        user = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share = user.iloc[0], user.iloc[2], user.iloc[3]
        
        # חישוב (שימוש בלעדי ב-total_nav מהזיכרון)
        u_gross = st.session_state.total_nav * (share / 100.0)
        profit = u_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        u_net = u_gross - tax

        st.header(f"שלום {name}")
        c1, c2 = st.columns(2)
        c1.metric("יתרה נטו", f"${u_net:,.2f}")
        c2.metric("רווח/הפסד", f"${(u_net-inv):,.2f}", delta=f"{((u_net-inv)/inv*100):.1f}%")
        
        fig = go.Figure(go.Scatter(x=["הפקדה", "נוכחי"], y=[inv, u_net], mode='lines+markers+text', 
                                   text=[f"${inv:,.0f}", f"${u_net:,.0f}"], textposition="top center"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("מצב מנהל")
        st.dataframe(st.session_state.df)
