"""
╔══════════════════════════════════════════════════════════════╗
║          RC Capital — Investment Dashboard  v3.0             ║
║                                                              ║
║  Architecture:                                               ║
║    • Streamlit (Python) hosted on Streamlit Cloud            ║
║    • Investor DB: Google Sheets (published CSV)              ║
║    • Live NAV:   IBKR Flex Query API                         ║
║                                                              ║
║  Key design decisions:                                       ║
║    • COL_ALIASES: tolerates any Hebrew/English column name   ║
║    • IBKR retry loop: up to 8 × 5 s — never returns $0      ║
║    • Cache-bust: timestamp appended to every Sheet URL       ║
║    • session_state: last known NAV survives page re-runs     ║
║    • Admin PIN 0000: reveals full investor table             ║
╚══════════════════════════════════════════════════════════════╝
"""

# ── stdlib ──────────────────────────────────────────────────────
import time
import xml.etree.ElementTree as ET
from datetime import datetime

# ── third-party ─────────────────────────────────────────────────
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st

# ════════════════════════════════════════════════════════════════
# 1.  CONSTANTS
# ════════════════════════════════════════════════════════════════
IB_TOKEN  = "837126977366730658372732"
IB_QUERY  = "1489351"
SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV"
    "/pub?output=csv"
)

ADMIN_PIN        = "0000"
FALLBACK_NAV     = 6_131.72          # last known hard-coded guard — edit freely
ADMIN_NAME       = "רפאל"            # substring match → tax exempt
TAX_RATE         = 0.25
PERF_RATE        = 0.20
IL_TZ            = pytz.timezone("Asia/Jerusalem")

# ════════════════════════════════════════════════════════════════
# 2.  COLUMN ALIAS MAP
#     Extend any list if the sheet uses a different spelling.
# ════════════════════════════════════════════════════════════════
COL_ALIASES: dict[str, list[str]] = {
    "name": [
        "name", "שם", "שם משתמש", "username", "user", "client", "לקוח",
    ],
    "pin": [
        "pin", "סיסמה", "קוד", "password", "פין", "code",
        "pin number", "קוד סודי", "secret",
    ],
    "investment": [
        "investment", "השקעה", "השקעה ראשונית", "initial investment",
        "amount", "סכום", "סכום השקעה",
    ],
    "share": [
        "share %", "share%", "share", "אחוז", "אחוז שותפות",
        "% share", "חלק", "חלק %", "אחוז חלק", "שיעור",
    ],
    "fees": [
        "commissions/actions", "commissions", "actions", "עמלות",
        "עמלה", "עמלות/פעולות", "fees", "broker fees", "עלויות",
        "דמי ניהול",
    ],
}


def find_col(df: pd.DataFrame, key: str) -> str | None:
    """Return the actual DataFrame column name for an internal key, or None."""
    lower_map = {c.strip().lower(): c for c in df.columns}
    for alias in COL_ALIASES.get(key, []):
        if alias.strip().lower() in lower_map:
            return lower_map[alias.strip().lower()]
    return None


def resolve_all_cols(df: pd.DataFrame) -> dict[str, str | None]:
    return {key: find_col(df, key) for key in COL_ALIASES}


# ════════════════════════════════════════════════════════════════
# 3.  PAGE CONFIG  (must be the very first Streamlit call)
# ════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="RC Capital",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════════════
# 4.  GLOBAL CSS — dark premium + RTL
# ════════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ── Base ── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stHeader"], [data-testid="stToolbar"] {
    background-color: #0a0e1a !important;
    color: #dce6f5 !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1321 0%, #111827 100%) !important;
    border-right: 1px solid #1e2d45;
}

/* ── RTL ── */
html, body, * { direction: rtl !important; }
.stTextInput input, .stNumberInput input { text-align: right; }

/* ── Typography ── */
h1 { font-size: 2.2rem !important; letter-spacing: -0.5px; }
h2 { font-size: 1.5rem !important; }
h3 { font-size: 1.2rem !important; }
h1, h2, h3 { color: #4da3ff !important; font-weight: 700 !important; }

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #0d1b2e 0%, #112240 100%);
    border: 1px solid #1e3a5f;
    border-radius: 14px;
    padding: 20px 24px;
    transition: border-color .2s;
}
[data-testid="metric-container"]:hover { border-color: #4da3ff; }
[data-testid="stMetricLabel"]  { color: #7fafd4 !important; font-size: .85rem !important; }
[data-testid="stMetricValue"]  { color: #ffffff  !important; font-size: 1.7rem !important; font-weight: 800 !important; }
[data-testid="stMetricDelta"]  { font-size: .95rem !important; font-weight: 600 !important; }

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, #1a6fc4 0%, #155fa0 100%);
    color: #fff; border: none; border-radius: 8px;
    width: 100%; font-size: .95rem; font-weight: 600;
    padding: .55rem 1.2rem; letter-spacing: .3px;
    transition: all .2s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2080d8 0%, #1a6fc4 100%);
    box-shadow: 0 4px 16px rgba(77,163,255,.3);
    transform: translateY(-1px);
}

/* ── Dividers ── */
hr { border-color: #1e3a5f !important; }

/* ── DataFrames ── */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* ── Expander ── */
details { border: 1px solid #1e3a5f !important; border-radius: 8px !important; }

/* ── Status badges ── */
.badge-live  { color: #3fb950; font-weight: 700; }
.badge-stale { color: #d29922; font-weight: 700; }
.badge-dead  { color: #f85149; font-weight: 700; }

/* ── Login card ── */
.login-card {
    background: linear-gradient(135deg, #0d1b2e, #112240);
    border: 1px solid #1e3a5f;
    border-radius: 16px;
    padding: 36px 40px;
    max-width: 420px;
    margin: 0 auto;
}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# 5.  SESSION STATE DEFAULTS
# ════════════════════════════════════════════════════════════════
_defaults = {
    "total_nav":     None,   # float or None
    "nav_source":    "לא נטען",
    "nav_ts":        None,   # datetime of last successful IBKR fetch
    "last_refresh":  None,   # human-readable string
    "authenticated": False,
    "current_user":  None,
    "is_admin":      False,
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ════════════════════════════════════════════════════════════════
# 6.  IBKR FLEX QUERY — robust fetch with retry loop
# ════════════════════════════════════════════════════════════════
def fetch_ibkr_nav(max_attempts: int = 8, delay_s: int = 5) -> tuple[float | None, str]:
    """
    Two-step IBKR Flex Query protocol:
      Step 1 — POST to SendRequest  → get ReferenceCode
      Step 2 — Poll GetStatement    → wait until NetAssetValue appears

    Returns (nav_value, status_message).
    Never raises; all exceptions produce (None, description).
    """
    SEND_URL = (
        "https://www.interactivebrokers.com/Universal/servlet/"
        f"FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3"
    )
    try:
        # ── Step 1: request report generation ──
        r1 = requests.get(SEND_URL, timeout=30)
        r1.raise_for_status()
        root1 = ET.fromstring(r1.content)

        status_el = root1.find("Status")
        if status_el is None or status_el.text != "Success":
            err = root1.find("ErrorMessage")
            msg = err.text if err is not None else "סטטוס לא ידוע"
            return None, f"IBKR שלב 1 נכשל: {msg}"

        ref_url  = root1.find("Url").text.strip()
        ref_code = root1.find("ReferenceCode").text.strip()

        # ── Step 2: poll until the report is ready ──
        for attempt in range(1, max_attempts + 1):
            time.sleep(delay_s)

            r2      = requests.get(f"{ref_url}?q={ref_code}&t={IB_TOKEN}", timeout=30)
            content = r2.content

            # IBKR returns an error envelope while the report isn't ready yet
            if b"NetAssetValue" not in content:
                try:
                    err_root = ET.fromstring(content)
                    err_el   = err_root.find("ErrorMessage")
                    if err_el is not None and "try again" in err_el.text.lower():
                        continue   # server still generating — keep waiting
                except ET.ParseError:
                    pass
                continue           # malformed or empty response — retry

            # Parse NAV values — skip zeros
            d_root = ET.fromstring(content)
            navs = [
                float(n.get("total"))
                for n in d_root.findall(".//NetAssetValue")
                if n.get("total") and n.get("total") not in ("", "0", "0.0")
            ]
            if navs:
                return max(navs), f"IBKR חי ✓  (ניסיון {attempt}/{max_attempts})"

        return None, f"IBKR: לא נמצא NAV לאחר {max_attempts} ניסיונות ({max_attempts * delay_s}s)"

    except requests.exceptions.Timeout:
        return None, "IBKR: timeout בחיבור"
    except requests.exceptions.ConnectionError:
        return None, "IBKR: שגיאת חיבור לרשת"
    except ET.ParseError as exc:
        return None, f"IBKR: שגיאת XML – {exc}"
    except Exception as exc:
        return None, f"IBKR: שגיאה לא צפויה – {exc}"


def resolve_nav() -> None:
    """
    Attempts a fresh IBKR fetch.
    On failure: keeps last session value.
    If session is also empty: uses FALLBACK_NAV.
    Updates st.session_state in all cases.
    """
    with st.spinner("📡 מושך נתונים מ-IBKR… (עד 40 שניות)"):
        nav, source = fetch_ibkr_nav()

    if nav and nav > 0:
        st.session_state.total_nav  = nav
        st.session_state.nav_source = source
        st.session_state.nav_ts     = datetime.now(IL_TZ)
    elif st.session_state.total_nav and st.session_state.total_nav > 0:
        # Keep last-known — just update the status label
        st.session_state.nav_source = f"ערך אחרון ידוע ⚠️  ({source})"
    else:
        # Absolute last resort — hard-coded fallback
        st.session_state.total_nav  = FALLBACK_NAV
        st.session_state.nav_source = f"ערך ברירת מחדל 🔴  ({source})"

    st.session_state.last_refresh = datetime.now(IL_TZ).strftime("%d/%m/%Y %H:%M:%S")


# ════════════════════════════════════════════════════════════════
# 7.  GOOGLE SHEETS — cache-busted fetch
# ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=0)   # ttl=0 means we control invalidation manually
def load_sheet(bust: str) -> pd.DataFrame:
    """
    `bust` is a timestamp string; changing it forces Streamlit to treat
    each call as a distinct computation, bypassing the cached result.
    """
    url = f"{SHEET_URL}&cachebust={bust}"
    df  = pd.read_csv(url)
    df.columns = df.columns.str.strip()
    return df


# ════════════════════════════════════════════════════════════════
# 8.  CALCULATIONS
# ════════════════════════════════════════════════════════════════
def calc_user(total_nav: float, investment: float, share_pct: float,
              fees: float, is_admin: bool) -> dict:
    gross      = total_nav * (share_pct / 100)
    raw_profit = gross - investment - fees

    if is_admin or raw_profit <= 0:
        tax  = 0.0
        perf = 0.0
    else:
        tax  = raw_profit * TAX_RATE
        perf = raw_profit * PERF_RATE

    net_profit = raw_profit - tax - perf
    net_value  = investment + net_profit
    roi_pct    = (net_profit / investment * 100) if investment else 0

    return dict(
        gross=gross, raw_profit=raw_profit,
        tax=tax, perf=perf,
        net_profit=net_profit, net_value=net_value, roi_pct=roi_pct,
    )


# ════════════════════════════════════════════════════════════════
# 9.  SIDEBAR
# ════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ הגדרות")

    if st.button("🔄  רענן נתונים"):
        load_sheet.clear()
        resolve_nav()
        st.rerun()

    st.divider()

    # NAV status
    _nav = st.session_state.total_nav
    _src = st.session_state.nav_source
    if _nav and _nav > 0:
        if "חי ✓" in _src:
            _badge = '<span class="badge-live">● Live</span>'
        elif "אחרון ידוע" in _src:
            _badge = '<span class="badge-stale">● ערך אחרון</span>'
        else:
            _badge = '<span class="badge-dead">● ברירת מחדל</span>'
        st.markdown(f"**סטטוס IBKR:** {_badge}", unsafe_allow_html=True)
        st.markdown(f"**NAV כולל:** `${_nav:,.2f}`")
        if st.session_state.nav_ts:
            st.caption(f"נשלף: {st.session_state.nav_ts.strftime('%H:%M:%S')}")
    else:
        st.markdown('<span class="badge-dead">● לא נטען</span>', unsafe_allow_html=True)

    if st.session_state.last_refresh:
        st.caption(f"רענון אחרון: {st.session_state.last_refresh}")

    st.divider()

    if st.session_state.authenticated:
        st.markdown(f"👤 **{st.session_state.current_user}**")
        if st.button("🔓  התנתקות"):
            for k in ("authenticated", "current_user", "is_admin"):
                st.session_state[k] = False if k != "current_user" else None
            st.rerun()

# ════════════════════════════════════════════════════════════════
# 10. INITIAL NAV LOAD (first run only)
# ════════════════════════════════════════════════════════════════
if st.session_state.total_nav is None:
    resolve_nav()

# ════════════════════════════════════════════════════════════════
# 11. LOGIN SCREEN
# ════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:

    # Header
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:0'>🏦 RC Capital</h1>"
        "<p style='text-align:center;color:#7fafd4;margin-top:4px'>פורטל לקוחות פרטי</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Load the sheet
    bust = str(int(time.time()))     # always fresh on the login page
    try:
        df_sheet = load_sheet(bust)
    except Exception as exc:
        st.error(f"❌ שגיאה בטעינת הגיליון: {exc}")
        st.stop()

    cols = resolve_all_cols(df_sheet)

    # ── Debug expander ──────────────────────────────────────────
    with st.expander("🔍 אבחון גיליון — פתח אם יש שגיאות", expanded=False):
        st.markdown("**עמודות שנמצאו בגיליון:**")
        st.code(list(df_sheet.columns))
        st.markdown("**מיפוי עמודות (internal → גיליון):**")
        st.json(cols)
        st.markdown("**3 שורות ראשונות:**")
        st.dataframe(df_sheet.head(3))
        st.info(
            "אם `name` או `pin` מופיעים כ-`null` — הוסף את שם העמודה המדויק "
            "לרשימת `COL_ALIASES` בחלק העליון של הקוד."
        )

    # Guard: must have at minimum name + pin columns
    missing_required = [k for k in ("name", "pin") if cols[k] is None]
    if missing_required:
        st.error(
            f"❌ עמודות חובה לא נמצאו: **{missing_required}**\n\n"
            f"עמודות קיימות בגיליון: `{list(df_sheet.columns)}`\n\n"
            "פתח את 'אבחון גיליון' למעלה לפרטים."
        )
        st.stop()

    # ── Login form ──────────────────────────────────────────────
    _, center, _ = st.columns([1, 1.6, 1])
    with center:
        st.markdown("<div class='login-card'>", unsafe_allow_html=True)
        st.markdown("### 🔐 כניסה לחשבון")
        pin_input = st.text_input(
            "הכנס קוד PIN",
            type="password",
            placeholder="••••••",
            key="pin_field",
        )
        if st.button("כניסה  →", key="login_btn"):
            # ── Admin shortcut ──
            if pin_input.strip() == ADMIN_PIN:
                st.session_state.authenticated = True
                st.session_state.current_user  = "מנהל"
                st.session_state.is_admin      = True
                st.rerun()

            # ── Regular user ──
            df_sheet["_pin_norm"] = df_sheet[cols["pin"]].astype(str).str.strip()
            match = df_sheet[df_sheet["_pin_norm"] == pin_input.strip()]
            if not match.empty:
                user_name = str(match.iloc[0][cols["name"]]).strip()
                st.session_state.authenticated = True
                st.session_state.current_user  = user_name
                st.session_state.is_admin      = False
                st.rerun()
            else:
                st.error("❌ קוד PIN שגוי. נסה שוב.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# ════════════════════════════════════════════════════════════════
# 12. ADMIN VIEW  (PIN 0000)
# ════════════════════════════════════════════════════════════════
if st.session_state.is_admin:
    st.markdown("# 🏦 RC Capital — תצוגת מנהל")
    st.divider()

    bust = str(int(time.time() // 60))   # refresh every minute for admin
    try:
        df_sheet = load_sheet(bust)
    except Exception as exc:
        st.error(f"❌ שגיאה בטעינת הגיליון: {exc}")
        st.stop()

    cols      = resolve_all_cols(df_sheet)
    total_nav = st.session_state.total_nav

    st.metric("🏦 NAV כולל (IBKR)", f"${total_nav:,.2f}")
    st.divider()
    st.markdown("### 📋 טבלת לקוחות מלאה")
    st.dataframe(df_sheet, use_container_width=True)

    # Per-user summary
    if cols["name"] and cols["investment"] and cols["share"]:
        st.divider()
        st.markdown("### 📊 סיכום לקוחות")
        rows = []
        for _, row in df_sheet.iterrows():
            try:
                name       = str(row[cols["name"]]).strip()
                investment = float(row[cols["investment"]])
                share_pct  = float(row[cols["share"]])
                fees       = float(row[cols["fees"]]) if cols["fees"] else 0.0
                is_ex      = ADMIN_NAME in name
                c          = calc_user(total_nav, investment, share_pct, fees, is_ex)
                rows.append({
                    "שם":           name,
                    "השקעה":        f"${investment:,.0f}",
                    "חלק %":        f"{share_pct:.1f}%",
                    "שווי ברוטו":   f"${c['gross']:,.0f}",
                    "רווח נקי":     f"${c['net_profit']:,.0f}",
                    "ROI":          f"{c['roi_pct']:+.1f}%",
                })
            except Exception:
                continue
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.stop()

# ════════════════════════════════════════════════════════════════
# 13. USER DASHBOARD
# ════════════════════════════════════════════════════════════════

# ── Load sheet ──────────────────────────────────────────────────
bust = str(int(time.time() // 300))    # cache 5 min per user
try:
    df_sheet = load_sheet(bust)
except Exception as exc:
    st.error(f"❌ שגיאה בטעינת הגיליון: {exc}")
    st.stop()

cols = resolve_all_cols(df_sheet)

# ── Find current user's row ──────────────────────────────────────
if cols["name"] is None:
    st.error("עמודת שם לא נמצאה. פתח אבחון גיליון.")
    st.stop()

user_row = df_sheet[
    df_sheet[cols["name"]].astype(str).str.strip() == st.session_state.current_user
]
if user_row.empty:
    st.error("המשתמש לא נמצא בגיליון. פנה למנהל המערכת.")
    st.stop()

row        = user_row.iloc[0]
user_name  = str(row[cols["name"]]).strip()
investment = float(row[cols["investment"]]) if cols["investment"] else 0.0
share_pct  = float(row[cols["share"]])      if cols["share"]      else 0.0
fees       = float(row[cols["fees"]])       if cols["fees"]       else 0.0
is_exempt  = ADMIN_NAME in user_name        # admin name substring = tax-exempt
total_nav  = st.session_state.total_nav

# ── Calculations ────────────────────────────────────────────────
c = calc_user(total_nav, investment, share_pct, fees, is_exempt)

# ── Header ──────────────────────────────────────────────────────
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(f"# 🏦 RC Capital")
    st.markdown(f"### שלום, {user_name} 👋")
with col_h2:
    now_str = datetime.now(IL_TZ).strftime("%d/%m/%Y  %H:%M")
    st.markdown(
        f"<div style='text-align:left;color:#7fafd4;padding-top:28px'>"
        f"<small>{now_str}</small></div>",
        unsafe_allow_html=True,
    )

st.divider()

# ── Metric row 1: primary KPIs ───────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric(
        "💰 יתרה נטו",
        f"${c['net_value']:,.2f}",
        f"{c['roi_pct']:+.2f}%",
    )
with m2:
    profit_sign = "+" if c["net_profit"] >= 0 else ""
    st.metric(
        "📈 רווח / הפסד נקי",
        f"{profit_sign}${c['net_profit']:,.2f}",
        f"{profit_sign}{c['roi_pct']:.1f}% ROI",
    )
with m3:
    st.metric(
        "📊 חלק יחסי מהתיק",
        f"{share_pct:.2f}%",
        f"NAV: ${total_nav:,.0f}",
    )
with m4:
    st.metric(
        "🏦 שווי ברוטו",
        f"${c['gross']:,.2f}",
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Metric row 2: deductions ─────────────────────────────────────
if not is_exempt and c["raw_profit"] > 0:
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.metric("💼 השקעה ראשונית",     f"${investment:,.2f}")
    with f2:
        st.metric("🧾 עמלות ברוקר",       f"${fees:,.2f}")
    with f3:
        st.metric("🏛️ מס רווח הון (25%)", f"${c['tax']:,.2f}")
    with f4:
        st.metric("⚡ דמי הצלחה (20%)",   f"${c['perf']:,.2f}")
else:
    f1, f2 = st.columns(2)
    with f1:
        st.metric("💼 השקעה ראשונית", f"${investment:,.2f}")
    with f2:
        st.metric("🧾 עמלות ברוקר",   f"${fees:,.2f}")
    if is_exempt:
        st.success("✅ פטור ממס רווח הון ודמי הצלחה")

st.divider()

# ════════════════════════════════════════════════════════════════
# 14. PLOTLY CHART — two-point bar (Investment → Net Value)
# ════════════════════════════════════════════════════════════════
bar_color = "#3fb950" if c["net_value"] >= investment else "#f85149"

fig = go.Figure()

# Main bars
fig.add_trace(go.Bar(
    name="ערכים",
    x=["השקעה ראשונית", "שווי נוכחי נקי"],
    y=[investment, c["net_value"]],
    marker=dict(
        color=["#1a6fc4", bar_color],
        line=dict(color=["#2080d8", bar_color], width=1),
    ),
    text=[f"${investment:,.0f}", f"${c['net_value']:,.0f}"],
    textposition="outside",
    textfont=dict(color="#dce6f5", size=15, family="Arial"),
    width=[0.35, 0.35],
))

# Gross value ghost bar for context
fig.add_trace(go.Bar(
    name="שווי ברוטו",
    x=["—", "שווי ברוטו"],
    y=[0, c["gross"]],
    marker=dict(color=["rgba(0,0,0,0)", "rgba(77,163,255,0.25)"],
                line=dict(color=["rgba(0,0,0,0)", "#4da3ff"], width=1)),
    text=["", f"${c['gross']:,.0f}"],
    textposition="outside",
    textfont=dict(color="#4da3ff", size=13),
    width=[0, 0.35],
    showlegend=True,
))

fig.add_hline(
    y=investment,
    line_dash="dot",
    line_color="#d29922",
    line_width=1.5,
    annotation_text=f"  נקודת איזון: ${investment:,.0f}",
    annotation_position="top right",
    annotation_font=dict(color="#d29922", size=12),
)

fig.update_layout(
    title=dict(
        text="📊 מסלול ביצועים — השקעה לעומת שווי נוכחי",
        font=dict(size=18, color="#4da3ff"),
        x=0.5,
    ),
    plot_bgcolor="#0a0e1a",
    paper_bgcolor="#0a0e1a",
    font=dict(color="#dce6f5", family="Arial"),
    xaxis=dict(
        tickfont=dict(size=13, color="#7fafd4"),
        showgrid=False,
        showline=True,
        linecolor="#1e3a5f",
    ),
    yaxis=dict(
        tickprefix="$",
        tickformat=",.0f",
        gridcolor="#111827",
        gridwidth=1,
        tickfont=dict(color="#7fafd4"),
    ),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="#1e3a5f",
        font=dict(color="#7fafd4"),
    ),
    margin=dict(t=70, b=40, l=70, r=40),
    height=440,
    barmode="overlay",
)

st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# 15. DETAILED BREAKDOWN TABLE
# ════════════════════════════════════════════════════════════════
st.divider()
st.markdown("### 📋 פירוט חישוב מלא")

breakdown_items = [
    ("🏦 NAV כולל IBKR",               f"${total_nav:,.2f}"),
    (f"📊 חלק יחסי ({share_pct:.2f}%)", f"${c['gross']:,.2f}"),
    ("💼 השקעה ראשונית",                f"${investment:,.2f}"),
    ("🧾 עמלות / פעולות",               f"${fees:,.2f}"),
    ("💹 רווח גולמי",                   f"${c['raw_profit']:,.2f}"),
    (
        "🏛️ מס רווח הון (25%)",
        f"${c['tax']:,.2f}" if not is_exempt else "פטור ✅",
    ),
    (
        "⚡ דמי הצלחה (20%)",
        f"${c['perf']:,.2f}" if not is_exempt else "פטור ✅",
    ),
    ("✅ רווח נקי סופי",                f"${c['net_profit']:,.2f}"),
    ("🏆 יתרה נטו",                     f"${c['net_value']:,.2f}"),
]

df_breakdown = pd.DataFrame(breakdown_items, columns=["פריט", "סכום"])
st.dataframe(df_breakdown, hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# 16. FOOTER — data source badge
# ════════════════════════════════════════════════════════════════
st.divider()
_src = st.session_state.nav_source
if "חי ✓" in _src:
    _col, _ico = "#3fb950", "🟢"
elif "אחרון ידוע" in _src:
    _col, _ico = "#d29922", "🟡"
else:
    _col, _ico = "#f85149", "🔴"

st.markdown(
    f"<small style='color:{_col}'>{_ico} מקור נתונים: {_src}</small>",
    unsafe_allow_html=True,
)
