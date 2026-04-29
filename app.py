import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime
import pytz

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1489351"
# הלינק הישיר לגיליון
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", page_icon="🏦", layout="wide")

# עיצוב (Dark Mode יוקרתי)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;600&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #050505; color: white; }
    #MainMenu, footer, header {visibility: hidden;}
    .stMetric { background-color: #0d1117; border: 1px solid #30363d; border-radius: 15px; padding: 15px; }
    .update-time { color: #d4af37; font-size: 14px; font-weight: bold; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# פונקציה למשיכת נתונים ללא CACHE בכלל
def fetch_data_now():
    # יצירת מזהה זמן ייחודי לגמרי למניעת זיכרון של גוגל
    t_key = str(time.time()).replace('.', '')
    full_url = f"{SHEET_URL}&v={t_key}"
    
    try:
        df = pd.read_csv(full_url)
        # משיכת נתונים מ-IBKR
        nav = 6131.72
        try:
            r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=5)
            root = ET.fromstring(r.content)
            if root.find("Status").text == "Success":
                time.sleep(1.2) # המתנה קלה כדי שהשרת של IB יסיים לעבד
                d_r = requests.get(f"{root.find('Url').text}?q={root.find('ReferenceCode').text}&t={IB_TOKEN}")
                nav_val = ET.fromstring(d_r.content).find(".//NetAssetValue")
                if nav_val is not None: nav = float(nav_val.get("total"))
        except: pass
        return df, nav
    except Exception as e:
        st.error(f"שגיאת טעינה: {e}")
        return None, 6131.72

# ניהול מצב הכניסה והנתונים
if 'auth' not in st.session_state: st.session_state.auth = False
if 'data' not in st.session_state: st.session_state.data = None
if 'nav' not in st.session_state: st.session_state.nav = 6131.72

# טעינה ראשונית אם אין נתונים
if st.session_state.data is None:
    st.session_state.data, st.session_state.nav = fetch_data_now()

# דף כניסה
if not st.session_state.auth:
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("<br><br><h1 style='text-align:center;'>RC Capital</h1>", unsafe_allow_html=True)
        pin = st.text_input("PIN", type="password")
        if st.button("כניסה"):
            df = st.session_state.data
            if pin == "0000": 
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "user", str(pin)
                st.rerun()
            else: st.error("PIN שגוי")
else:
    # סרגל צד עם כפתור רענון שעובד באמת
    with st.sidebar:
        st.markdown("### שליטה")
        if st.button("🔄 רענון נתונים עכשיו"):
            # ניקוי ה-Cache של Streamlit בכוח
            st.cache_data.clear()
            # משיכה מחדש לתוך ה-Session
            st.session_state.data, st.session_state.nav = fetch_data_now()
            st.success("הנתונים עודכנו!")
            time.sleep(0.5)
            st.rerun()
            
        if st.button("🚪 התנתק"):
            st.session_state.auth = False
            st.rerun()

    df, total_nav = st.session_state.data, st.session_state.nav

    if st.session_state.role == "user":
        user_row = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        name = user_row.iloc[0]
        inv = float(str(user_row.iloc[2]).replace('$', '').replace(',', ''))
        share = float(str(user_row.iloc[3]).replace('%', ''))
        acts = float(user_row.iloc[4])
        
        # חישובים
        gross = total_nav * (share / 100.0)
        profit_raw = gross - inv - ((acts + 1) * 1.0)
        tax = profit_raw * 0.25 if profit_raw > 0 and "רפאל" not in name else 0
        fee = (profit_raw - tax) * 0.20 if profit_raw > 0 and "רפאל" not in name else 0
        net = gross - tax - fee

        # זמן ישראל מעודכן
        israel_tz = pytz.timezone('Asia/Jerusalem')
        now_israel = datetime.now(israel_tz).strftime('%H:%M:%S | %d/%m/%Y')

        st.title(f"שלום, {name}")
        st.markdown(f"<div class='update-time'>סונכרן לאחרונה: {now_israel}</div>", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו (USD)", f"${net:,.2f}")
        c2.metric("רווח/הפסד", f"${(net-inv):,.2f}", delta=f"{((net-inv)/inv*100):.2f}%")
        c3.metric("נתח בתיק", f"{share}%")

        # גרף ביצועים
        st.write("<br>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=["הפקדה ראשונית", "שווי נוכחי נטו"], y=[inv, net],
            mode='lines+markers+text',
            text=[f"${inv:,.0f}", f"${net:,.0f}"], textposition="top center",
            line=dict(color='#d4af37', width=4),
            marker=dict(size=12, color='#d4af37')
        ))
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=30, b=0), height=350,
            xaxis=dict(fixedrange=True), yaxis=dict(side="right", fixedrange=True, showgrid=True, gridcolor="#1c2128"),
            dragmode=False
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # פירוט עמלות
        st.write("---")
        st.subheader("פירוט שקיפות")
        f1, f2, f3 = st.columns(3)
        f1.info(f"**מס משוער:** ${tax:,.2f}")
        f2.info(f"**עמלת הצלחה:** ${fee:,.2f}")
        f3.info(f"**עמלות ברוקר:** ${(acts+1)*1.0:,.2f}")
    else:
        st.title("Admin - כל התיקים")
        st.dataframe(df)
