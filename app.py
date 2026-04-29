"""
RC Capital Portfolio Dashboard — v2 (column-safe)
===================================================
Fixes in this version:
  • Auto-detects column names from Google Sheet (Hebrew or English).
    Add more aliases to COL_ALIASES if your sheet changes column names.
  • Shows a debug panel on login page so you can see exact column names.
  • Robust IBKR retry (up to 8 attempts × 5 s delay) — never returns $0.
  • Cache-busting Google Sheets fetch (timestamp query param).
  • Session-state NAV fallback — survives IBKR downtime.
  • Two-point Plotly chart only — no zig-zag.
  • RTL / Hebrew dark theme.

requirements.txt (place next to this file on Streamlit Cloud):
    streamlit
    pandas
    plotly
    requests
    pytz
    lxml
"""

import time
import pytz
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ──────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────
IB_TOKEN     = "837126977366730658372732"
IB_QUERY     = "1489351"
SHEET_URL    = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV"
    "/pub?output=csv"
)
FALLBACK_NAV     = 6131.72
TAX_EXEMPT_USERS = {"רפאל כהן"}
TAX_RATE         = 0.25
PERFORMANCE_RATE = 0.20
IL_TZ            = pytz.timezone("Asia/Jerusalem")

# ──────────────────────────────────────────────────────────────────
# COLUMN ALIAS MAP
# Maps internal keys → all possible column spellings (case-insensitive).
# Extend this list if your sheet uses different names.
# ──────────────────────────────────────────────────────────────────
COL_ALIASES = {
    "name": [
        "name", "שם", "שם משתמש", "username", "user", "client", "לקוח",
    ],
    "pin": [
        "pin", "סיסמה", "קוד", "password", "פין", "code", "secret",
        "pin number", "קוד סודי",
    ],
    "investment": [
        "investment", "השקעה", "השקעה ראשונית", "initial investment",
        "amount", "סכום", "סכום השקעה",
    ],
    "share": [
        "share %", "share%", "share", "אחוז", "אחוז שותפות",
        "% share", "חלק", "חלק %", "אחוז חלק", "שיעור",
    ],
    "commissions": [
        "commissions/actions", "commissions", "actions", "עמלות",
        "עמלה", "עמלות/פעולות", "fees", "broker fees", "עלויות",
        "דמי ניהול",
    ],
}


def resolve_columns(df: pd.DataFrame) -> dict:
    """Return {internal_key: actual_column_name | None}."""
    lower_map = {c.strip().lower(): c for c in df.columns}
    result = {}
    for key, aliases in COL_ALIASES.items():
        found = None
        for alias in aliases:
            if alias.strip().lower() in lower_map:
                found = lower_map[alias.strip().lower()]
                break
        result[key] = found
    return result


# ──────────────────────────────────────────────
# PAGE CONFIG  (must be first Streamlit call)
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="RC Capital",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0d1117 !important;
    color: #e6edf3 !important;
}
[data-testid="stSidebar"] { background-color: #161b22 !important; }
* { direction: rtl; text-align: right; }
.stMetric label { direction: rtl; text-align: right; }
[data-testid="metric-container"] {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px 20px;
}
[data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700; }
h1, h2, h3 { color: #58a6ff !important; }
.stButton > button {
    background: #238636; color: #fff; border: none;
    border-radius: 6px; width: 100%; font-size: 1rem; padding: .5rem 1rem;
}
.stButton > button:hover { background: #2ea043; }
.status-ok   { color: #3fb950; font-weight: 700; }
.status-warn { color: #d29922; font-weight: 700; }
.status-err  { color: #f85149; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# SESSION STATE DEFAULTS
# ──────────────────────────────────────────────
for _k, _v in {
    "total_nav":     None,
    "nav_source":    "לא נטען",
    "last_refresh":  None,
    "authenticated": False,
    "current_user":  None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ──────────────────────────────────────────────
# IBKR FLEX QUERY — robust fetch
# ──────────────────────────────────────────────
def fetch_ibkr_nav(max_attempts: int = 8, delay_s: int = 5):
    """Returns (nav_float | None, status_str)."""
    try:
        r = requests.get(
            f"https://www.interactivebrokers.com/Universal/servlet/"
            f"FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3",
            timeout=30,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)

        status_el = root.find("Status")
        if status_el is None or status_el.text != "Success":
            err = root.find("ErrorMessage")
            return None, f"IBKR שלב 1 נכשל: {err.text if err is not None else 'סטטוס לא ידוע'}"

        ref_url  = root.find("Url").text
        ref_code = root.find("ReferenceCode").text

        for attempt in range(1, max_attempts + 1):
            time.sleep(delay_s)
            data_r  = requests.get(f"{ref_url}?q={ref_code}&t={IB_TOKEN}", timeout=30)
            content = data_r.content

            if b"NetAssetValue" not in content:
                try:
                    err_root = ET.fromstring(content)
                    err_el   = err_root.find("ErrorMessage")
                    if err_el is not None and "try again" in err_el.text.lower():
                        continue
                except ET.ParseError:
                    pass
                continue

            d_root = ET.fromstring(content)
            navs = [
                float(n.get("total"))
                for n in d_root.findall(".//NetAssetValue")
                if n.get("total") and n.get("total") not in ("", "0", "0.0")
            ]
            if navs:
                return max(navs), f"IBKR חי ✓ (ניסיון {attempt})"

        return None, f"IBKR: לא נמצא NAV לאחר {max_attempts} ניסיונות"

    except requests.exceptions.Timeout:
        return None, "IBKR: timeout בחיבור"
    except requests.exceptions.ConnectionError:
        return None, "IBKR: שגיאת חיבור לרשת"
    except ET.ParseError as e:
        return None, f"IBKR: שגיאת XML – {e}"
    except Exception as e:
        return None, f"IBKR: שגיאה לא צפויה – {e}"


# ──────────────────────────────────────────────
# GOOGLE SHEETS — cache-busted
# ──────────────────────────────────────────────
@st.cache_data(ttl=0)
def load_sheet(bust: str) -> pd.DataFrame:
    """bust changes every call / every 5 min to prevent stale cache."""
    url = f"{SHEET_URL}&cachebust={bust}"
    df  = pd.read_csv(url)
    df.columns = df.columns.str.strip()
    return df


# ──────────────────────────────────────────────
# NAV RESOLVER
# ──────────────────────────────────────────────
def resolve_nav():
    with st.spinner("מושך נתונים מ-IBKR… (עד 40 שניות)"):
        nav, source = fetch_ibkr_nav()

    if nav and nav > 0:
        st.session_state.total_nav  = nav
        st.session_state.nav_source = source
    elif st.session_state.total_nav and st.session_state.total_nav > 0:
        st.session_state.nav_source = f"ערך אחרון ידוע (IBKR לא זמין: {source})"
    else:
        st.session_state.total_nav  = FALLBACK_NAV
        st.session_state.nav_source = f"ערך ברירת מחדל (IBKR לא זמין: {source})"

    st.session_state.last_refresh = datetime.now(IL_TZ).strftime("%d/%m/%Y %H:%M:%S")


# ──────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ הגדרות")

    if st.button("🔄 רענן נתונים"):
        load_sheet.clear()
        resolve_nav()
        st.rerun()

    st.divider()

    _nav = st.session_state.total_nav
    if _nav and _nav > 0:
        _src = st.session_state.nav_source
        _badge = (
            '<span class="status-ok">● חי</span>'          if "חי ✓"       in _src else
            '<span class="status-warn">● ערך אחרון</span>' if "אחרון ידוע" in _src else
            '<span class="status-err">● ברירת מחדל</span>'
        )
        st.markdown(f"**סטטוס IBKR:** {_badge}", unsafe_allow_html=True)
        st.markdown(f"**NAV כולל:** ${_nav:,.2f}")
    else:
        st.markdown('<span class="status-err">● לא נטען</span>', unsafe_allow_html=True)

    if st.session_state.last_refresh:
        st.caption(f"עדכון אחרון: {st.session_state.last_refresh}")

    st.divider()
    if st.session_state.authenticated:
        if st.button("🔓 התנתקות"):
            st.session_state.authenticated = False
            st.session_state.current_user  = None
            st.rerun()

# ──────────────────────────────────────────────
# INITIAL NAV LOAD
# ──────────────────────────────────────────────
if st.session_state.total_nav is None:
    resolve_nav()

# ──────────────────────────────────────────────
# LOGIN SCREEN
# ──────────────────────────────────────────────
if not st.session_state.authenticated:
    st.markdown("# 🏦 RC Capital")
    st.markdown("### כניסה לחשבון")
    st.divider()

    bust = str(int(time.time()))   # always fresh on login page
    try:
        df_users = load_sheet(bust)
    except Exception as e:
        st.error(f"שגיאה בטעינת הגיליון: {e}")
        st.stop()

    cols = resolve_columns(df_users)

    # ── DEBUG EXPANDER — open this if login fails ──
    with st.expander("🔍 אבחון גיליון — פתח אם יש שגיאת כניסה", expanded=False):
        st.markdown("**עמודות שנמצאו בגיליון:**")
        st.code(list(df_users.columns))
        st.markdown("**מיפוי עמודות (internal → גיליון):**")
        st.json(cols)
        st.markdown("**3 שורות ראשונות:**")
        st.dataframe(df_users.head(3))
        st.markdown(
            "אם עמודות `name` ו-`pin` מופיעות כ-`null` למעלה, "
            "עדכן את `COL_ALIASES` בקוד כך שיתאים לשמות העמודות שמוצגות כאן."
        )

    # Validate required columns
    missing = [k for k in ("name", "pin") if cols[k] is None]
    if missing:
        st.error(
            f"❌ לא נמצאו עמודות חובה: **{missing}**\n\n"
            f"עמודות בגיליון: `{list(df_users.columns)}`\n\n"
            "פתח את אבחון הגיליון למעלה ועדכן את `COL_ALIASES` בקוד."
        )
        st.stop()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pin_input = st.text_input("הכנס PIN", type="password", placeholder="••••••")
        if st.button("כניסה"):
            df_users["_pin_norm"] = df_users[cols["pin"]].astype(str).str.strip()
            match = df_users[df_users["_pin_norm"] == pin_input.strip()]
            if not match.empty:
                st.session_state.authenticated = True
                st.session_state.current_user  = str(match.iloc[0][cols["name"]]).strip()
                st.success(f"ברוך הבא, {st.session_state.current_user}!")
                st.rerun()
            else:
                st.error("PIN שגוי. נסה שוב.")

    st.stop()

# ──────────────────────────────────────────────
# DASHBOARD (authenticated users only)
# ──────────────────────────────────────────────
bust = str(int(time.time() // 300))   # sheet refresh every 5 min
try:
    df_users = load_sheet(bust)
except Exception as e:
    st.error(f"שגיאה בטעינת הגיליון: {e}")
    st.stop()

cols     = resolve_columns(df_users)
user_row = df_users[
    df_users[cols["name"]].astype(str).str.strip() == st.session_state.current_user
]

if user_row.empty:
    st.error("המשתמש לא נמצא בגיליון. פנה למנהל המערכת.")
    st.stop()

user         = user_row.iloc[0]
user_name    = str(user[cols["name"]]).strip()
investment   = float(user[cols["investment"]])   if cols["investment"]  else 0.0
share_pct    = float(user[cols["share"]])        if cols["share"]       else 0.0
commissions  = float(user[cols["commissions"]])  if cols["commissions"] else 0.0
is_exempt    = user_name in TAX_EXEMPT_USERS
total_nav    = st.session_state.total_nav

# ── Core calculations ──
gross_value = total_nav * (share_pct / 100)
raw_profit  = gross_value - investment - commissions

if is_exempt or raw_profit <= 0:
    taxes           = 0.0
    performance_fee = 0.0
else:
    taxes           = raw_profit * TAX_RATE
    performance_fee = raw_profit * PERFORMANCE_RATE

net_profit = raw_profit - taxes - performance_fee
net_value  = investment + net_profit
roi_pct    = (net_profit / investment * 100) if investment else 0

# ── Header ──
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown("# 🏦 RC Capital")
    st.markdown(f"### שלום, {user_name} 👋")
with c2:
    now_str = datetime.now(IL_TZ).strftime("%d/%m/%Y %H:%M")
    st.markdown(f"<br><br><small style='color:#8b949e'>{now_str}</small>", unsafe_allow_html=True)

st.divider()

# ── Metric row 1 ──
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("💰 השקעה ראשונית",          f"${investment:,.2f}")
with m2:
    st.metric("📊 שווי ברוטו (חלק יחסי)",  f"${gross_value:,.2f}", f"{share_pct:.1f}% מה-NAV")
with m3:
    st.metric("📈 רווח נקי",               f"${net_profit:,.2f}",  f"{roi_pct:+.1f}%")
with m4:
    st.metric("🏦 NAV כולל (IBKR)",        f"${total_nav:,.2f}")

st.markdown("<br>", unsafe_allow_html=True)

# ── Metric row 2 (fees) ──
if not is_exempt:
    f1, f2, f3 = st.columns(3)
    with f1:
        st.metric("🏛️ מס רווח הון (25%)", f"${taxes:,.2f}")
    with f2:
        st.metric("💼 דמי הצלחה (20%)",    f"${performance_fee:,.2f}")
    with f3:
        st.metric("🧾 עמלות / עלויות",     f"${commissions:,.2f}")
else:
    st.info("✅ פטור ממס ודמי הצלחה")

st.divider()

# ── Two-point bar chart ──
fig = go.Figure(go.Bar(
    x=["השקעה ראשונית", "שווי נוכחי נקי"],
    y=[investment, net_value],
    marker_color=["#388bfd", "#3fb950" if net_value >= investment else "#f85149"],
    text=[f"${investment:,.0f}", f"${net_value:,.0f}"],
    textposition="outside",
    textfont=dict(color="#e6edf3", size=14),
    width=0.4,
))
fig.update_layout(
    title=dict(text="השקעה לעומת שווי נוכחי", font=dict(size=20, color="#58a6ff"), x=0.5),
    plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
    font=dict(color="#e6edf3"),
    xaxis=dict(tickfont=dict(size=14), showgrid=False),
    yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#21262d"),
    margin=dict(t=60, b=40, l=60, r=40),
    height=420, showlegend=False,
)
fig.add_hline(
    y=investment, line_dash="dot", line_color="#d29922",
    annotation_text=f"נקודת איזון: ${investment:,.0f}",
    annotation_position="top right",
    annotation_font_color="#d29922",
)
st.plotly_chart(fig, use_container_width=True)

# ── Details table ──
st.divider()
st.markdown("### 📋 פירוט חישוב מלא")
st.dataframe(
    pd.DataFrame({
        "פריט": [
            "NAV כולל (IBKR)", f"חלק יחסי ({share_pct:.1f}%)",
            "השקעה ראשונית", "עמלות / עלויות", "רווח גולמי",
            "מס רווח הון (25%)" if not is_exempt else "מס רווח הון",
            "דמי הצלחה (20%)"   if not is_exempt else "דמי הצלחה",
            "רווח נקי סופי", "שווי נוכחי נקי",
        ],
        "סכום ($)": [
            f"${total_nav:,.2f}",   f"${gross_value:,.2f}",
            f"${investment:,.2f}",  f"${commissions:,.2f}",
            f"${raw_profit:,.2f}",
            f"${taxes:,.2f}"           if not is_exempt else "פטור",
            f"${performance_fee:,.2f}" if not is_exempt else "פטור",
            f"${net_profit:,.2f}",  f"${net_value:,.2f}",
        ],
    }),
    hide_index=True,
    use_container_width=True,
)

# ── Footer ──
st.divider()
_src = st.session_state.nav_source
_col = "#3fb950" if "חי ✓" in _src else "#d29922" if "אחרון" in _src else "#f85149"
_ico = "🟢"      if "חי ✓" in _src else "🟡"      if "אחרון" in _src else "🔴"
st.markdown(f"<small style='color:{_col}'>{_ico} מקור נתונים: {_src}</small>", unsafe_allow_html=True)
