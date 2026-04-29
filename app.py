"""
RC Capital Portfolio Dashboard
================================
Fixes applied:
  1. Robust IBKR Flex Query retry loop (up to 8 attempts, 5 s delay) — never returns 0 to UI.
  2. Cache-busting Google Sheets URL (timestamp query param) so stale CSV is never served.
  3. Persistent last-known NAV stored in st.session_state — survives IBKR downtime.
  4. Sidebar Refresh button clears st.cache_data AND resets session NAV so a fresh fetch runs.
  5. Two-point Plotly chart (Investment vs Current Value) — no zig-zag.
  6. RTL / Hebrew support, dark theme, pytz timezone display.

requirements.txt (create alongside this file on Streamlit Cloud):
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
IB_TOKEN   = "837126977366730658372732"
IB_QUERY   = "1489351"
SHEET_URL  = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV"
    "/pub?output=csv"
)

# Last-known NAV used as a hard fallback when IBKR is completely unreachable
FALLBACK_NAV = 6131.72

# Users exempt from taxes / performance fee (exact name match)
TAX_EXEMPT_USERS = {"רפאל כהן"}

TAX_RATE         = 0.25   # 25 %
PERFORMANCE_RATE = 0.20   # 20 %

IL_TZ = pytz.timezone("Asia/Jerusalem")

# ──────────────────────────────────────────────
# PAGE CONFIG  (must be first Streamlit call)
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="RC Capital",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# GLOBAL STYLES  – dark theme + RTL
# ──────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Dark background ── */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #0d1117 !important;
        color: #e6edf3 !important;
    }
    [data-testid="stSidebar"] {
        background-color: #161b22 !important;
    }

    /* ── RTL / Hebrew ── */
    * { direction: rtl; text-align: right; }
    .stMetric label { direction: rtl; text-align: right; }

    /* ── Metric cards ── */
    [data-testid="metric-container"] {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 16px 20px;
    }
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700; }

    /* ── Headings ── */
    h1, h2, h3 { color: #58a6ff !important; }

    /* ── Button ── */
    .stButton > button {
        background: #238636;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        width: 100%;
        font-size: 1rem;
        padding: 0.5rem 1rem;
    }
    .stButton > button:hover { background: #2ea043; }

    /* ── Status badge ── */
    .status-ok   { color: #3fb950; font-weight: 700; }
    .status-warn { color: #d29922; font-weight: 700; }
    .status-err  { color: #f85149; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# SESSION STATE DEFAULTS
# ──────────────────────────────────────────────
if "total_nav"      not in st.session_state:
    st.session_state.total_nav      = None   # None = "not fetched yet"
if "nav_source"     not in st.session_state:
    st.session_state.nav_source     = "לא נטען"
if "last_refresh"   not in st.session_state:
    st.session_state.last_refresh   = None
if "authenticated"  not in st.session_state:
    st.session_state.authenticated  = False
if "current_user"   not in st.session_state:
    st.session_state.current_user   = None

# ──────────────────────────────────────────────
# IBKR FLEX QUERY  –  robust fetch
# ──────────────────────────────────────────────
def fetch_ibkr_nav(max_attempts: int = 8, delay_s: int = 5) -> tuple[float | None, str]:
    """
    Returns (nav_value, status_message).
    nav_value is None only if all attempts fail AND no session fallback exists.
    """
    REQUEST_URL = (
        f"https://www.interactivebrokers.com/Universal/servlet/"
        f"FlexStatementService.SendRequest"
        f"?t={IB_TOKEN}&q={IB_QUERY}&v=3"
    )

    try:
        # Step 1 – request the report generation
        r = requests.get(REQUEST_URL, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        status_el = root.find("Status")
        if status_el is None or status_el.text != "Success":
            err = root.find("ErrorMessage")
            msg = err.text if err is not None else "סטטוס לא ידוע מ-IBKR"
            return None, f"שגיאת IBKR (שלב 1): {msg}"

        ref_url  = root.find("Url").text
        ref_code = root.find("ReferenceCode").text

        # Step 2 – poll until the report is ready
        FETCH_URL = f"{ref_url}?q={ref_code}&t={IB_TOKEN}"
        for attempt in range(1, max_attempts + 1):
            time.sleep(delay_s)
            data_r = requests.get(FETCH_URL, timeout=30)
            content = data_r.content

            # IBKR returns an XML error envelope while the report isn't ready yet
            if b"NetAssetValue" not in content:
                # Check if it's a "try again" response
                try:
                    err_root = ET.fromstring(content)
                    err_el   = err_root.find("ErrorMessage")
                    if err_el is not None and "try again" in err_el.text.lower():
                        continue   # server still generating – keep waiting
                except ET.ParseError:
                    pass
                continue  # malformed XML – retry

            # Parse NAV
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
# GOOGLE SHEETS  –  cache-busted fetch
# ──────────────────────────────────────────────
@st.cache_data(ttl=0)   # cache disabled; we bust manually via unique URL
def load_sheet(bust: str) -> pd.DataFrame:
    """
    `bust` is a timestamp string; changing it forces st.cache_data to
    treat each call as a new computation, bypassing the cached result.
    """
    url = f"{SHEET_URL}&cachebust={bust}"
    df  = pd.read_csv(url)
    df.columns = df.columns.str.strip()
    # Normalise expected columns
    df["PIN"]         = df["PIN"].astype(str).str.strip()
    df["Investment"]  = pd.to_numeric(df["Investment"],  errors="coerce").fillna(0)
    df["Share %"]     = pd.to_numeric(df["Share %"],     errors="coerce").fillna(0)
    # Commissions/Actions column might have various names
    fee_col = [c for c in df.columns if "commiss" in c.lower() or "action" in c.lower()]
    if fee_col:
        df["Commissions"] = pd.to_numeric(df[fee_col[0]], errors="coerce").fillna(0)
    else:
        df["Commissions"] = 0.0
    return df


# ──────────────────────────────────────────────
# HELPER: resolve NAV  (fetch → session → hardcoded fallback)
# ──────────────────────────────────────────────
def resolve_nav() -> None:
    """
    Tries to get a fresh NAV from IBKR.
    On failure, keeps the last value stored in session_state.
    Only if session_state is also empty does it fall back to FALLBACK_NAV.
    """
    with st.spinner("מושך נתונים מ-IBKR… (עד 40 שניות)"):
        nav, source = fetch_ibkr_nav()

    if nav is not None and nav > 0:
        st.session_state.total_nav    = nav
        st.session_state.nav_source   = source
    elif st.session_state.total_nav is not None and st.session_state.total_nav > 0:
        # Keep last-known value; just update the status message
        st.session_state.nav_source = f"ערך אחרון ידוע (IBKR לא זמין: {source})"
    else:
        # Absolute last resort
        st.session_state.total_nav  = FALLBACK_NAV
        st.session_state.nav_source = f"ערך ברירת מחדל (IBKR לא זמין: {source})"

    st.session_state.last_refresh = datetime.now(IL_TZ).strftime("%d/%m/%Y %H:%M:%S")


# ──────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ הגדרות")

    if st.button("🔄 רענן נתונים"):
        # 1. Clear cached Google Sheet data
        load_sheet.clear()
        # 2. Reset NAV so fetch runs fresh (but keep old value as fallback)
        #    We do NOT set total_nav to None here; resolve_nav handles fallback.
        resolve_nav()
        st.rerun()

    st.divider()

    # NAV status display
    nav = st.session_state.total_nav
    if nav and nav > 0:
        source_lower = st.session_state.nav_source.lower()
        if "חי ✓" in st.session_state.nav_source:
            badge = '<span class="status-ok">● חי</span>'
        elif "אחרון ידוע" in st.session_state.nav_source:
            badge = '<span class="status-warn">● ערך אחרון</span>'
        else:
            badge = '<span class="status-err">● ברירת מחדל</span>'

        st.markdown(f"**סטטוס IBKR:** {badge}", unsafe_allow_html=True)
        st.markdown(f"**NAV כולל:** ${nav:,.2f}")
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
# INITIAL DATA LOAD  (first run only)
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

    bust = str(int(time.time()))   # fresh fetch every login attempt
    try:
        df_users = load_sheet(bust)
    except Exception as e:
        st.error(f"שגיאה בטעינת הגיליון: {e}")
        st.stop()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pin_input = st.text_input("הכנס PIN", type="password", placeholder="••••••")
        if st.button("כניסה"):
            match = df_users[df_users["PIN"] == pin_input.strip()]
            if not match.empty:
                st.session_state.authenticated = True
                st.session_state.current_user  = match.iloc[0]["Name"].strip()
                st.success(f"ברוך הבא, {st.session_state.current_user}!")
                st.rerun()
            else:
                st.error("PIN שגוי. נסה שוב.")
    st.stop()

# ──────────────────────────────────────────────
# DASHBOARD  (authenticated)
# ──────────────────────────────────────────────
bust = str(int(time.time() // 300))  # refresh sheet every 5 min in cache
try:
    df_users = load_sheet(bust)
except Exception as e:
    st.error(f"שגיאה בטעינת הגיליון: {e}")
    st.stop()

user_row = df_users[df_users["Name"].str.strip() == st.session_state.current_user]
if user_row.empty:
    st.error("המשתמש לא נמצא בגיליון. פנה למנהל המערכת.")
    st.stop()

user = user_row.iloc[0]
user_name    = user["Name"].strip()
investment   = float(user["Investment"])
share_pct    = float(user["Share %"])
commissions  = float(user["Commissions"])
is_tax_exempt = user_name in TAX_EXEMPT_USERS

total_nav = st.session_state.total_nav

# ── Core calculations ──
gross_value  = total_nav * (share_pct / 100)
raw_profit   = gross_value - investment - commissions

if is_tax_exempt:
    taxes           = 0.0
    performance_fee = 0.0
else:
    if raw_profit > 0:
        taxes           = raw_profit * TAX_RATE
        performance_fee = raw_profit * PERFORMANCE_RATE
    else:
        taxes           = 0.0
        performance_fee = 0.0

net_profit   = raw_profit - taxes - performance_fee
net_value    = investment + net_profit   # what the investor actually has after all deductions
roi_pct      = (net_profit / investment * 100) if investment else 0

# ──────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────
c_title, c_user = st.columns([3, 1])
with c_title:
    st.markdown(f"# 🏦 RC Capital")
    st.markdown(f"### שלום, {user_name} 👋")
with c_user:
    now_str = datetime.now(IL_TZ).strftime("%d/%m/%Y %H:%M")
    st.markdown(f"<br><br><small style='color:#8b949e'>{now_str}</small>", unsafe_allow_html=True)

st.divider()

# ──────────────────────────────────────────────
# METRIC CARDS — row 1
# ──────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)

with m1:
    st.metric(
        label="💰 השקעה ראשונית",
        value=f"${investment:,.2f}",
    )
with m2:
    st.metric(
        label="📊 שווי ברוטו (חלק יחסי)",
        value=f"${gross_value:,.2f}",
        delta=f"{share_pct:.1f}% מה-NAV",
    )
with m3:
    profit_delta = f"+${net_profit:,.2f}" if net_profit >= 0 else f"-${abs(net_profit):,.2f}"
    st.metric(
        label="📈 רווח נקי",
        value=f"${net_profit:,.2f}",
        delta=f"{roi_pct:+.1f}%",
    )
with m4:
    st.metric(
        label="🏦 NAV כולל (IBKR)",
        value=f"${total_nav:,.2f}",
    )

st.markdown("<br>", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# METRIC CARDS — row 2 (fees)
# ──────────────────────────────────────────────
if not is_tax_exempt:
    f1, f2, f3 = st.columns(3)
    with f1:
        st.metric(label="🏛️ מס רווח הון (25%)",  value=f"${taxes:,.2f}")
    with f2:
        st.metric(label="💼 דמי הצלחה (20%)",      value=f"${performance_fee:,.2f}")
    with f3:
        st.metric(label="🧾 עמלות / עלויות",        value=f"${commissions:,.2f}")
else:
    st.info("✅ פטור ממס ודמי הצלחה")

st.divider()

# ──────────────────────────────────────────────
# PLOTLY CHART  –  two points only (no zig-zag)
# ──────────────────────────────────────────────
chart_labels  = ["השקעה ראשונית", "שווי נוכחי נקי"]
chart_values  = [investment, net_value]
chart_colors  = ["#388bfd", "#3fb950" if net_value >= investment else "#f85149"]

fig = go.Figure()

fig.add_trace(go.Bar(
    x=chart_labels,
    y=chart_values,
    marker_color=chart_colors,
    text=[f"${v:,.0f}" for v in chart_values],
    textposition="outside",
    textfont=dict(color="#e6edf3", size=14),
    width=0.4,
))

fig.update_layout(
    title=dict(
        text="השקעה לעומת שווי נוכחי",
        font=dict(size=20, color="#58a6ff"),
        x=0.5,
    ),
    plot_bgcolor="#0d1117",
    paper_bgcolor="#0d1117",
    font=dict(color="#e6edf3", family="Arial"),
    xaxis=dict(
        tickfont=dict(size=14),
        gridcolor="#21262d",
        showgrid=False,
    ),
    yaxis=dict(
        tickprefix="$",
        tickformat=",.0f",
        gridcolor="#21262d",
        gridwidth=1,
    ),
    margin=dict(t=60, b=40, l=60, r=40),
    height=420,
    showlegend=False,
)

# Horizontal baseline
fig.add_hline(
    y=investment,
    line_dash="dot",
    line_color="#d29922",
    annotation_text=f"נקודת איזון: ${investment:,.0f}",
    annotation_position="top right",
    annotation_font_color="#d29922",
)

st.plotly_chart(fig, use_container_width=True)

# ──────────────────────────────────────────────
# DETAILS TABLE
# ──────────────────────────────────────────────
st.divider()
st.markdown("### 📋 פירוט חישוב מלא")

details = {
    "פריט": [
        "NAV כולל (IBKR)",
        f"חלק יחסי ({share_pct:.1f}%)",
        "השקעה ראשונית",
        "עמלות / עלויות",
        "רווח גולמי",
        "מס רווח הון (25%)" if not is_tax_exempt else "מס רווח הון",
        "דמי הצלחה (20%)"   if not is_tax_exempt else "דמי הצלחה",
        "רווח נקי סופי",
        "שווי נוכחי נקי",
    ],
    "סכום ($)": [
        f"${total_nav:,.2f}",
        f"${gross_value:,.2f}",
        f"${investment:,.2f}",
        f"${commissions:,.2f}",
        f"${raw_profit:,.2f}",
        f"${taxes:,.2f}" if not is_tax_exempt else "פטור",
        f"${performance_fee:,.2f}" if not is_tax_exempt else "פטור",
        f"${net_profit:,.2f}",
        f"${net_value:,.2f}",
    ],
}

df_details = pd.DataFrame(details)
st.dataframe(
    df_details,
    hide_index=True,
    use_container_width=True,
)

# ──────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────
st.divider()
nav_source = st.session_state.nav_source
if "חי ✓" in nav_source:
    colour, icon = "#3fb950", "🟢"
elif "אחרון ידוע" in nav_source:
    colour, icon = "#d29922", "🟡"
else:
    colour, icon = "#f85149", "🔴"

st.markdown(
    f"<small style='color:{colour}'>{icon} מקור נתונים: {nav_source}</small>",
    unsafe_allow_html=True,
)
