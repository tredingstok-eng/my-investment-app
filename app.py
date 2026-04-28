import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות מערכת ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY_ID = "1489351"
ADMIN_CODE = "0000"
NO_FEE_USER = "רפאל כהן"
TAX_RATE, SUCCESS_FEE, ACTION_FEE = 0.25, 0.20, 1.0
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", page_icon="📈", layout="wide")

# עיצוב CSS למראה מודרני
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; }
    .auth-container { max-width: 400px; margin: auto; padding-top: 100px; text-align: center; }
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
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        df.columns = df.columns.str.strip()
        return df
    except: return None

def calc_metrics(name, inv, gross, acts):
    fees = (acts + 1) * ACTION_FEE
    profit = gross - inv - fees
    tax, comm = (profit * TAX_RATE, (profit * 0.75) * SUCCESS_FEE) if profit > 0 and name != NO_FEE_USER else (0, 0)
    net = gross - tax - comm - (fees if name != NO_FEE_USER else 0)
    return {"net": net, "profit": net - inv, "perc": (net-inv)/inv*100 if inv>0 else 0, "gross": gross}

# --- לוגיקת כניסה ---
if 'auth' not in st.session_state: st.session_state.auth = False

df = load_data()
ib_val = get_ibkr_value() or 6131.72

if not st.session_state.auth:
    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.title("RC Capital")
    st.write("ברוכים הבאים למערכת ניהול ההשקעות")
    pwd = st.text_input("הכנס קוד גישה:", type="password")
    if st.button("התחבר"):
        if pwd == ADMIN_CODE or (df is not None and str(pwd) in df.iloc[:, 1].astype(str).values):
            st.session_state.auth = True
            st.session_state.pwd = pwd
            st.rerun()
        else: st.error("קוד שגוי")
    st.markdown('</div>', unsafe_allow_html=True)

else:
    if st.sidebar.button("יציאה"):
        st.session_state.auth = False
        st.rerun()

    # תצוגת מנהל
    if st.session_state.pwd == ADMIN_CODE:
        st.title("📊 לוח בקרה - רפאל כהן")
        total_inv = df.iloc[:, 2].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("שווי כולל (IBKR)", f"${ib_val:,.2f}")
        c2.metric("סה\"כ הפקדות", f"${total_inv:,.2f}")
        c3.metric("תשואה כוללת", f"{((ib_val-total_inv)/total_inv*100):.2f}%")
        
        st.write("### פירוט תיקי לקוחות")
        summary = []
        for _, r in df.iterrows():
            m = calc_metrics(r[0], float(r[2]), ib_val * (float(str(r[3]).replace('%',''))/100), int(r[4]))
            summary.append({"לקוח": r[0], "הפקדה": f"${r[2]:,.0f}", "יתרה נטו": f"${m['net']:,.2f}", "רווח": f"{m['perc']:.1f}%"})
        st.table(pd.DataFrame(summary))

    # תצוגת לקוח
    else:
        user_row = df[df.iloc[:, 1].astype(str) == st.session_state.pwd].iloc[0]
        name, inv, share = user_row[0], float(user_row[2]), float(str(user_row[3]).replace('%',''))
        m = calc_metrics(name, inv, ib_val * (share/100), int(user_row[4]))

        st.title(f"שלום, {name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("יתרה נטו", f"${m['net']:,.2f}")
        c2.metric("רווח/הפסד", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
        c3.metric("נתח מהתיק", f"{share}%")

        col_l, col_r = st.columns([2, 1])
        with col_l:
            st.plotly_chart(px.area(x=["הפקדה", "נוכחי"], y=[inv, m['net']], title="צמיחת ההשקעה", color_discrete_sequence=['#2ecc71']), use_container_width=True)
        with col_r:
            st.plotly_chart(px.pie(values=[share, 100-share], names=["חלקך", "אחרים"], hole=0.5, title="פיזור בקרן"), use_container_width=True)
