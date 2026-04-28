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

# הגדרת דף ועיצוב יוקרתי
st.set_page_config(page_title="RC Capital | פרימיום", page_icon="💎", layout="wide")

st.markdown("""
    <style>
    .main { background: linear-gradient(180deg, #0e1117 0%, #161b22 100%); color: white; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #00ff88 !important; }
    .stButton>button { background-color: #00ff88; color: black; font-weight: bold; border-radius: 8px; border: none; padding: 10px 20px; width: 100%; }
    .auth-box { background-color: #1e2130; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); text-align: center; max-width: 450px; margin: auto; border: 1px solid #30363d; }
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
        df = df.dropna(subset=[df.columns[0], df.columns[1]]) # ניקוי שורות ריקות
        return df
    except: return None

def calc_metrics(name, inv, gross, acts):
    fees = (acts + 1) * ACTION_FEE
    profit = gross - inv - fees
    tax, comm = (profit * TAX_RATE, (profit * 0.75) * SUCCESS_FEE) if profit > 0 and name != NO_FEE_USER else (0, 0)
    net = gross - tax - comm - (fees if name != NO_FEE_USER else 0)
    return {"net": net, "profit": net - inv, "perc": (net-inv)/inv*100 if inv>0 else 0, "gross": gross}

# --- לוגיקה ראשית ---
if 'auth' not in st.session_state: st.session_state.auth = False

df = load_data()
current_portfolio_value = get_ibkr_value() or 6131.72

# מסך כניסה
if not st.session_state.auth:
    st.markdown('<div style="padding-top: 100px;"></div>', unsafe_allow_html=True)
    with st.container():
        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col2:
            st.markdown(f"""
                <div class="auth-box">
                    <h1 style="color: #00ff88; margin-bottom: 10px;">RC Capital</h1>
                    <p style="color: #8b949e; margin-bottom: 30px;">Private Investment Portal</p>
                </div>
            """, unsafe_allow_html=True)
            pwd = st.text_input("קוד גישה:", type="password", help="הזן את הקוד האישי שלך")
            if st.button("כניסה למערכת"):
                if str(pwd) == ADMIN_CODE or (df is not None and str(pwd) in df.iloc[:, 1].astype(str).values):
                    st.session_state.auth = True
                    st.session_state.pwd = str(pwd)
                    st.rerun()
                else: st.error("קוד שגוי. אנא נסה שוב.")
else:
    # סרגל צד מעוצב
    with st.sidebar:
        st.title("ניהול חשבון")
        st.info(f"שווי תיק כולל: ${current_portfolio_value:,.2f}")
        if st.button("יציאה מאובטחת"):
            st.session_state.auth = False
            st.rerun()

    # תצוגת מנהל
    if st.session_state.pwd == ADMIN_CODE:
        st.title("💼 לוח בקרה - מנהל השקעות")
        total_inv = pd.to_numeric(df.iloc[:, 2], errors='coerce').sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("שווי נכסים (IBKR)", f"${current_portfolio_value:,.2f}")
        c2.metric("סך הפקדות", f"${total_inv:,.2f}")
        c3.metric("תשואה מצטברת", f"{((current_portfolio_value-total_inv)/total_inv*100):.2f}%")
        
        st.write("### ריכוז תיקי לקוחות")
        summary = []
        for _, r in df.iterrows():
            try:
                name, inv, share, acts = r[0], float(r[2]), float(str(r[3]).replace('%','')), int(r[4])
                m = calc_metrics(name, inv, current_portfolio_value * (share/100), acts)
                summary.append({"לקוח": name, "הפקדה": f"${inv:,.0f}", "יתרה נטו": f"${m['net']:,.2f}", "רווח %": f"{m['perc']:.1f}%"})
            except: continue
        st.dataframe(pd.DataFrame(summary), use_container_width=True)

    # תצוגת לקוח
    else:
        user_row = df[df.iloc[:, 1].astype(str) == st.session_state.pwd].iloc[0]
        name, inv, share, acts = user_row[0], float(user_row[2]), float(str(user_row[3]).replace('%','')), int(user_row[4])
        m = calc_metrics(name, inv, current_portfolio_value * (share/100), acts)

        st.title(f"שלום, {name}")
        st.markdown(f"סטטוס תיק נכון ל: {time.strftime('%d/%m/%Y')}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("שווי תיק נטו", f"${m['net']:,.2f}")
        c2.metric("רווח/הפסד נטו", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
        c3.metric("נתח בקרן", f"{share}%")

        st.divider()
        col_l, col_r = st.columns([2, 1])
        with col_l:
            fig = px.area(x=["הפקדה ראשונית", "שווי נוכחי נטו"], y=[inv, m['net']], 
                         title="צמיחת ההון שלך", color_discrete_sequence=['#00ff88'])
            fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color="white")
            st.plotly_chart(fig, use_container_width=True)
        with col_r:
            fig2 = px.pie(values=[share, 100-share], names=["חלקך בקרן", "משקיעים אחרים"], 
                        hole=0.6, title="מבנה הבעלות בתיק", color_discrete_sequence=['#00ff88', '#1e2130'])
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
