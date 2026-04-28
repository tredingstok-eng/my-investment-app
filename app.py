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

# עיצוב פרימיום
st.set_page_config(page_title="RC Capital Management", page_icon="🏦", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #e0e0e0; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; }
    div[data-testid="stMetricValue"] { color: #d4af37 !important; font-weight: bold; }
    .auth-card { background-color: #161b22; padding: 50px; border-radius: 20px; border: 1px solid #d4af37; text-align: center; max-width: 500px; margin: auto; }
    .stButton>button { background: linear-gradient(90deg, #d4af37 0%, #f9e29d 100%); color: black; font-weight: bold; border: none; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=120)
def get_ibkr_value():
    try:
        url = f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY_ID}&v=3"
        res = requests.get(url, timeout=15)
        root = ET.fromstring(res.content)
        if root.find("Status").text == "Success":
            code = root.find("ReferenceCode").text
            base_url = root.find("Url").text
            time.sleep(1.5)
            data_res = requests.get(f"{base_url}?q={code}&t={IB_TOKEN}", timeout=15)
            data_root = ET.fromstring(data_res.content)
            nav = data_root.find(".//NetAssetValue")
            if nav is not None: return float(nav.get("total"))
    except: return None
    return None

def load_data():
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        return df.fillna(0) # מחליף תאים ריקים ב-0 כדי למנוע שגיאות
    except: return None

def calc_metrics(name, inv, gross, acts):
    fees = (float(acts) + 1) * ACTION_FEE
    profit = gross - inv - fees
    tax, comm = (profit * TAX_RATE, (profit * 0.75) * SUCCESS_FEE) if profit > 0 and name != NO_FEE_USER else (0, 0)
    net = gross - tax - comm - (fees if name != NO_FEE_USER else 0)
    return {"net": net, "profit": net - inv, "perc": (net-inv)/inv*100 if inv>0 else 0}

# --- לוגיקה ---
if 'auth_status' not in st.session_state: st.session_state.auth_status = False

df = load_data()
current_val = get_ibkr_value() or 6131.72

if not st.session_state.auth_status:
    st.markdown("<br><br>", unsafe_allow_html=True)
    with st.container():
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="auth-card">', unsafe_allow_html=True)
            st.title("🏦 RC Capital")
            st.markdown("### Private Investment Portal")
            pwd = st.text_input("קוד גישה אישי:", type="password")
            if st.button("התחבר למערכת"):
                if str(pwd) == ADMIN_CODE or (df is not None and str(pwd) in df.iloc[:, 1].astype(str).values):
                    st.session_state.auth_status = True
                    st.session_state.pwd = str(pwd)
                    st.rerun()
                else: st.error("קוד שגוי")
            st.markdown('</div>', unsafe_allow_html=True)
else:
    # ממשק פנימי
    st.sidebar.title("RC Control")
    if st.sidebar.button("התנתק"):
        st.session_state.auth_status = False
        st.rerun()

    # מצב מנהל
    if st.session_state.pwd == ADMIN_CODE:
        st.header("💼 ניהול תיק השקעות - רפאל כהן")
        total_inv = pd.to_numeric(df.iloc[:, 2], errors='coerce').sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("שווי תיק (IBKR)", f"${current_val:,.2f}")
        c2.metric("סך הפקדות", f"${total_inv:,.2f}")
        c3.metric("תשואה", f"{((current_val-total_inv)/total_inv*100):.2f}%")
        
        st.write("---")
        st.subheader("פירוט לפי לקוח")
        st.dataframe(df.iloc[:, [0, 2, 3]], use_container_width=True)

    # מצב לקוח
    else:
        user_row = df[df.iloc[:, 1].astype(str) == st.session_state.pwd].iloc[0]
        name, inv, share, acts = user_row[0], float(user_row[2]), float(str(user_row[3]).replace('%','')), user_row[4]
        m = calc_metrics(name, inv, current_val * (share/100), acts)

        st.title(f"שלום, {name}")
        st.markdown(f"**עדכון תיק:** {time.strftime('%d/%m/%Y')}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("שווי נטו", f"${m['net']:,.2f}")
        c2.metric("רווח/הפסד", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
        c3.metric("חלק בקרן", f"{share}%")

        col_l, col_r = st.columns([2, 1])
        with col_l:
            fig = px.area(x=["הפקדה", "שווי נוכחי"], y=[inv, m['net']], title="צמיחת ההון", color_discrete_sequence=['#d4af37'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
            st.plotly_chart(fig, use_container_width=True)
        with col_r:
            fig2 = px.pie(values=[share, 100-share], names=["חלקך", "אחרים"], hole=0.6, title="חלוקת בעלות", color_discrete_sequence=['#d4af37', '#1c1f26'])
            st.plotly_chart(fig2, use_container_width=True)
