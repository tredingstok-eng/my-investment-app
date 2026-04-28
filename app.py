import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime

# --- CONFIGURATION ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1489351"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"
ADMIN_PIN = "0000"

# --- STYLING ---
st.set_page_config(page_title="RC Capital Elite", page_icon="🏆", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@200;400;700&display=swap');
    * { font-family: 'Assistant', sans-serif; direction: rtl; }
    .main { background-color: #050505; color: #ffffff; }
    .stMetric { background: linear-gradient(145deg, #111, #1a1a1a); border: 1px solid #d4af37; padding: 25px; border-radius: 20px; box-shadow: 0 10px 20px rgba(0,0,0,0.5); }
    div[data-testid="stMetricValue"] { color: #d4af37 !important; font-weight: 700; font-size: 35px !important; }
    .auth-container { background: #111; padding: 60px; border-radius: 30px; border: 1px solid #d4af37; text-align: center; max-width: 500px; margin: 100px auto; }
    .stButton>button { background: linear-gradient(90deg, #d4af37, #f9e29d); color: black; font-weight: bold; border-radius: 12px; height: 50px; border: none; width: 100%; transition: 0.3s; }
    .stButton>button:hover { transform: translateY(-3px); box-shadow: 0 5px 15px rgba(212,175,55,0.4); }
    .sidebar-content { background-color: #111; padding: 20px; border-radius: 15px; border: 1px solid #333; }
    </style>
    """, unsafe_allow_html=True)

# --- DATA ENGINE ---
def safe_num(v):
    try:
        if pd.isna(v): return 0.0
        return float(str(v).replace('$', '').replace('%', '').replace(',', '').strip())
    except: return 0.0

@st.cache_data(ttl=60)
def fetch_data():
    try:
        # קריאת הגיליון
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        # קריאת IBKR
        nav = 6131.72
        try:
            r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=5)
            root = ET.fromstring(r.content)
            if root.find("Status").text == "Success":
                time.sleep(1)
                d_r = requests.get(f"{root.find('Url').text}?q={root.find('ReferenceCode').text}&t={IB_TOKEN}")
                nav = float(ET.fromstring(d_r.content).find(".//NetAssetValue").get("total"))
        except: pass
        return df, nav
    except: return None, 6131.72

def get_stats(name, inv, share, acts, total_nav):
    gross = total_nav * (share / 100.0)
    fees = (acts + 1) * 1.0 # $1 לכל פעולה
    profit_pre = gross - inv - fees
    tax, succ = (profit_pre * 0.25, (profit_pre * 0.75) * 0.20) if profit_pre > 0 and name != "רפאל כהן" else (0, 0)
    net = gross - tax - succ - (fees if name != "רפאל כהן" else 0)
    return {"net": net, "profit": net - inv, "perc": (net-inv)/inv*100 if inv>0 else 0, "tax": tax, "succ": succ, "gross": gross}

# --- APP LOGIC ---
df, nav_total = fetch_data()

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135706.png", width=80)
    st.title("RC CAPITAL")
    st.write("מערכת ניהול השקעות פרימיום")
    pin = st.text_input("הזן קוד זיהוי:", type="password")
    if st.button("כניסה למערכת"):
        if pin == ADMIN_PIN:
            st.session_state.auth, st.session_state.role = True, "admin"
            st.rerun()
        elif df is not None:
            # בדיקת סיסמה בעמודה השנייה (אינדקס 1)
            all_pins = df.iloc[:, 1].astype(str).tolist()
            if pin in all_pins:
                st.session_state.auth, st.session_state.role, st.session_state.user_pin = True, "user", pin
                st.rerun()
            else: st.error("קוד שגוי")
    st.markdown('</div>', unsafe_allow_html=True)

else:
    with st.sidebar:
        st.markdown("### RC Capital Elite")
        st.write(f"שווי תיק: ${nav_total:,.2f}")
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    if st.session_state.role == "admin":
        st.header("💼 לוח ניהול מרכזי")
        total_dep = sum([safe_num(x) for x in df.iloc[:, 2]])
        c1, c2, c3 = st.columns(3)
        c1.metric("נכסים בניהול", f"${nav_total:,.2f}")
        c2.metric("סך הפקדות", f"${total_dep:,.2f}")
        c3.metric("תשואת קרן", f"{((nav_total-total_dep)/total_dep*100):.2f}%")
        
        st.write("---")
        st.subheader("פירוט משקיעים")
        res = []
        for _, r in df.iterrows():
            m = get_stats(r.iloc[0], safe_num(r.iloc[2]), safe_num(r.iloc[3]), safe_num(r.iloc[4]), nav_total)
            res.append({"שם": r.iloc[0], "הפקדה": f"${safe_num(r.iloc[2]):,.0f}", "נטו": f"${m['net']:,.2f}", "רווח %": f"{m['perc']:.2f}%"})
        st.dataframe(pd.DataFrame(res), use_container_width=True)

    else:
        # תצוגת לקוח - שליפה לפי אינדקסים כדי למנוע KeyError
        user_row = df[df.iloc[:, 1].astype(str) == st.session_state.user_pin].iloc[0]
        name = user_row.iloc[0]
        inv = safe_num(user_row.iloc[2])
        share = safe_num(user_row.iloc[3])
        acts = safe_num(user_row.iloc[4])
        
        m = get_stats(name, inv, share, acts, nav_total)

        st.title(f"שלום, {name} 👋")
        st.write(f"עדכון נכון ל: {datetime.now().strftime('%H:%M | %d/%m/%Y')}")
        
        # כרטיסי מידע יוקרתיים
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("יתרה נטו למשיכה", f"${m['net']:,.2f}")
        with col2:
            st.metric("רווח/הפסד נקי", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
        with col3:
            st.metric("נתח בתיק הכללי", f"{share}%")

        st.write("---")
        
        c_left, c_right = st.columns([2, 1])
        with c_left:
            st.subheader("📈 מגמת צמיחה")
            fig = px.area(x=["הפקדה", "יתרה נוכחית"], y=[inv, m['net']], color_discrete_sequence=['#d4af37'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white", xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)
            
        with c_right:
            st.subheader("🧾 פירוט מאזן")
            fig2 = go.Figure(go.Waterfall(
                orientation="v",
                measure=["relative", "relative", "relative", "total"],
                x=["שווי ברוטו", "מס", "עמלות", "נטו"],
                y=[m['gross'], -m['tax'], -m['succ'], 0],
                connector={"line":{"color":"#444"}},
                decreasing={"marker":{"color":"#ff4b4b"}},
                totals={"marker":{"color":"#d4af37"}}
            ))
            fig2.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white", showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        with st.expander("📝 דוח שקיפות מלא"):
            st.write(f"שווי ברוטו: **${m['gross']:,.2f}**")
            st.write(f"הפרשה למס (25% מהרווח): **${m['tax']:,.2f}**")
            st.write(f"עמלת הצלחה (20% מהנטו): **${m['succ']:,.2f}**")
            st.caption("הנתונים נמשכים ישירות מ-IBKR ומבוססים על אחוז הבעלות המוגדר בגיליון.")
