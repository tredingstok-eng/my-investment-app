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

# פונקציית ניקוי מספרים משופרת
def clean_num(val):
    try:
        if pd.isna(val): return 0.0
        s = str(val).replace('$', '').replace('%', '').replace(',', '').strip()
        return float(s)
    except: return 0.0

@st.cache_data(ttl=60)
def load_data():
    try:
        # הוספת קוד שמונע מהדפדפן לשמור גרסה ישנה של הגיליון
        df = pd.read_csv(f"{SHEET_URL}&cb={int(time.time())}")
        # ניקוי שמות עמודות מרווחים מיותרים
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"שגיאה בטעינת הגיליון: {e}")
        return None

# --- לוגיקה ---
df = load_data()

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🏦 RC Capital - כניסה")
    pwd = st.text_input("קוד גישה:", type="password")
    if st.button("התחבר"):
        if str(pwd) == ADMIN_CODE:
            st.session_state.auth = True
            st.session_state.pwd = ADMIN_CODE
            st.rerun()
        elif df is not None:
            # מחפש את הקוד בעמודה השנייה (אינדקס 1)
            user_codes = df.iloc[:, 1].astype(str).tolist()
            if str(pwd) in user_codes:
                st.session_state.auth = True
                st.session_state.pwd = str(pwd)
                st.rerun()
            else:
                st.error("קוד לא נמצא בגיליון")
else:
    # כפתור התנתקות
    if st.sidebar.button("התנתק"):
        st.session_state.auth = False
        st.rerun()

    if st.session_state.pwd == ADMIN_CODE:
        st.header("מצב מנהל")
        st.write("הנה מה שהקוד קורא מהגיליון שלך:")
        st.dataframe(df) # מציג את כל הטבלה כדי שתראה אם חסר משהו
    else:
        # ניסיון למצוא את המשתמש בצורה בטוחה
        try:
            user_data = df[df.iloc[:, 1].astype(str) == st.session_state.pwd].iloc[0]
            
            # שליפת נתונים לפי מיקום עמודה (0=שם, 2=הפקדה, 3=אחוז, 4=פעולות)
            name = user_data.iloc[0]
            inv = clean_num(user_data.iloc[2])
            share = clean_num(user_data.iloc[3])
            
            st.title(f"שלום, {name}")
            st.metric("הפקדה שזוהתה", f"${inv:,.2f}")
            st.metric("אחוז בתיק", f"{share}%")
            
            st.success("הנתונים נקראו בהצלחה! אם חסרים גרפים, זה השלב הבא.")
            
        except Exception as e:
            st.error(f"שגיאה בקריאת שורת המשתמש: {e}")
            st.write("נתוני השורה שמצאתי:")
            st.write(user_data)
