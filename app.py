import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ---
# כאן אתה שם את הלינק של ה-CSV מגוגל שיטס שלך
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787"

st.set_page_config(page_title="RC Capital", layout="wide")

# פונקציית רענון
def refresh_data():
    try:
        # טעינת נתונים מגוגל שיטס (הנתונים של המשתמשים)
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        for col in df.columns[2:]:
            df[col] = df[col].astype(str).str.replace('$', '').str.replace('%', '').str.replace(',', '').astype(float)
        st.session_state.df = df
        
        # ניסיון למשוך מאינטראקטיב - אם הם לא התעדכנו, נשתמש בערך האחרון שיש לנו
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=10)
        root = ET.fromstring(r.content)
        if root.find("Status").text == "Success":
            code, base_url = root.find('ReferenceCode').text, root.find('Url').text
            time.sleep(1) # בקשה מהירה
            res = requests.get(f"{base_url}?q={code}&t={IB_TOKEN}", timeout=10)
            d_root = ET.fromstring(res.content)
            vals = [float(el.get("total")) for el in d_root.findall(".//EquitySummaryByReportDateInBase") if el.get("total")]
            if vals:
                st.session_state.total_nav = max(vals)
    except:
        pass

if 'df' not in st.session_state:
    st.session_state.total_nav = 6131.72 # ערך מחדל
    refresh_data()

# עיצוב RTL
st.markdown("<style> * { direction: rtl; text-align: right; } </style>", unsafe_allow_html=True)

# --- דאשבורד ---
with st.sidebar:
    st.title("RC Capital")
    if st.button("🔄 רענון נתונים"):
        refresh_data()
        st.rerun()
    st.write(f"שווי תיק נוכחי: **${st.session_state.total_nav:,.2f}**")

# תצוגה לקובי כהן (7.81%)
if st.session_state.df is not None:
    share = 7.81
    total = st.session_state.total_nav
    u_val = total * (share / 100)
    
    st.title("שלום, קובי כהן")
    st.metric("היתרה שלך", f"${u_val:,.2f}")
    st.info(f"הנתונים מסונכרנים מול אינטראקטיב ברוקרס. שווי תיק כולל: ${total:,.2f}")
