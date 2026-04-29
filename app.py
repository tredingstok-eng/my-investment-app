"""
RC Capital — Investment Dashboard  v4.0
========================================
Column names taken directly from the live Google Sheet:
  שם הלקח               → name
  קוד אישי               → pin
  סכום הפקדה מקרי ($)   → investment
  אחוז נוכחי בתיק        → share %
  כמות פעולות (עמלה 1$) → fees (each action = $1)
  שווי תיק               → (ignored – we use live IBKR NAV instead)
"""

import time
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st

# ═══════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════
IB_TOKEN  = "837126977366730658372732"
IB_QUERY  = "1489351"
SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV"
    "/pub?output=csv"
)

ADMIN_PIN    = "0000"
FALLBACK_NAV = 6_131.72
ADMIN_NAME   = "רפאל"      # substring → tax exempt
TAX_RATE     = 0.25
PERF_RATE    = 0.20
IL_TZ        = pytz.timezone("Asia/Jerusalem")

# ═══════════════════════════════════════════════════════════
# EXACT COLUMN NAMES (from the live sheet screenshot)
# Change these strings if the sheet columns are ever renamed.
# ═══════════════════════════════════════════════════════════
COL_NAME       = "שם הלקח"
COL_PIN        = "קוד אישי"
COL_INVESTMENT = "סכום הפקדה מקרי ($)"
COL_SHARE      = "אחוז נוכחי בתיק"
COL_ACTIONS    = "כמות פעולות (עמלה 1$)"   # each action costs $1
FEE_PER_ACTION = 1.0                         # $1 per action/trade


# ═══════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════
st.set_page_config(
    page_title="RC Capital",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"],
[data-testid="stHeader"], [data-testid="stToolbar"] {
    background-color: #0a0e1a !important;
    color: #dce6f5 !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#0d1321,#111827) !important;
    border-right: 1px solid #1e2d45;
}
html, body, * { direction: rtl !important; }
.stTextInput input { text-align: right; }
h1 { font-size:2.2rem !important; letter-spacing:-0.5px; }
h1,h2,h3 { color:#4da3ff !important; font-weight:700 !important; }
[data-testid="metric-container"] {
    background: linear-gradient(135deg,#0d1b2e,#112240);
    border: 1px solid #1e3a5f;
    border-radius: 14px;
    padding: 20px 24px;
}
[data-testid="metric-container"]:hover { border-color:#4da3ff; }
[data-testid="stMetricLabel"]  { color:#7fafd4 !important; font-size:.85rem !important; }
[data-testid="stMetricValue"]  { color:#fff    !important; font-size:1.7rem !important; font-weight:800 !important; }
.stButton > button {
    background: linear-gradient(135deg,#1a6fc4,#155fa0);
    color:#fff; border:none; border-radius:8px;
    width:100%; font-size:.95rem; font-weight:600; padding:.55rem 1.2rem;
}
.stButton > button:hover {
    background: linear-gradient(135deg,#2080d8,#1a6fc4);
    box-shadow: 0 4px 16px rgba(77,163,255,.3);
    transform: translateY(-1px);
}
hr { border-color:#1e3a5f !important; }
.badge-live  { color:#3fb950; font-weight:700; }
.badge-stale { color:#d29922; font-weight:700; }
.badge-dead  { color:#f85149; font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════
_defs = dict(
    total_nav=None, nav_source="לא נטען", nav_ts=None,
    last_refresh=None, authenticated=False,
    current_user=None, is_admin=False,
)
for k, v in _defs.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════════
# IBKR FLEX QUERY — robust retry loop
# ═══════════════════════════════════════════════════════════
def fetch_ibkr_nav(max_attempts=8, delay_s=5):
    try:
        r1 = requests.get(
            "https://www.interactivebrokers.com/Universal/servlet/"
            f"FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3",
            timeout=30,
        )
        r1.raise_for_status()
        root1 = ET.fromstring(r1.content)
        status = root1.find("Status")
        if status is None or status.text != "Success":
            err = root1.find("ErrorMessage")
            return None, f"IBKR שלב 1 נכשל: {err.text if err is not None else 'סטטוס לא ידוע'}"

        ref_url  = root1.find("Url").text.strip()
        ref_code = root1.find("ReferenceCode").text.strip()

        for attempt in range(1, max_attempts + 1):
            time.sleep(delay_s)
            r2      = requests.get(f"{ref_url}?q={ref_code}&t={IB_TOKEN}", timeout=30)
            content = r2.content
            if b"NetAssetValue" not in content:
                try:
                    er = ET.fromstring(content).find("ErrorMessage")
                    if er is not None and "try again" in er.text.lower():
                        continue
                except ET.ParseError:
                    pass
                continue
            navs = [
                float(n.get("total"))
                for n in ET.fromstring(content).findall(".//NetAssetValue")
                if n.get("total") and n.get("total") not in ("", "0", "0.0")
            ]
            if navs:
                return max(navs), f"IBKR חי ✓ (ניסיון {attempt})"
        return None, f"לא נמצא NAV לאחר {max_attempts} ניסיונות"
    except requests.exceptions.Timeout:
        return None, "IBKR: timeout"
    except requests.exceptions.ConnectionError:
        return None, "IBKR: שגיאת חיבור"
    except Exception as e:
        return None, f"IBKR: שגיאה – {e}"


def resolve_nav():
    with st.spinner("📡 מושך נתונים מ-IBKR… (עד 40 שניות)"):
        nav, source = fetch_ibkr_nav()
    if nav and nav > 0:
        st.session_state.total_nav  = nav
        st.session_state.nav_source = source
        st.session_state.nav_ts     = datetime.now(IL_TZ)
    elif st.session_state.total_nav and st.session_state.total_nav > 0:
        st.session_state.nav_source = f"ערך אחרון ידוע ⚠️ ({source})"
    else:
        st.session_state.total_nav  = FALLBACK_NAV
        st.session_state.nav_source = f"ערך ברירת מחדל 🔴 ({source})"
    st.session_state.last_refresh = datetime.now(IL_TZ).strftime("%d/%m/%Y %H:%M:%S")


# ═══════════════════════════════════════════════════════════
# GOOGLE SHEETS — cache-busted
# ═══════════════════════════════════════════════════════════
@st.cache_data(ttl=0)
def load_sheet(bust: str) -> pd.DataFrame:
    df = pd.read_csv(f"{SHEET_URL}&cachebust={bust}")
    df.columns = df.columns.str.strip()
    return df


def safe_float(val, default=0.0) -> float:
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except Exception:
        return default


# ═══════════════════════════════════════════════════════════
# CALCULATIONS
# ═══════════════════════════════════════════════════════════
def calc_user(total_nav, investment, share_pct, actions, exempt):
    fees       = actions * FEE_PER_ACTION
    gross      = total_nav * (share_pct / 100)
    raw_profit = gross - investment - fees
    if exempt or raw_profit <= 0:
        tax  = 0.0
        perf = 0.0
    else:
        tax  = raw_profit * TAX_RATE
        perf = raw_profit * PERF_RATE
    net_profit = raw_profit - tax - perf
    net_value  = investment + net_profit
    roi_pct    = (net_profit / investment * 100) if investment else 0
    return dict(
        fees=fees, gross=gross, raw_profit=raw_profit,
        tax=tax, perf=perf, net_profit=net_profit,
        net_value=net_value, roi_pct=roi_pct,
    )


# ═══════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ הגדרות")
    if st.button("🔄  רענן נתונים"):
        load_sheet.clear()
        resolve_nav()
        st.rerun()
    st.divider()

    _nav = st.session_state.total_nav
    _src = st.session_state.nav_source
    if _nav and _nav > 0:
        _badge = (
            '<span class="badge-live">● Live</span>'         if "חי ✓"       in _src else
            '<span class="badge-stale">● ערך אחרון</span>'  if "אחרון ידוע" in _src else
            '<span class="badge-dead">● ברירת מחדל</span>'
        )
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
            for k in ("authenticated", "is_admin"):
                st.session_state[k] = False
            st.session_state.current_user = None
            st.rerun()

# ═══════════════════════════════════════════════════════════
# INITIAL NAV LOAD
# ═══════════════════════════════════════════════════════════
if st.session_state.total_nav is None:
    resolve_nav()

# ═══════════════════════════════════════════════════════════
# LOGIN
# ═══════════════════════════════════════════════════════════
if not st.session_state.authenticated:
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:0'>🏦 RC Capital</h1>"
        "<p style='text-align:center;color:#7fafd4;margin-top:4px'>פורטל לקוחות פרטי</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    bust = str(int(time.time()))
    try:
        df = load_sheet(bust)
    except Exception as e:
        st.error(f"❌ שגיאה בטעינת הגיליון: {e}")
        st.stop()

    # ── debug expander ──
    with st.expander("🔍 אבחון גיליון", expanded=False):
        st.markdown("**עמודות שנמצאו:**")
        st.code(list(df.columns))
        st.dataframe(df.head(3))

    # ── verify required columns exist ──
    missing = [c for c in (COL_NAME, COL_PIN) if c not in df.columns]
    if missing:
        st.error(
            f"❌ עמודות חובה לא נמצאו: `{missing}`\n\n"
            f"עמודות בגיליון: `{list(df.columns)}`\n\n"
            f"עדכן את `COL_NAME` ו-`COL_PIN` בראש הקוד."
        )
        st.stop()

    # ── PIN input ──
    _, center, _ = st.columns([1, 1.4, 1])
    with center:
        st.markdown("""
        <div style='background:linear-gradient(135deg,#0d1b2e,#112240);
                    border:1px solid #1e3a5f;border-radius:16px;
                    padding:36px 40px;'>
        """, unsafe_allow_html=True)
        st.markdown("### 🔐 כניסה לחשבון")
        pin_input = st.text_input("הכנס קוד PIN", type="password",
                                   placeholder="••••••", key="pin_field")
        if st.button("כניסה  →"):
            if pin_input.strip() == ADMIN_PIN:
                st.session_state.authenticated = True
                st.session_state.current_user  = "מנהל"
                st.session_state.is_admin      = True
                st.rerun()

            df["_pin"] = df[COL_PIN].astype(str).str.strip()
            match = df[df["_pin"] == pin_input.strip()]
            if not match.empty:
                st.session_state.authenticated = True
                st.session_state.current_user  = str(match.iloc[0][COL_NAME]).strip()
                st.session_state.is_admin      = False
                st.rerun()
            else:
                st.error("❌ קוד PIN שגוי. נסה שוב.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# ═══════════════════════════════════════════════════════════
# ADMIN VIEW  (PIN 0000)
# ═══════════════════════════════════════════════════════════
if st.session_state.is_admin:
    st.markdown("# 🏦 RC Capital — ניהול")
    st.divider()

    bust = str(int(time.time() // 60))
    try:
        df = load_sheet(bust)
    except Exception as e:
        st.error(f"❌ {e}")
        st.stop()

    total_nav = st.session_state.total_nav
    st.metric("🏦 NAV כולל (IBKR)", f"${total_nav:,.2f}")
    st.divider()

    # Full raw table
    st.markdown("### 📋 גיליון לקוחות")
    st.dataframe(df, use_container_width=True)

    # Calculated summary
    st.divider()
    st.markdown("### 📊 סיכום ביצועים")
    rows = []
    for _, row in df.iterrows():
        try:
            name       = str(row[COL_NAME]).strip()
            if not name or name.lower() in ("nan", ""):
                continue
            investment = safe_float(row.get(COL_INVESTMENT, 0))
            share_pct  = safe_float(row.get(COL_SHARE, 0))
            actions    = safe_float(row.get(COL_ACTIONS, 0))
            exempt     = ADMIN_NAME in name
            c          = calc_user(total_nav, investment, share_pct, actions, exempt)
            rows.append({
                "שם":           name,
                "השקעה":        f"${investment:,.0f}",
                "חלק %":        f"{share_pct:.2f}%",
                "שווי ברוטו":   f"${c['gross']:,.2f}",
                "יתרה נטו":     f"${c['net_value']:,.2f}",
                "רווח נקי":     f"${c['net_profit']:,.2f}",
                "ROI":          f"{c['roi_pct']:+.1f}%",
                "פטור ממס":     "✅" if exempt else "❌",
            })
        except Exception:
            continue
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.stop()

# ═══════════════════════════════════════════════════════════
# USER DASHBOARD
# ═══════════════════════════════════════════════════════════
bust = str(int(time.time() // 300))
try:
    df = load_sheet(bust)
except Exception as e:
    st.error(f"❌ שגיאה בטעינת הגיליון: {e}")
    st.stop()

df["_name"] = df[COL_NAME].astype(str).str.strip()
user_row = df[df["_name"] == st.session_state.current_user]
if user_row.empty:
    st.error("המשתמש לא נמצא בגיליון.")
    st.stop()

row        = user_row.iloc[0]
user_name  = str(row[COL_NAME]).strip()
investment = safe_float(row.get(COL_INVESTMENT, 0))
share_pct  = safe_float(row.get(COL_SHARE, 0))
actions    = safe_float(row.get(COL_ACTIONS, 0))
is_exempt  = ADMIN_NAME in user_name
total_nav  = st.session_state.total_nav

c = calc_user(total_nav, investment, share_pct, actions, is_exempt)

# ── Header ──
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown("# 🏦 RC Capital")
    st.markdown(f"### שלום, {user_name} 👋")
with col_h2:
    st.markdown(
        f"<div style='color:#7fafd4;padding-top:30px;text-align:left'>"
        f"<small>{datetime.now(IL_TZ).strftime('%d/%m/%Y  %H:%M')}</small></div>",
        unsafe_allow_html=True,
    )

st.divider()

# ── KPI row ──
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("💰 יתרה נטו",            f"${c['net_value']:,.2f}",
              f"{c['roi_pct']:+.2f}%")
with m2:
    sign = "+" if c["net_profit"] >= 0 else ""
    st.metric("📈 רווח / הפסד נקי",     f"{sign}${c['net_profit']:,.2f}",
              f"{sign}{c['roi_pct']:.1f}% ROI")
with m3:
    st.metric("📊 חלק יחסי בתיק",       f"{share_pct:.2f}%",
              f"NAV: ${total_nav:,.0f}")
with m4:
    st.metric("🏦 שווי ברוטו",           f"${c['gross']:,.2f}")

st.markdown("<br>", unsafe_allow_html=True)

# ── Deductions row ──
if not is_exempt and c["raw_profit"] > 0:
    f1, f2, f3, f4 = st.columns(4)
    with f1: st.metric("💼 השקעה ראשונית",     f"${investment:,.2f}")
    with f2: st.metric("🧾 עמלות פעולות",       f"${c['fees']:,.2f}",
                        f"{int(actions)} פעולות × $1")
    with f3: st.metric("🏛️ מס רווח הון (25%)", f"${c['tax']:,.2f}")
    with f4: st.metric("⚡ דמי הצלחה (20%)",   f"${c['perf']:,.2f}")
else:
    f1, f2 = st.columns(2)
    with f1: st.metric("💼 השקעה ראשונית", f"${investment:,.2f}")
    with f2: st.metric("🧾 עמלות פעולות",   f"${c['fees']:,.2f}",
                        f"{int(actions)} פעולות × $1")
    if is_exempt:
        st.success("✅ פטור ממס רווח הון ודמי הצלחה")

st.divider()

# ── Chart ──
bar_color = "#3fb950" if c["net_value"] >= investment else "#f85149"
fig = go.Figure()
fig.add_trace(go.Bar(
    x=["השקעה ראשונית", "שווי נוכחי נקי"],
    y=[investment, c["net_value"]],
    marker=dict(color=["#1a6fc4", bar_color]),
    text=[f"${investment:,.0f}", f"${c['net_value']:,.0f}"],
    textposition="outside",
    textfont=dict(color="#dce6f5", size=15),
    width=[0.35, 0.35],
))
fig.add_hline(
    y=investment, line_dash="dot", line_color="#d29922", line_width=1.5,
    annotation_text=f"  נקודת איזון: ${investment:,.0f}",
    annotation_position="top right",
    annotation_font=dict(color="#d29922", size=12),
)
fig.update_layout(
    title=dict(text="📊 השקעה לעומת שווי נוכחי",
               font=dict(size=18, color="#4da3ff"), x=0.5),
    plot_bgcolor="#0a0e1a", paper_bgcolor="#0a0e1a",
    font=dict(color="#dce6f5"),
    xaxis=dict(tickfont=dict(size=13, color="#7fafd4"), showgrid=False,
               showline=True, linecolor="#1e3a5f"),
    yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#111827"),
    margin=dict(t=70, b=40, l=70, r=40), height=420, showlegend=False,
)
st.plotly_chart(fig, use_container_width=True)

# ── Breakdown table ──
st.divider()
st.markdown("### 📋 פירוט חישוב")
st.dataframe(
    pd.DataFrame({
        "פריט": [
            "🏦 NAV כולל IBKR",
            f"📊 חלק יחסי ({share_pct:.2f}%)",
            "💼 השקעה ראשונית",
            f"🧾 עמלות ({int(actions)} פעולות × $1)",
            "💹 רווח גולמי",
            "🏛️ מס רווח הון (25%)" if not is_exempt else "🏛️ מס רווח הון",
            "⚡ דמי הצלחה (20%)"   if not is_exempt else "⚡ דמי הצלחה",
            "✅ רווח נקי סופי",
            "🏆 יתרה נטו",
        ],
        "סכום ($)": [
            f"${total_nav:,.2f}",
            f"${c['gross']:,.2f}",
            f"${investment:,.2f}",
            f"${c['fees']:,.2f}",
            f"${c['raw_profit']:,.2f}",
            f"${c['tax']:,.2f}"  if not is_exempt else "פטור ✅",
            f"${c['perf']:,.2f}" if not is_exempt else "פטור ✅",
            f"${c['net_profit']:,.2f}",
            f"${c['net_value']:,.2f}",
        ],
    }),
    hide_index=True, use_container_width=True,
)

# ── Footer ──
st.divider()
_src = st.session_state.nav_source
_col = "#3fb950" if "חי ✓" in _src else "#d29922" if "אחרון" in _src else "#f85149"
_ico = "🟢"      if "חי ✓" in _src else "🟡"      if "אחרון" in _src else "🔴"
st.markdown(
    f"<small style='color:{_col}'>{_ico} מקור נתונים: {_src}</small>",
    unsafe_allow_html=True,
)
