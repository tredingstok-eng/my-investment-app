import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time
import plotly.graph_objects as go

# --- הגדרות חיבור (מפרט טכני) ---
IB_TOKEN = "837126977366730658372732" #
IB_QUERY = "1492787" #
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv" #

st.set_page_config(page_title="RC Capital", layout="wide")

# עיצוב RTL לעברית
st.markdown("""
    <style>
    .main { direction: rtl; text-align: right; }
    div.stButton > button { width: 100%; }
    [data-testid="stSidebar"] { direction: rtl; }
    </style>
    """, unsafe_allow_html=True)

# פונקציה למשיכת נתונים מאינטראקטיב (Flex Query)
def get_ibkr_nav():
    try:
        # שליחת בקשה לייצור דו"ח
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=10)
        root = ET.fromstring(r.content)
        if root.find("Status").text == "Success":
            url = root.find('Url').text
            code = root.find('ReferenceCode').text
            time.sleep(1) # המתנה קלה לעיבוד
            # משיכת הקובץ בפועל
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=10)
            d_root = ET.fromstring(res.content)
            # חילוץ ה-NAV מה-XML
            nav_elements = d_root.findall(".//EquitySummaryByReportDateInBase")
            vals = [float(el.get("total")) for el in nav_elements if el.get("total")]
            if vals: return max(vals)
    except: pass
    return None

# טעינת נתונים וניהול זיכרון (Session State)
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72 # ערך מחדל
if 'df' not in st.session_state: st.session_state.df = None
if 'auth' not in st.session_state: st.session_state.auth = False

def refresh_all():
    # 1. טעינת גוגל שיטס (משתמשים ואחוזים)
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        for col in df.columns[2:]:
            df[col] = df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = df
    except: st.error("שגיאה בחיבור לגוגל שיטס")

    # 2. עדכון מהבורסה
    new_nav = get_ibkr_nav()
    if new_nav:
        st.session_state.total_nav = new_nav

# טעינה ראשונית
if st.session_state.df is None: refresh_all()

# --- ממשק כניסה ---
if not st.session_state.auth:
    st.title("RC Capital - כניסת משקיעים")
    pin = st.text_input("הזן קוד PIN", type="password")
    if st.button("כניסה"):
        if pin == "0000": 
            st.session_state.auth, st.session_state.role = True, "admin"
            st.rerun()
        elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
            st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
            st.rerun()
        else:
            st.error("קוד PIN שגוי")

else:
    # --- תצוגת דאשבורד ---
    with st.sidebar:
        st.header("ניהול תיק")
        st.write(f"שווי ברוקר: **${st.session_state.total_nav:,.2f}**")
        if st.button("🔄 רענון נתונים מהבורסה"):
            refresh_all()
            st.rerun()
        
        # אפשרות עדכון ידנית למנהל בלבד (במקרה שה-API של IBKR תקוע)
        if st.session_state.role == "admin":
            st.write("---")
            manual_val = st.number_input("תיקון ידני (Admin)", value=st.session_state.total_nav)
            if st.button("עדכן שווי ידנית"):
                st.session_state.total_nav = manual_val
                st.success("השווי עודכן לכולם!")
        
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    # תצוגת משתמש (למשל קובי כהן)
    if st.session_state.role == "user":
        user_row = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name, inv, share = user_row.iloc[0], user_row.iloc[2], user_row.iloc[3]
        
        # חישוב הערך היחסי
        current_gross = st.session_state.total_nav * (share / 100)
        profit = current_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        current_net = current_gross - tax

        st.title(f"שלום, {name}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("יתרה נטו", f"${current_net:,.2f}")
        col2.metric("רווח/הפסד", f"${profit:,.2f}", delta=f"{(profit/inv)*100:.2f}%")
        col3.metric("נתח בתיק", f"{share}%")

        # גרף ביצועים פשוט
        fig = go.Figure(go.Scatter(x=["השקעה מקורית", "שווי נוכחי נטו"], y=[inv, current_net], mode='lines+markers+text', 
                                   text=[f"${inv:,.0f}", f"${current_net:,.0f}"], textposition="top center"))
        fig.update_layout(title="צמיחת ההשקעה", template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    elif st.session_state.role == "admin":
        st.title("ממשק ניהול - RC Capital")
        st.write("נתוני משקיעים מגוגל שיטס:")
        st.dataframe(st.session_state.df)
