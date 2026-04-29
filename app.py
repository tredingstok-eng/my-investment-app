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

# עיצוב יוקרתי
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    #MainMenu, footer, header {visibility: hidden;}
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    .update-tag { background-color: #d4af37; color: black; padding: 4px 12px; border-radius: 8px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def get_ibkr_data():
    """משיכת נתונים עם הגנה מפני ערכי אפס"""
    try:
        # שלב 1: בקשת הדו"ח
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        root = ET.fromstring(r.content)
        
        if root.find("Status").text == "Success":
            url = root.find('Url').text
            code = root.find('ReferenceCode').text
            
            # שלב 2: ניסיונות משיכה עם המתנה גדלה
            for i in range(3):
                time.sleep(3 + i) 
                resp = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
                
                # בדיקה אם יש תוכן רלוונטי ב-XML
                if b"NetAssetValue" in resp.content:
                    d_root = ET.fromstring(resp.content)
                    
                    # שיטת חיפוש אגרסיבית בכל ענפי ה-XML
                    all_navs = d_root.findall(".//NetAssetValue")
                    for nav_item in all_navs:
                        # אנחנו מחפשים שורה שיש בה גם total וגם היא מייצגת את התיק הכולל
                        val = nav_item.get("total")
                        if val and float(val) > 100: # הגנה: אם השווי נמוך מ-100$, זה כנראה לא התיק האמיתי
                            return float(val)
        return None
    except:
        return None

def fetch_master_data():
    """ריענון של גוגל ושל אינטראקטיב"""
    # גוגל (עם מזהה ייחודי למניעת Cache)
    try:
        df = pd.read_csv(f"{SHEET_URL}&nocache={int(time.time())}")
    except:
        df = None
    
    # אינטראקטיב
    nav = get_ibkr_data()
    return df, nav

# ניהול ה-Session State
if 'auth' not in st.session_state: st.session_state.auth = False
if 'df' not in st.session_state: st.session_state.df = None
if 'last_valid_nav' not in st.session_state: st.session_state.last_valid_nav = 6131.72

# טעינה ראשונית במידה ואין נתונים
if st.session_state.df is None:
    d, n = fetch_master_data()
    st.session_state.df = d
    if n: st.session_state.last_valid_nav = n

# --- מסך כניסה ---
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("<br><br><h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("PIN", type="password")
        if st.button("כניסה"):
            if pin == "0000": 
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("PIN לא תקין")
else:
    # --- תפריט צד ---
    with st.sidebar:
        st.markdown("### RC Capital Control")
        if st.button("🔄 רענון נתונים מלא"):
            with st.spinner("מושך נתונים מ-IBKR..."):
                new_df, new_nav = fetch_master_data()
                if new_df is not None: st.session_state.df = new_df
                # קריטי: אם ה-NAV החדש הוא אפס או None, אנחנו לא דורסים את הקיים!
                if new_nav and new_nav > 0:
                    st.session_state.last_valid_nav = new_nav
                    st.success("הסנכרון הצליח!")
                else:
                    st.warning("IBKR לא שלח נתונים, שומר שווי אחרון ידוע")
                st.rerun()
        
        st.write("---")
        st.write("שווי תיק ברוקר:")
        st.subheader(f"${st.session_state.last_valid_nav:,.2f}")
        
        if st.button("🚪 התנתק"):
            st.session_state.auth = False
            st.rerun()

    # --- תצוגת משתמש ---
    if st.session_state.role == "user":
        u_df = st.session_state.df
        user = u_df[u_df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        
        name = user.iloc[0]
        inv = float(str(user.iloc[2]).replace('$', '').replace(',', ''))
        share = float(str(user.iloc[3]).replace('%', ''))
        acts = float(user.iloc[4])
        
        # חישובים
        current_nav = st.session_state.last_valid_nav
        gross = current_nav * (share / 100.0)
        profit = gross - inv - ((acts + 1) * 1.0)
        
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        fee = (profit - tax) * 0.20 if profit > 0 and "רפאל" not in name else 0
        net = gross - tax - fee

        tz = pytz.timezone('Asia/Jerusalem')
        update_str = datetime.now(tz).strftime('%H:%M:%S | %d/%m/%Y')

        st.title(f"שלום, {name}")
        st.markdown(f"<span class='update-tag'>סונכרן עם IBKR: {update_str}</span>", unsafe_allow_html=True)
        
        st.write("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${net:,.2f}")
        c2.metric("רווח/הפסד", f"${(net-inv):,.2f}", delta=f"{((net-inv)/inv*100):.2f}%")
        c3.metric("אחוז בקרן", f"{share}%")

        # גרף חסין נפילות
        st.write("<br>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=["הפקדה", "נוכחי"], y=[inv, net],
            mode='lines+markers+text',
            text=[f"${inv:,.0f}", f"${net:,.0f}"], textposition="top center",
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
        st.title("Admin Dashboard")
        st.dataframe(st.session_state.df)
