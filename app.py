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

st.set_page_config(page_title="RC Capital", page_icon="🏦", layout="wide")

# עיצוב פרימיום
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #e0e0e0; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; }
    div[data-testid="stMetricValue"] { color: #d4af37 !important; }
    .auth-card { background-color: #161b22; padding: 40px; border-radius: 20px; border: 1px solid #d4af37; text-align: center; max-width: 450px; margin: auto; }
    .stButton>button { background: linear-gradient(90deg, #d4af37 0%, #f9e29d 100%); color: black; font-weight: bold; }
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
    except: return 6131.72
    return 6131.72

def clean_num(val):
    """מנקה תווים לא רצויים מהמספרים בגיליון"""
    try:
        if pd.isna(val): return 0.0
        s = str(val).replace('$', '').replace('%', '').replace(',', '').strip()
        return float(s)
    except: return 0.0

def load_data():
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        return df
    except: return None

def calc_metrics(name, inv, gross, acts):
    fees = (clean_num(acts) + 1) * ACTION_FEE
    profit = gross - inv - fees
    tax, comm = (profit * TAX_RATE, (profit * 0.75) * SUCCESS_FEE) if profit > 0 and name != NO_FEE_USER else (0, 0)
    net = gross - tax - comm - (fees if name != NO_FEE_USER else 0)
    return {"net": net, "profit": net - inv, "perc": (net-inv)/inv*100 if inv>0 else 0}

# --- לוגיקה ---
if 'auth' not in st.session_state: st.session_state.auth = False

df = load_data()
current_val = get_ibkr_value()

if not st.session_state.auth:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        st.title("🏦 RC Capital")
        pwd = st.text_input("קוד גישה:", type="password")
        if st.button("כניסה"):
            if str(pwd) == ADMIN_CODE or (df is not None and str(pwd) in df.iloc[:, 1].astype(str).values):
                st.session_state.auth = True
                st.session_state.pwd = str(pwd)
                st.rerun()
            else: st.error("קוד שגוי")
        st.markdown('</div>', unsafe_allow_html=True)
else:
    if st.sidebar.button("התנתק"):
        st.session_state.auth = False
        st.rerun()

    if df is not None:
        # מצב מנהל
        if st.session_state.pwd == ADMIN_CODE:
            st.header("💼 לוח מנהל")
            total_inv = sum([clean_num(x) for x in df.iloc[:, 2]])
            st.metric("שווי תיק כולל", f"${current_val:,.2f}")
            st.write("### רשימת משקיעים")
            st.dataframe(df.iloc[:, [0, 2, 3]])

        # מצב לקוח
        else:
            try:
                user_row = df[df.iloc[:, 1].astype(str) == st.session_state.pwd].iloc[0]
                name = str(user_row[0])
                inv = clean_num(user_row[2])
                share = clean_num(user_row[3])
                acts = clean_num(user_row[4])
                
                m = calc_metrics(name, inv, current_val * (share/100), acts)

                st.title(f"שלום, {name}")
                c1, c2, c3 = st.columns(3)
                c1.metric("שווי נטו", f"${m['net']:,.2f}")
                c2.metric("רווח/הפסד", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
                c3.metric("נתח בקרן", f"{share}%")

                col_l, col_r = st.columns([2, 1])
                with col_l:
                    st.plotly_chart(px.area(x=["הפקדה", "נוכחי"], y=[inv, m['net']], title="צמיחת הון", color_discrete_sequence=['#d4af37']), use_container_width=True)
                with col_r:
                    st.plotly_chart(px.pie(values=[share, 100-share], names=["חלקך", "אחרים"], hole=0.6, color_discrete_sequence=['#d4af37', '#1c1f26']), use_container_width=True)
            except Exception as e:
                st.error(f"נראה שיש בעיה בנתוני המשתמש בגיליון. וודא שהעמודות מלאות כראוי.")
