import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime

# --- הגדרות ליבה ---
IB_CONFIG = {"TOKEN": "837126977366730658372732", "QUERY_ID": "1489351"}
APP_NAME = "RC Capital | ניהול השקעות פרימיום"
ADMIN_CODE = "0000"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

# הגדרות מס וניהול
TAX_RATE = 0.25      # 25% מס רווח הון
SUCCESS_FEE = 0.20   # 20% עמלת הצלחה
BROKER_FEE = 1.0     # $1 עמלת פעולה

st.set_page_config(page_title=APP_NAME, page_icon="📈", layout="wide")

# --- עיצוב CSS מותאם אישית (יוקרה כהה) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Assistant', sans-serif; direction: rtl; text-align: right; }
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { background-color: #1c1f26; border: 1px solid #2d3139; padding: 20px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
    div[data-testid="stMetricValue"] { font-size: 30px !important; color: #d4af37 !important; }
    .auth-box { background-color: #1c1f26; padding: 50px; border-radius: 25px; border: 1px solid #d4af37; text-align: center; max-width: 450px; margin: auto; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
    .stButton>button { background: linear-gradient(135deg, #d4af37 0%, #b8860b 100%); color: #000; font-weight: bold; border: none; border-radius: 10px; padding: 12px; transition: 0.3s; width: 100%; }
    .stButton>button:hover { transform: scale(1.02); box-shadow: 0 5px 15px rgba(212,175,55,0.4); }
    .status-tag { padding: 5px 15px; border-radius: 20px; font-size: 12px; background: #2d3139; color: #d4af37; border: 1px solid #d4af37; }
    </style>
    """, unsafe_allow_html=True)

# --- פונקציות עיבוד נתונים ---
def clean_val(val):
    try:
        if pd.isna(val): return 0.0
        return float(str(val).replace('$', '').replace('%', '').replace(',', '').strip())
    except: return 0.0

@st.cache_data(ttl=60)
def load_all_data():
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        df = df.fillna(0)
        # משיכת שווי מאינטראקטיב (או ערך ברירת מחדל אם נכשל)
        nav = 6131.72
        try:
            r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_CONFIG['TOKEN']}&q={IB_CONFIG['QUERY_ID']}&v=3", timeout=5)
            root = ET.fromstring(r.content)
            if root.find("Status").text == "Success":
                ref = root.find("ReferenceCode").text
                time.sleep(1)
                d_r = requests.get(f"{root.find('Url').text}?q={ref}&t={IB_CONFIG['TOKEN']}")
                nav = float(ET.fromstring(d_r.content).find(".//NetAssetValue").get("total"))
        except: pass
        return df, nav
    except: return None, 6131.72

def calculate_full_metrics(name, deposited, share_perc, actions, total_nav):
    gross_value = total_nav * (share_perc / 100.0)
    broker_costs = (actions + 1) * BROKER_FEE
    profit_before_tax = gross_value - deposited - broker_costs
    
    if name == "רפאל כהן" or profit_before_tax <= 0:
        tax, management_fee = 0.0, 0.0
    else:
        tax = profit_before_tax * TAX_RATE
        management_fee = (profit_before_tax - tax) * SUCCESS_FEE
        
    net_value = gross_value - tax - management_fee - (broker_costs if name != "רפאל כהן" else 0)
    profit_net = net_value - deposited
    return {
        "gross": gross_value, "tax": tax, "mgt": management_fee, "broker": broker_costs,
        "net": net_value, "profit": profit_net, "perc": (profit_net / deposited * 100) if deposited > 0 else 0
    }

# --- לוגיקת האפליקציה ---
df, current_nav = load_all_data()

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="auth-box">', unsafe_allow_html=True)
        st.image("https://cdn-icons-png.flaticon.com/512/3135/3135706.png", width=70)
        st.markdown("<h2 style='color:white;'>כניסה למערכת RC Capital</h2>", unsafe_allow_html=True)
        pin = st.text_input("הזן קוד PIN אישי:", type="password")
        if st.button("התחבר למרכז ההשקעות"):
            if pin == ADMIN_CODE:
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif df is not None and str(pin) in df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pin = True, "client", str(pin)
                st.rerun()
            else: st.error("❌ קוד שגוי, נסה שוב")
        st.markdown('</div>', unsafe_allow_html=True)
else:
    # סרגל צד מעוצב
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.markdown(f"<span class='status-tag'>סטטוס תיק: פעיל 🟢</span>", unsafe_allow_html=True)
        st.write("---")
        if st.button("התנתק מהמערכת"):
            st.session_state.auth = False
            st.rerun()

    # --- תצוגת מנהל ---
    if st.session_state.role == "admin":
        st.title("💼 לוח בקרה - מנהל קרן")
        total_deposited = sum([clean_val(x) for x in df.iloc[:, 2]])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("שווי כולל (IBKR)", f"${current_nav:,.2f}")
        c2.metric("סך הפקדות", f"${total_deposited:,.2f}")
        c3.metric("תשואה כוללת", f"{((current_nav-total_deposited)/total_deposited*100):.2f}%")
        
        st.write("### רשימת לקוחות וביצועים")
        rows = []
        for _, r in df.iterrows():
            m = calculate_full_metrics(r[0], clean_val(r[2]), clean_val(r[3]), clean_val(r[4]), current_nav)
            rows.append({"לקוח": r[0], "הפקדה": f"${r[2]:,.0f}", "יתרה נטו": f"${m['net']:,.2f}", "רווח %": f"{m['perc']:.2f}%"})
        st.table(pd.DataFrame(rows))

    # --- תצוגת לקוח ---
    else:
        user = df[df.iloc[:, 1].astype(str) == st.session_state.pin].iloc[0]
        m = calculate_full_metrics(user[0], clean_val(user[2]), clean_val(user[3]), clean_val(user[4]), current_nav)
        
        st.title(f"שלום, {user[0]} 👋")
        st.markdown(f"עדכון נתונים נכון ליום: {datetime.now().strftime('%d/%m/%Y')}")
        st.write("---")
        
        # כרטיסי מידע ראשיים
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("יתרה נטו למשיכה", f"${m['net']:,.2f}")
        with col2:
            st.metric("רווח/הפסד נקי", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
        with col3:
            st.metric("נתח מהתיק הכללי", f"{user[3]}%")
            
        st.write("---")
        
        # גרפים וניתוחים
        g_col1, g_col2 = st.columns([2, 1])
        with g_col1:
            st.markdown("### צמיחת ההשקעה")
            fig = px.area(x=["הפקדה", "נוכחי (נטו)"], y=[clean_val(user[2]), m['net']], color_discrete_sequence=['#d4af37'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white", xaxis_title="", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
            
        with g_col2:
            st.markdown("### פירוט עמלות ומיסים")
            fig2 = go.Figure(go.Waterfall(
                orientation="v",
                measure=["relative", "relative", "relative", "total"],
                x=["שווי ברוטו", "מס (25%)", "עמלת ניהול", "יתרת נטו"],
                y=[m['gross'], -m['tax'], -m['mgt'], 0],
                connector={"line":{"color":"#555"}},
                decreasing={"marker":{"color":"#ef4444"}},
                totals={"marker":{"color":"#d4af37"}}
            ))
            fig2.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white", showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        with st.expander("🔍 הצג פירוט חשבונאי מלא"):
            st.write(f"**שווי ברוטו בבורסה:** ${m['gross']:,.2f}")
            st.write(f"**הפרשה למס רווח הון:** ${m['tax']:,.2f}")
            st.write(f"**עמלת הצלחה (20% מהרווח נטו):** ${m['mgt']:,.2f}")
            st.write(f"**עמלות ברוקר מצטברות:** ${m['broker']:,.2f}")
            st.caption("החישובים מבוצעים בזמן אמת בהתאם לשער הדולר וביצועי התיק באינטראקטיב ברוקרס.")
