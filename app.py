import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
import random

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital Live", layout="wide")

# עיצוב RTL
st.markdown("<style> * { direction: rtl; text-align: right; } .stMetric { background-color: #0d1117; border-radius: 10px; padding: 15px; border: 1px solid #30363d; } </style>", unsafe_allow_html=True)

def fetch_now():
    """משיכת נתונים עם עקיפת Cache"""
    try:
        # הוספת מספר אקראי כדי שאינטראקטיב לא יביא קובץ ישן מהזיכרון
        cb = random.randint(1000, 9999)
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3&cb={cb}", timeout=15)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            url, code = root.find('Url').text, root.find('ReferenceCode').text
            # המתנה קצרה כדי שהשרת יסיים לייצר
            time.sleep(10)
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
            d_root = ET.fromstring(res.content)
            
            # חיפוש הערך הכי גבוה (השווי הכולל)
            nav_elements = d_root.findall(".//EquitySummaryByReportDateInBase")
            vals = [float(el.get("total")) for el in nav_elements if el.get("total")]
            
            if vals:
                return max(vals)
        return None
    except: return None

# ניהול זיכרון (State)
if 'auth' not in st.session_state: st.session_state.auth = False
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72 # ערך בסיס
if 'df' not in st.session_state: st.session_state.df = None

def refresh():
    # גוגל שיטס
    try:
        new_df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        for col in new_df.columns[2:]:
            new_df[col] = new_df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = new_df
    except: pass
    
    # אינטראקטיב
    val = fetch_now()
    if val and val > 1000:
        st.session_state.total_nav = val

if st.session_state.df is None: refresh()

# --- כניסה ---
if not st.session_state.auth:
    st.title("RC Capital")
    pin = st.text_input("PIN", type="password")
    if st.button("כניסה"):
        if pin == "0000": st.session_state.auth, st.session_state.role = True, "admin"
        elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
            st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
        st.rerun()
else:
    with st.sidebar:
        st.header("ניהול")
        if st.button("🔄 עדכן מספרים עכשיו"):
            with st.spinner("מושך נתונים חיים מהבורסה..."):
                refresh()
            st.rerun()
        st.write("---")
        st.write("שווי תיק נוכחי בברוקר:")
        st.subheader(f"${st.session_state.total_nav:,.2f}")
        if st.button("יציאה"):
            st.session_state.auth = False
            st.rerun()

    if st.session_state.role == "user":
        user = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share = user.iloc[0], user.iloc[2], user.iloc[3]
        
        # חישוב יחסי למספר שמופיע בסרגל הצד
        current_nav = st.session_state.total_nav
        u_gross = current_nav * (share / 100.0)
        profit = u_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        u_net = u_gross - tax

        st.title(f"שלום, {name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו (אחרי מס)", f"${u_net:,.2f}")
        c2.metric("רווח/הפסד כולל", f"${(u_net-inv):,.2f}", delta=f"{((u_net-inv)/inv*100):.2f}%")
        c3.metric("נתח יחסי בתיק", f"{share}%")

        fig = go.Figure(go.Scatter(x=["הפקדה", "נוכחי"], y=[inv, u_net], mode='lines+markers+text', 
                                   text=[f"${inv:,.0f}", f"${u_net:,.0f}"], textposition="top center",
                                   line=dict(color='#d4af37', width=4)))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400)
        st.plotly_chart(fig, use_container_width=True)
