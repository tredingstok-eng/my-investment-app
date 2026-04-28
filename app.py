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
APP_CONFIG = {
    "TITLE": "RC Capital Management",
    "ADMIN_CODE": "0000",
    "NO_FEE_USER": "רפאל כהן",
    "REFRESH_RATE": 120
}
FEES = {"TAX": 0.25, "SUCCESS": 0.20, "ACTION": 1.0}
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

# --- עיצוב פרימיום ---
st.set_page_config(page_title=APP_CONFIG["TITLE"], page_icon="🏦", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0d12; color: #e0e0e0; }
    div[data-testid="stMetricValue"] { color: #d4af37 !important; font-size: 35px !important; }
    .auth-card { background-color: #11141a; padding: 40px; border-radius: 20px; border: 1px solid #d4af37; text-align: center; max-width: 450px; margin: auto; }
    .stButton>button { background: linear-gradient(90deg, #d4af37, #f9e29d); color: black; font-weight: bold; width: 100%; border-radius: 10px; }
    .premium-divider { height: 2px; background: linear-gradient(90deg, transparent, #d4af37, transparent); margin: 20px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- פונקציות עזר ---
def clean_num(val):
    try:
        if pd.isna(val): return 0.0
        return float(str(val).replace('$', '').replace('%', '').replace(',', '').strip())
    except: return 0.0

@st.cache_data(ttl=120)
def get_data():
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        return df.fillna(0)
    except: return None

@st.cache_data(ttl=120)
def get_ibkr():
    try:
        url = f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_CONFIG['TOKEN']}&q={IB_CONFIG['QUERY_ID']}&v=3"
        res = requests.get(url, timeout=10)
        root = ET.fromstring(res.content)
        if root.find("Status").text == "Success":
            ref = root.find("ReferenceCode").text
            time.sleep(1)
            data_res = requests.get(f"{root.find('Url').text}?q={ref}&t={IB_CONFIG['TOKEN']}")
            nav = ET.fromstring(data_res.content).find(".//NetAssetValue")
            if nav is not None: return float(nav.get("total"))
    except: pass
    return 6131.72

def calc_client(name, inv, gross, acts):
    action_fees = (acts + 1) * FEES["ACTION"]
    profit_raw = gross - inv - action_fees
    tax, succ = (profit_raw * FEES["TAX"], (profit_raw * 0.75) * FEES["SUCCESS"]) if profit_raw > 0 and name != APP_CONFIG["NO_FEE_USER"] else (0, 0)
    net = gross - tax - succ - (action_fees if name != APP_CONFIG["NO_FEE_USER"] else 0)
    return {"net": net, "profit": net - inv, "perc": ((net-inv)/inv*100) if inv > 0 else 0, "tax": tax, "succ": succ, "gross": gross}

# --- לוגיקה מרכזית ---
if 'auth' not in st.session_state: st.session_state.auth = False

df = get_data()
ib_val = get_ibkr()

if not st.session_state.auth:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="auth-card"><h1>🏦 RC Capital</h1><p>Private Portal</p>', unsafe_allow_html=True)
        pwd = st.text_input("Enter PIN:", type="password")
        if st.button("Login"):
            if pwd == APP_CONFIG["ADMIN_CODE"]:
                st.session_state.auth, st.session_state.role = True, "admin"
                st.rerun()
            elif df is not None and str(pwd) in df.iloc[:, 1].astype(str).values:
                st.session_state.auth, st.session_state.role, st.session_state.pwd = True, "client", str(pwd)
                st.rerun()
            else: st.error("Invalid PIN")
        st.markdown('</div>', unsafe_allow_html=True)
else:
    if st.sidebar.button("Logout"):
        st.session_state.auth = False
        st.rerun()

    if st.session_state.role == "admin":
        st.title("💼 Admin Dashboard")
        total_inv = sum([clean_num(x) for x in df.iloc[:, 2]])
        c1, c2, c3 = st.columns(3)
        c1.metric("Total NAV (IBKR)", f"${ib_val:,.2f}")
        c2.metric("Total Deposits", f"${total_inv:,.2f}")
        c3.metric("Overall Return", f"{((ib_val-total_inv)/total_inv*100):.2f}%")
        st.write("### Clients Overview")
        st.dataframe(df.iloc[:, [0, 2, 3]], use_container_width=True)

    else:
        user_data = df[df.iloc[:, 1].astype(str) == st.session_state.pwd].iloc[0]
        name, inv, share, acts = user_data.iloc[0], clean_num(user_data.iloc[2]), clean_num(user_data.iloc[3]), clean_num(user_data.iloc[4])
        m = calc_client(name, inv, ib_val * (share/100), acts)

        st.title(f"Hello, {name}")
        st.markdown("<div class='premium-divider'></div>", unsafe_allow_html=True)

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Net Balance", f"${m['net']:,.2f}")
        col_b.metric("Profit/Loss", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
        col_c.metric("Portfolio Share", f"{share}%")

        st.write("---")
        c_left, c_right = st.columns([2, 1])
        with c_left:
            # גרף צמיחה
            fig = px.area(x=["Deposit", "Current Net"], y=[inv, m['net']], title="Wealth Growth", color_discrete_sequence=['#d4af37'])
            fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
            st.plotly_chart(fig, use_container_width=True)
        with c_right:
            # גרף Waterfall של עמלות
            fig2 = go.Figure(go.Waterfall(
                orientation="v",
                measure=["relative", "relative", "relative", "total"],
                x=["Gross", "Tax", "Fees", "Net"],
                y=[m['gross'], -m['tax'], -m['succ'], 0],
                connector={"line":{"color":"#374151"}},
                decreasing={"marker":{"color":"#ef4444"}},
                totals={"marker":{"color":"#d4af37"}}
            ))
            fig2.update_layout(title="Fee Breakdown", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
            st.plotly_chart(fig2, use_container_width=True)
