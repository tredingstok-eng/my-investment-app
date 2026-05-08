import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY = "1492787" 
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

st.set_page_config(page_title="Debug Mode", layout="wide")
st.markdown("<style> * { direction: rtl; text-align: right; } </style>", unsafe_allow_html=True)

if 'total_nav' not in st.session_state: 
    st.session_state.total_nav = 6131.72

def debug_fetch():
    try:
        st.write("📡 שולח בקשה לאינטראקטיב...")
        # שימוש ב-Timeout כדי למנוע תקיעה
        r = requests.get(f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY}&v=3", timeout=15)
        
        if "ErrorCode" in r.text:
            st.error(f"שגיאה מאינטראקטיב: {r.text}")
            return None
            
        root = ET.fromstring(r.content)
        status_elem = root.find("Status")
        
        if status_elem is not None and status_elem.text == "Success":
            code = root.find('ReferenceCode').text
            url = root.find('Url').text
            st.info(f"הבקשה הצליחה. קוד: {code}. מחכה 12 שניות לייצור הקובץ...")
            
            time.sleep(12)
            res = requests.get(f"{url}?q={code}&t={IB_TOKEN}", timeout=15)
            
            if b"NetAssetValue" in res.content:
                d_root = ET.fromstring(res.content)
                navs = [float(n.get("total")) for n in d_root.findall(".//NetAssetValue") if n.get("total")]
                if navs:
                    new_val = max(navs)
                    st.success(f"הצלחתי! המספר המעודכן הוא: ${new_val:,.2f}")
                    return new_val
                else:
                    st.warning("הקובץ התקבל אבל לא נמצאו נתוני NAV בתוכו. וודא שב-Flex Query סימנת את סעיף Net Asset Value.")
            else:
                st.error("התקבל קובץ ריק או לא תקין מאינטראקטיב.")
        else:
            st.error(f"אינטראקטיב החזיר סטטוס שגיאה: {r.text}")
    except Exception as e:
        st.error(f"שגיאה טכנית: {str(e)}")
    return None

st.title("מערכת בדיקת סנכרון IBKR")

if st.button("בצע בדיקה עכשיו"):
    val = debug_fetch()
    if val:
        st.session_state.total_nav = val
    st.rerun()

st.write("---")
st.header(f"המספר השמור כרגע: ${st.session_state.total_nav:,.2f}")

if st.checkbox("הצג נתונים מגוגל שיטס (לוודא חיבור)"):
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        st.dataframe(df)
    except:
        st.error("לא מצליח להתחבר לגוגל שיטס")
