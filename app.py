import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
IBKR_TOKEN      = "837126977366730658372732"
IBKR_QUERY_ID   = "1492787"
ADMIN_PIN       = "0000"
TAX_RATE        = 0.25
IBKR_WAIT_SECS  = 12

# הלינק המעודכן ביותר שלך מוטמע כאן
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxbjPgewwMtpEXKF-8A-4KuXCofmc4yfcle_htbxtdVEvMnTMe6mCBuF8liMWJ2Wj6f/exec"

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1AuspdxTTFAoAYqgU0bpGko6-Z1PUcI3Zs7kF-ixjVC0/edit?usp=sharing"
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

IBKR_SEND_URL = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
IBKR_GET_URL  = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="RC Capital | לוח בקרה",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── GLOBAL STYLES ───────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700;900&display=swap');
html, body, [class*="css"], .stApp {
    font-family: 'Heebo', sans-serif !important;
    direction: rtl;
    background: #060d18;
    color: #e6edf3;
}
h1, h2, h3, h4 { font-family: 'Heebo', sans-serif !important; }
.kpi-card {
    background: linear-gradient(145deg, #0f1f38 0%, #0c1a2e 100%);
    border: 1px solid #1d3557;
    border-radius: 14px;
    padding: 26px 22px;
    text-align: center;
    height: 100%;
}
.kpi-label { font-size: 0.78rem; color: #607b96; margin-bottom: 8px; letter-spacing: 0.05em; text-transform: uppercase; }
.kpi-value { font-size: 2rem; font-weight: 700; line-height: 1.1; }
.kpi-sub   { font-size: 0.75rem; color: #607b96; margin-top: 6px; }
.green { color: #3ddc97 !important; }
.red   { color: #ff5c5c !important; }
.gold  { color: #ffc857 !important; }
.white { color: #e6edf3 !important; }
.muted { color: #607b96 !important; }
.login-wrap { max-width: 380px; margin: 70px auto 0; text-align: center; }
.stTextInput > div > div > input {
    background: #0a1525 !important;
    border: 1px solid #1d3557 !important;
    color: #e6edf3 !important;
    border-radius: 10px !important;
    text-align: center;
    font-family: 'Heebo', sans-serif;
    font-size: 1.1rem;
    letter-spacing: 0.25em;
}
.stButton > button {
    width: 100%;
    background: linear-gradient(135deg, #1d6fa4, #1450a3);
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Heebo', sans-serif !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
    padding: 12px !important;
}
hr { border-color: #1d3557 !important; }
</style>
""", unsafe_allow_html=True)

# ─── SESSION STATE INIT ──────────────────────────────────────────────────────
if "authenticated" not in st.session_state: st.session_state.authenticated = False
if "user_row" not in st.session_state: st.session_state.user_row = None
if "is_admin" not in st.session_state: st.session_state.is_admin = False
if "live_nav" not in st.session_state: st.session_state.live_nav = None

# ─── DATA LOADERS ────────────────────────────────────────────────────────────
@st.cache_data(ttl=2)
def load_users_and_nav() -> tuple:
    bust = int(time.time())
    url = f"{GOOGLE_SHEET_CSV_URL}&cb={bust}"
    df = pd.read_csv(url)
    
    saved_nav = None
    if df.shape[1] > 5:
        nav_val = str(df.iloc[0, 5]).replace('$', '').replace(',', '').strip()
        try:
            if nav_val.lower() != 'nan' and nav_val != '':
                saved_nav = float(nav_val)
                if saved_nav <= 0: saved_nav = None
        except ValueError:
            saved_nav = None

    cleaned_df = df.iloc[:, :4].copy()
    cleaned_df.columns = ['name', 'pin', 'initial_capital', 'share_pct']
    cleaned_df["pin"] = cleaned_df["pin"].astype(str).str.strip().str.replace('.0', '', regex=False)
    
    for col in ["initial_capital", "share_pct"]:
        cleaned_df[col] = cleaned_df[col].astype(str).str.replace('%', '').str.replace('$', '').str.replace(',', '').str.strip()
        cleaned_df[col] = pd.to_numeric(cleaned_df[col], errors="coerce").fillna(0)
    
    cleaned_df["is_manager"] = cleaned_df["name"].str.lower().str.contains("raphael")
    return cleaned_df, saved_nav


def save_nav_to_google_sheet(new_nav: float) -> bool:
    """מעדכן את הזיכרון הפנימי מיד ושולח ברקע פקודת שמירה לגוגל שיטס"""
    st.session_state.live_nav = new_nav
    if "https://" in APPS_SCRIPT_URL:
        try:
            res = requests.get(f"{APPS_SCRIPT_URL}?value={new_nav}", timeout=10)
            st.cache_data.clear()
            return True
        except Exception:
            pass
    return False


def fetch_ibkr_nav() -> tuple:
    try:
        r1 = requests.get(IBKR_SEND_URL, params={"t": IBKR_TOKEN, "q": IBKR_QUERY_ID, "v": "3"}, timeout=15)
        root1 = ET.fromstring(r1.text)
        status = root1.findtext("Status", "")
        if status == "Warn":
            code = root1.findtext("ErrorCode", "")
            if code == "1019": return None, "⏳ IBKR: יותר מדי בקשות רצופות. המתן 3 דקות."
            return None, f"IBKR Error: {root1.findtext('ErrorMessage')}"
        
        ref_code = root1.findtext("ReferenceCode", "").strip()
        if not ref_code: return None, "לא התקבל קוד אסמכתא מ-IBKR."
        
        time.sleep(IBKR_WAIT_SECS)
        
        r2 = requests.get(IBKR_GET_URL, params={"t": IBKR_TOKEN, "q": ref_code, "v": "3"}, timeout=30)
        root2 = ET.fromstring(r2.text)
        
        if root2.tag == "FlexStatementOperationMessage":
            return None, "IBKR עדיין מעבד את הדוח, נסה שוב בעוד חצי דקה."
            
        nodes = root2.findall(".//EquitySummaryByReportDateInBase")
        if not nodes: return None, "לא נמצא נתון NAV בדוח."
        
        total_str = nodes[-1].get("total", "").replace(",", "").strip()
        return float(total_str), None
    except Exception as exc:
        return None, f"שגיאה בתקשורת: {exc}"


# ─── CALCULATION ENGINE ──────────────────────────────────────────────────────
def calculate(nav: float, share_pct: float, initial_capital: float, is_manager: bool) -> dict:
    gross = nav * (share_pct / 100.0)
    pnl   = gross - initial_capital
    tax   = (pnl * TAX_RATE) if (pnl > 0 and not is_manager) else 0.0
    net   = gross - tax
    return {"gross": gross, "pnl": pnl, "tax": tax, "net": net, "net_pnl": net - initial_capital, "roi": ((net - initial_capital) / initial_capital * 100) if initial_capital else 0.0}


def kpi(label: str, value: str, sub: str = "", colour: str = "white") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value {colour}">{value}</div>
        {sub_html}
    </div>"""


# ─── LOGIN SCREEN ─────────────────────────────────────────────────────────────
def show_login():
    st.markdown("""
    <div class="login-wrap">
        <div style="font-size:3rem;">💼</div>
        <h1 style="font-size:2.4rem; font-weight:900; margin:8px 0 4px;">RC Capital</h1>
        <p class="muted" style="font-size:1rem; margin-bottom:36px;">ניהול תיק השקעות | לוח בקרה</p>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 1.1, 1])
    with col_c:
        with st.form("login"):
            pin = st.text_input("קוד גישה", type="password", placeholder="••••", max_chars=20, label_visibility="collapsed")
            ok = st.form_submit_button("כניסה →")

        if ok:
            pin = pin.strip()
            if pin == ADMIN_PIN:
                st.session_state.authenticated = True
                st.session_state.is_admin = True
                st.rerun()
            elif pin:
                try:
                    users, _ = load_users_and_nav()
                    match = users[users["pin"] == pin]
                    if not match.empty:
                        st.session_state.authenticated = True
                        st.session_state.is_admin = False
                        st.session_state.user_row = match.iloc[0].to_dict()
                        st.rerun()
                    else:
                        st.error("קוד גישה שגוי — נסה שנית.")
                except Exception as exc:
                    st.error(f"שגיאה בקריאת הנתונים: {exc}")


# ─── ADMIN COMMAND CENTER ─────────────────────────────────────────────────────
def show_admin():
    users, saved_nav = load_users_and_nav()
    
    if st.session_state.live_nav is not None:
        nav = st.session_state.live_nav
    elif saved_nav is not None:
        nav = saved_nav
    else:
        nav = 9500.0

    col_title, col_logout = st.columns([6, 1])
    with col_title: st.markdown("## 🏛️ Command Center — RC Capital")
    with col_logout:
        if st.button("התנתק"):
            st.session_state.clear()
            st.rerun()

    st.markdown("---")

    with st.expander("⚙️ פאנל ניהול שווי תיק", expanded=True):
        ctrl_left, ctrl_mid, ctrl_right = st.columns([2, 2, 1])
        with ctrl_left:
            st.markdown("**📝 עדכון שווי תיק ידני**")
            manual_nav = st.number_input("הזן שווי תיק כולל ($)", min_value=0.0, step=100.0, value=float(nav), format="%.2f")
            if st.button("💾 שמור שווי תיק קבוע"):
                if manual_nav > 0:
                    st.session_state.live_nav = manual_nav
                    with st.spinner("שומר ומעדכן קובץ גוגל שיטס ברקע..."):
                        save_nav_to_google_sheet(manual_nav)
                    st.success(f"✅ שווי עודכן באפליקציה ונשלח ל-Sheets תא F2: ${manual_nav:,.2f}")
                    time.sleep(0.5)
                    st.rerun()

        with ctrl_mid:
            st.markdown("**📡 סנכרון אוטומטי**")
            if st.button("🔄 משוך ושמור מ-IBKR"):
                with st.spinner("מתחבר לשרתי IBKR..."):
                    fetched_nav, err = fetch_ibkr_nav()
                if err: st.error(err)
                else:
                    st.session_state.live_nav = fetched_nav
                    with st.spinner("שומר את הנתון מ-IBKR בגוגל שיטס..."):
                        save_nav_to_google_sheet(fetched_nav)
                    st.success(f"✅ עודכן ונשמר מ-IBKR: ${fetched_nav:,.2f}")
                    time.sleep(0.5)
                    st.rerun()

        with ctrl_right:
            st.markdown("**שווי שמור נוכחי**")
            st.markdown(f"""
            <div class="kpi-card" style="padding:16px;">
                <div class="kpi-label">NAV פעיל במערכת</div>
                <div class="kpi-value green" style="font-size:1.4rem;">${nav:,.2f}</div>
                <div class="kpi-sub">מעודכן בזמן אמת</div>
            </div>""", unsafe_allow_html=True)

    # חישובים
    calcs = [calculate(nav, r["share_pct"], r["initial_capital"], r["is_manager"]) for _, r in users.iterrows()]
    total_initial = users["initial_capital"].sum()
    total_net     = sum(c["net"] for c in calcs)
    total_pnl     = total_net - total_initial
    total_tax     = sum(c["tax"] for c in calcs)
    overall_roi   = (total_pnl / total_initial * 100) if total_initial else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(kpi("NAV מאסטר", f"${nav:,.2f}", "מזהה פעיל"), unsafe_allow_html=True)
    with c2: st.markdown(kpi("סה״כ הון מושקע", f"${total_initial:,.0f}"), unsafe_allow_html=True)
    with c3: st.markdown(kpi("סה״כ שווי נטו", f"${total_net:,.2f}"), unsafe_allow_html=True)
    with c4: st.markdown(kpi("רווח כולל נטו", f"${total_pnl:,.2f}", f"{overall_roi:.2f}% | מס: ${total_tax:,.2f}", "green" if total_pnl >= 0 else "red"), unsafe_allow_html=True)

    st.markdown("### 📊 מצב חשבונות המשקיעים (מתוך הגיליון)")
    rows = []
    for (_, u), c in zip(users.iterrows(), calcs):
        rows.append({
            "שם": u["name"],
            "חלק %": f"{u['share_pct']:.2f}%",
            "הון ראשוני $": f"${u['initial_capital']:,.0f}",
            "ברוטו $": f"${c['gross']:,.2f}",
            "רווח/הפסד $": f"${c['pnl']:+,.2f}",
            "מס $": f"${c['tax']:,.2f}" if c['tax'] > 0 else "—",
            "שווי נטו $": f"${c['net']:,.2f}",
            "תשואה %": f"{c['roi']:+.2f}%",
            "סוג": "מנהל" if u["is_manager"] else "משקיע"
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ─── USER DASHBOARD ──────────────────────────────────────────────────────────
def show_user():
    u = st.session_state.user_row
    users, saved_nav = load_users_and_nav()
    
    if st.session_state.live_nav is not None: nav = st.session_state.live_nav
    elif saved_nav is not None: nav = saved_nav
    else: nav = 9500.0

    current_user_match = users[users["name"] == u["name"]]
    if not current_user_match.empty:
        u = current_user_match.iloc[0].to_dict()

    c = calculate(nav, float(u["share_pct"]), float(u["initial_capital"]), bool(u["is_manager"]))
    
    col_h, col_logout = st.columns([5, 1])
    with col_h: st.markdown(f'<h2>שלום, {u["name"]} 👋</h2>', unsafe_allow_html=True)
    with col_logout:
        if st.button("התנתק"):
            st.session_state.clear()
            st.rerun()

    st.markdown(f"""
    <div class="kpi-card" style="max-width:480px; margin:0 auto 28px auto; padding:36px 28px;">
        <div class="kpi-label">השווי נטו שלך</div>
        <div class="kpi-value green" style="font-size:3rem;">${c['net']:,.2f}</div>
        <div class="kpi-sub green" style="font-size:0.85rem;">{c['net_pnl']:+,.2f}$ | {c['roi']:+.2f}%</div>
    </div>""", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(kpi("הון ראשוני", f"${u['initial_capital']:,.0f}"), unsafe_allow_html=True)
    with c2: st.markdown(kpi("פוזיציה ברוטו", f"${c['gross']:,.2f}", f"חלק: {u['share_pct']}%"), unsafe_allow_html=True)
    with c3: st.markdown(kpi("מס רווח הון (25%)", f"${c['tax']:,.2f}" if c['tax'] > 0 else "אין", colour="gold" if c['tax'] > 0 else "green"), unsafe_allow_html=True)


# ─── ROUTER ──────────────────────────────────────────────────────────────────
if not st.session_state.authenticated: show_login()
elif st.session_state.is_admin: show_admin()
else: show_user()
