import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות סופיות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", layout="wide")

# עיצוב RTL ויוקרה
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    </style>
    """, unsafe_allow_html=True)

def fetch_actual_nav():
    """משיכת נתונים המותאמת בדיוק למבנה ה-XML שקיבלנו"""
    try:
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        if root.find("Status").text == "Success":
            url, code = root.find('Url').text, root.find('ReferenceCode').text
            time.sleep(12) # המתנה לייצור הקובץ
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
            
            if b"EquitySummaryByReportDateInBase" in res.content:
                d_root = ET.fromstring(res.content)
                # מחפש את השדה שראינו ב-Debug
                elements = d_root.findall(".//EquitySummaryByReportDateInBase")
                for el in elements:
                    # אנחנו לוקחים את ה-Total (השדה שמכיל הכל)
                    total_val = el.get("total")
                    if total_val and float(total_val) > 1000:
                        return float(total_val)
        return None
    except: return None

# ניהול זיכרון
if 'auth' not in st.session_state: st.session_state.auth = False
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72
if 'df' not in st.session_state: st.session_state.df = None

def refresh_all():
    try:
        # רענון גוגל שיטס עם ניקוי תווים
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        for col in df.columns[2:]:
            df[col] = df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = df
    except: pass
    
    # רענון אינטראקטיב
    new_nav = fetch_actual_nav()
    if new_nav:
        st.session_state.total_nav = new_nav

if st.session_state.df is None:
    refresh_all()

# --- ממשק כניסה ---
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.title("RC Capital")
        pin = st.text_input("קוד PIN", type="password")
        if st.button("כניסה"):
            if pin == "0000": 
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("קוד שגוי")
else:
    # --- דאשבורד ---
    with st.sidebar:
        if st.button("🔄 רענון נתונים"):
            with st.spinner("מעדכן נתונים חיים..."): refresh_all()
            st.rerun()
        st.write("---")
        st.write("שווי תיק ברוקר:")
        st.subheader(f"${st.session_state.total_nav:,.2f}")
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    if st.session_state.role == "user":
        user_row = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share = user_row.iloc[0], user_row.iloc[2], user_row.iloc[3]
        
        # חישוב יחסי
        u_gross = st.session_state.total_nav * (share / 100.0)
        profit = u_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        u_net = u_gross - tax

        st.header(f"שלום, {name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${u_net:,.2f}")
        c2.metric("רווח/הפסד", f"${(u_net-inv):,.2f}", delta=f"{((u_net-inv)/inv*100):.1f}%")
        c3.metric("נתח בקרן", f"{share}%")

        fig = go.Figure(go.Scatter(x=["הפקדה", "נוכחי"], y=[inv, u_net], mode='lines+markers+text', 
                                   text=[f"${inv:,.0f}", f"${u_net:,.0f}"], textposition="top center",
                                   line=dict(color='#d4af37', width=4)))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("מצב מנהל")
        st.dataframe(st.session_state.df)
