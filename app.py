import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות מעודכנות לפי התמונות שלך ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787"  # ה-ID החדש מהתמונה שלך
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", layout="wide")

# עיצוב UI
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    </style>
    """, unsafe_allow_html=True)

def fetch_ibkr_final():
    """משיכת נתונים עם התאמה ל-NAV in Base"""
    try:
        # שלב 1: שליחת הבקשה
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            url = root.find('Url').text
            code = root.find('ReferenceCode').text
            
            # שלב 2: המתנה לקובץ (6 ניסיונות)
            for _ in range(6):
                time.sleep(5)
                res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
                
                # בדיקה אם ה-XML מכיל נתוני NAV
                if b"NetAssetValue" in res.content or b"NAVInBase" in res.content:
                    d_root = ET.fromstring(res.content)
                    
                    # מחפש את הערך הגבוה ביותר בדו"ח (בדרך כלל ה-Total NAV)
                    all_values = []
                    for nav in d_root.findall(".//NetAssetValue"):
                        val = nav.get("total")
                        if val: all_values.append(float(val))
                    
                    # אם השתמשת ב-NAV in Base, ייתכן שהשדה נקרא אחרת ב-XML
                    for nav in d_root.findall(".//NavInBase"):
                        val = nav.get("total")
                        if val: all_values.append(float(val))
                        
                    if all_values:
                        found_nav = max(all_values)
                        # הגנה: אם המספר קטן מדי (טעות טעינה), נתעלם
                        if found_nav > 1000:
                            return found_nav
        return None
    except Exception as e:
        return None

# זיכרון אפליקציה
if 'auth' not in st.session_state: st.session_state.auth = False
if 'total_nav' not in st.session_state: st.session_state.total_nav = 6131.72
if 'df' not in st.session_state: st.session_state.df = None

def refresh():
    try: st.session_state.df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
    except: pass
    
    new_val = fetch_ibkr_final()
    if new_val:
        st.session_state.total_nav = new_val

if st.session_state.df is None:
    refresh()

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
            else: st.error("PIN שגוי")
else:
    # --- דאשבורד ---
    with st.sidebar:
        if st.button("🔄 רענון נתונים"):
            with st.spinner("מתחבר לאינטראקטיב..."):
                refresh()
            st.rerun()
        st.write("---")
        st.write("שווי תיק כולל:")
        st.subheader(f"${st.session_state.total_nav:,.2f}")
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    if st.session_state.role == "user":
        user_data = st.session_state.df[st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name = user_data.iloc[0]
        inv = float(str(user_data.iloc[2]).replace('$', '').replace(',', ''))
        share = float(str(user_data.iloc[3]).replace('%', ''))
        
        # חישוב
        u_gross = st.session_state.total_nav * (share / 100.0)
        profit = u_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        u_net = u_gross - tax

        st.title(f"שלום, {name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${u_net:,.2f}")
        c2.metric("רווח/הפסד", f"${(u_net-inv):,.2f}", delta=f"{((u_net-inv)/inv*100):.2f}%")
        c3.metric("נתח בתיק", f"{share}%")

        fig = go.Figure(go.Scatter(x=["הפקדה", "היום"], y=[inv, u_net], mode='lines+markers+text', 
                                   text=[f"${inv:,.0f}", f"${u_net:,.0f}"], textposition="top center",
                                   line=dict(color='#d4af37', width=4)))
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=400)
        st.plotly_chart(fig, use_container_width=True)
