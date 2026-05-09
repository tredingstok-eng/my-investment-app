import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time
import plotly.graph_objects as go
from datetime import datetime

# --- הגדרות חיבור ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="RC Capital", layout="wide")

st.markdown("""
    <style>
    .main { direction: rtl; text-align: right; }
    div.stButton > button { width: 100%; }
    [data-testid="stSidebar"] { direction: rtl; }
    .nav-source { font-size: 12px; color: gray; margin-top: -10px; }
    </style>
    """, unsafe_allow_html=True)


def get_ibkr_nav():
    """משיכת NAV מ-IBKR Flex Query"""
    try:
        r = requests.get(
            f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
            f"?t={IB_TOKEN}&q={IB_QUERY}&v=3",
            timeout=10
        )
        st.sidebar.caption("📋 תגובת IBKR (שלב 1):")
        st.sidebar.code(r.text[:600])

        root = ET.fromstring(r.content)
        status = root.find("Status")

        if status is None:
            st.sidebar.error("❌ לא נמצא שדה Status בתגובה")
            return None

        if status.text != "Success":
            error_msg = root.find("ErrorMessage")
            st.sidebar.error(f"❌ סטטוס: {status.text} | שגיאה: {error_msg.text if error_msg is not None else 'לא ידוע'}")
            return None

        url = root.find('Url').text
        code = root.find('ReferenceCode').text
        time.sleep(2)

        res = requests.get(f"{url}?q={code}&t={IB_TOKEN}&_={int(time.time())}", timeout=10)
        st.sidebar.caption("📋 תגובת IBKR (שלב 2):")
        st.sidebar.code(res.text[:600])

        d_root = ET.fromstring(res.content)
        nav_elements = d_root.findall(".//EquitySummaryByReportDateInBase")

        if not nav_elements:
            st.sidebar.error("❌ לא נמצא שדה EquitySummaryByReportDateInBase ב-XML")
            return None

        vals = [float(el.get("total")) for el in nav_elements if el.get("total")]
        if vals:
            st.sidebar.success(f"✅ NAV נמשך בהצלחה: ${max(vals):,.2f}")
            return max(vals)

    except Exception as e:
        st.sidebar.error(f"❌ שגיאה: {e}")
    return None


def load_sheet():
    """טעינת גוגל שיטס — כולל עמודת Manual_NAV אם קיימת"""
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        # עמודת Manual_NAV (אופציונלית) — אם קיימת, שמור בנפרד
        manual_nav = None
        if "Manual_NAV" in df.columns:
            val = df["Manual_NAV"].dropna()
            if not val.empty:
                try:
                    manual_nav = float(str(val.iloc[0]).replace("$", "").replace(",", ""))
                except:
                    pass
            df = df.drop(columns=["Manual_NAV"])

        # ניקוי עמודות מספריות (עמודות 2 ומעלה)
        for col in df.columns[2:]:
            df[col] = (
                df[col].astype(str)
                .str.replace("$", "", regex=False)
                .str.replace("%", "", regex=False)
                .str.replace(",", "", regex=False)
                .astype(float)
            )
        return df, manual_nav
    except Exception as e:
        st.error(f"שגיאה בחיבור לגוגל שיטס: {e}")
        return None, None


# --- Session State ---
if "total_nav" not in st.session_state:
    st.session_state.total_nav = 6131.72
if "nav_source" not in st.session_state:
    st.session_state.nav_source = "ברירת מחדל"
if "nav_updated_at" not in st.session_state:
    st.session_state.nav_updated_at = None
if "df" not in st.session_state:
    st.session_state.df = None
if "auth" not in st.session_state:
    st.session_state.auth = False


def refresh_all():
    """
    סדר עדיפויות לעדכון NAV:
      1. Manual_NAV בגוגל שיטס  ← עדיפות ראשונה
      2. IBKR Flex Query API     ← אם השיטס ריק
      3. ערך קיים ב-Session      ← אם גם IBKR נכשל
    """
    df, manual_nav = load_sheet()
    if df is not None:
        st.session_state.df = df

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    if manual_nav is not None:
        # עדיפות 1 — ידני מהשיטס
        st.session_state.total_nav = manual_nav
        st.session_state.nav_source = "✏️ עדכון ידני (Google Sheets)"
        st.session_state.nav_updated_at = now_str
    else:
        # עדיפות 2 — IBKR
        ibkr_val = get_ibkr_nav()
        if ibkr_val:
            st.session_state.total_nav = ibkr_val
            st.session_state.nav_source = "📡 IBKR Flex Query"
            st.session_state.nav_updated_at = now_str
        else:
            # עדיפות 3 — ערך קיים
            st.session_state.nav_source = "⚠️ ערך אחרון ידוע (API לא זמין)"


# טעינה ראשונית
if st.session_state.df is None:
    refresh_all()


# ===================== ממשק כניסה =====================
if not st.session_state.auth:
    st.title("RC Capital — כניסת משקיעים")
    pin = st.text_input("הזן קוד PIN", type="password")
    if st.button("כניסה"):
        if pin == "0000":
            st.session_state.auth = True
            st.session_state.role = "admin"
            st.rerun()
        elif st.session_state.df is not None and str(pin) in st.session_state.df.iloc[:, 1].astype(str).values:
            st.session_state.auth = True
            st.session_state.role = "user"
            st.session_state.pin = str(pin)
            st.rerun()
        else:
            st.error("קוד PIN שגוי")

else:
    # ===================== סיידבר =====================
    with st.sidebar:
        st.header("ניהול תיק")
        st.metric("שווי תיק", f"${st.session_state.total_nav:,.2f}")
        st.markdown(f'<div class="nav-source">{st.session_state.nav_source}</div>', unsafe_allow_html=True)
        if st.session_state.nav_updated_at:
            st.caption(f"עודכן: {st.session_state.nav_updated_at}")

        if st.button("🔄 רענון נתונים"):
            refresh_all()
            st.rerun()

        # ---- עדכון ידני למנהל (גיבוי מהיר אם השיטס לא זמין) ----
        if st.session_state.role == "admin":
            st.markdown("---")
            st.markdown("**עדכון ידני (Admin)**")
            st.caption("השתמש בזה רק אם עמודת Manual_NAV בשיטס לא זמינה")
            manual_val = st.number_input(
                "שווי תיק ($)", 
                value=float(st.session_state.total_nav),
                min_value=0.0,
                step=100.0,
                format="%.2f"
            )
            if st.button("עדכן ידנית (Session בלבד)"):
                st.session_state.total_nav = manual_val
                st.session_state.nav_source = "✏️ עדכון ידני (Admin — Session)"
                st.session_state.nav_updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
                st.success(f"שווי עודכן ל-${manual_val:,.2f}")
                st.rerun()

        st.markdown("---")
        if st.button("התנתק"):
            st.session_state.auth = False
            st.rerun()

    # ===================== דאשבורד משתמש =====================
    if st.session_state.role == "user":
        user_row = st.session_state.df[
            st.session_state.df.iloc[:, 1].astype(str) == st.session_state.pin
        ].iloc[0]

        name = user_row.iloc[0]
        inv = user_row.iloc[2]
        share = user_row.iloc[3]

        current_gross = st.session_state.total_nav * (share / 100)
        profit = current_gross - inv
        tax = profit * 0.25 if profit > 0 and "רפאל" not in name else 0
        current_net = current_gross - tax
        pct_change = (profit / inv) * 100 if inv > 0 else 0

        st.title(f"שלום, {name} 👋")
        st.caption(f"מקור נתון: {st.session_state.nav_source}")

        col1, col2, col3 = st.columns(3)
        col1.metric("יתרה נטו (אחרי מס)", f"${current_net:,.2f}")
        col2.metric("רווח / הפסד", f"${profit:,.2f}", delta=f"{pct_change:.2f}%")
        col3.metric("נתח בתיק", f"{share}%")

        # גרף
        fig = go.Figure(go.Scatter(
            x=["השקעה מקורית", "שווי נוכחי נטו"],
            y=[inv, current_net],
            mode="lines+markers+text",
            text=[f"${inv:,.0f}", f"${current_net:,.0f}"],
            textposition="top center",
            line=dict(color="#4CAF50" if current_net >= inv else "#F44336", width=2),
            marker=dict(size=10)
        ))
        fig.update_layout(
            title="צמיחת ההשקעה",
            template="plotly_dark",
            yaxis_title="שווי ($)"
        )
        st.plotly_chart(fig, use_container_width=True)

    # ===================== דאשבורד מנהל =====================
    elif st.session_state.role == "admin":
        st.title("ממשק ניהול — RC Capital")

        st.info(
            "💡 **כדי לעדכן את שווי התיק לכולם:** הוסף עמודה בשם `Manual_NAV` לגיליון הראשון "
            "ורשום את הערך בשורה הראשונה מתחת לכותרת. "
            "לחץ 'רענון נתונים' ← הערך יתעדכן לכל המשקיעים מיד."
        )

        st.subheader("נתוני משקיעים")
        st.dataframe(st.session_state.df, use_container_width=True)
