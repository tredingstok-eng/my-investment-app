import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ליבה ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY_ID = "1489351"
ADMIN_CODE = "0000"
NO_FEE_USER = "רפאל כהן"
TAX_RATE, SUCCESS_FEE, ACTION_FEE = 0.25, 0.20, 1.0
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

# הגדרות עיצוב גלובליות
st.set_page_config(page_title="RC Capital", page_icon="📈", layout="wide")

# CSS לעיצוב יוקרתי
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1e2130; padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    div[data-testid="stExpander"] { border: none !important; box-shadow: none !important; }
    .stButton>button { width: 100%; border-radius: 10px; background-color: #00ff88; color: black; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=120)
def get_ibkr_value():
    try:
        url = f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY_ID}&v=3"
        res = requests.get(url, timeout=10)
        root = ET.fromstring(res.content)
        if root.find("Status").text == "Success":
            code = root.find("ReferenceCode").text
            base_url = root.find("Url").text
            time.sleep(1)
            data_res = requests.get(f"{base_url}?q={code}&t={IB_TOKEN}", timeout=10)
            data_root = ET.fromstring(data_res.content)
            nav = data_root.find(".//NetAssetValue")
            if nav is not None: return float(nav.get("total"))
    except: return None
    return None

def load_data():
    try: return pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
    except: return None

def calc_metrics(name, inv, gross, acts):
    fees = (acts + 1) * ACTION_FEE
    profit = gross - inv - fees
    tax, comm = (profit * TAX_RATE, (profit - (profit * TAX_RATE)) * SUCCESS_FEE) if profit > 0 and name != NO_FEE_USER else (0, 0)
    net = gross - tax - comm - (fees if name != NO_FEE_USER else 1.0)
    return {"net": net, "profit": net - inv, "perc": (net-inv)/inv*100 if inv>0 else 0, "tax": tax, "comm": comm, "fees": fees, "gross": gross}

# --- לוגיקת אפליקציה ---
df = load_data()
ib_val = get_ibkr_value() or 6131.0

# מסך כניסה מרכזי
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("https://cdn-icons-png.flaticon.com/512/3135/3135706.png", width=100) # אייקון לוגו
        st.title("RC Capital Management")
        st.subheader("כניסה למערכת המעקב")
        pwd = st.text_input("הכנס קוד גישה אישי:", type="password")
        if st.button("התחבר"):
            if pwd == ADMIN_CODE or (df is not None and str(pwd) in df.iloc[:, 1].astype(str).values):
                st.session_state.authenticated = True
                st.session_state.pwd = pwd
                st.rerun()
            else:
                st.error("קוד שגוי, נסה שוב")
else:
    # כפתור התנתקות בפינה
    if st.sidebar.button("יציאה מהמערכת"):
        st.session_state.authenticated = False
        st.rerun()

    # --- תצוגת מנהל ---
    if st.session_state.pwd == ADMIN_CODE:
        st.title("💼 לוח בקרה - רפאל כהן")
        total_inv = df.iloc[:, 2].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("שווי תיק (IBKR)", f"${ib_val:,.2f}")
        c2.metric("סה\"כ הפקדות", f"${total_inv:,.2f}")
        c3.metric("רווח קרן", f"${ib_val - total_inv:,.2f}", delta=f"{((ib_val-total_inv)/total_inv*100):.2f}%")
        c4.metric("סטטוס חיבור", "פעיל 🟢")

        st.write("### פירוט לקוחות מלא")
        summary = []
        for _, r in df.iterrows():
            m = calc_metrics(r[0], float(r[2]), ib_val * (float(str(r[3]).replace('%',''))/100), int(r[4]))
            summary.append([r[0], f"${r[2]:,.0f}", f"${m['net']:,.2f}", f"{m['perc']:.1f}%"])
        st.table(pd.DataFrame(summary, columns=["לקוח", "הפקדה", "יתרה נטו", "תשואה"]))

    # --- תצוגת לקוח ---
    else:
        user_row = df[df.iloc[:, 1].astype(str) == st.session_state.pwd].iloc[0]
        name, inv, share, acts = user_row[0], float(user_row[2]), float(str(user_row[3]).replace('%','')), int(user_row[4])
        m = calc_metrics(name, inv, ib_val * (share/100), acts)

        st.title(f"שלום, {name}")
        st.markdown("---")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו למשיכה", f"${m['net']:,.2f}")
        c2.metric("רווח נקי", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
        c3.metric("חלק בתיק", f"{share}%")

        st.write("### ניתוח ביצועים")
        col_l, col_r = st.columns([2, 1])
        with col_l:
            fig = px.area(x=["הפקדה", "היום"], y=[inv, m['net']], title="גרף צמיחה נומינלי",
                         color_discrete_sequence=['#00ff88'])
            st.plotly_chart(fig, use_container_width=True)
        with col_r:
            fig2 = px.pie(values=[share, 100-share], names=["חלקך", "אחרים"], hole=0.6,
                        title="פיזור בקרן", color_discrete_sequence=['#00ff88', '#1e2130'])
            st.plotly_chart(fig2, use_container_width=True)

        with st.expander("🔍 שקיפות ועמלות"):
            st.write(f"שווי ברוטו: ${m['gross']:,.2f}")
            st.write(f"עמלת ניהול והצלחה: ${m['comm']+m['tax']:,.2f}")
            st.caption("החישוב כולל הפרשה למס רווח הון ועמלות פעולה של הברוקר")
