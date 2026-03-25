import streamlit as st
import pandas as pd

# הגדרות
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0

# הקישור שנתת (המרתי אותו לפורמט CSV כדי שהקוד יקרא אותו)
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

def load_data():
    try:
        # קריאת הנתונים מהגוגל שיטס
        df = pd.read_csv(SHEET_URL)
        return df
    except Exception as e:
        st.error(f"שגיאה בטעינת הנתונים: {e}")
        return None

def calculate_fees(initial_inv, current_gross, action_count):
    total_action_fees = (action_count + 1) * ACTION_FEE_USD
    gross_profit = current_gross - initial_inv - total_action_fees
    
    if gross_profit > 0:
        tax = gross_profit * TAX_RATE
        commission = (gross_profit - tax) * SUCCESS_FEE
        net = current_gross - tax - commission
    else:
        tax, commission = 0, 0
        net = current_gross - total_action_fees
    return net, tax, commission, total_action_fees

st.set_page_config(page_title="Investment Tracker", page_icon="📈", layout="centered")
st.title("📈 מעקב השקעות אישי")

df = load_data()

if df is not None:
    # ניקוי שמות העמודות (במקרה שיש רווחים)
    df.columns = df.columns.str.strip()
    
    user_code = st.text_input("הכנס קוד אישי (4 ספרות):", type="password")
    
    if user_code:
        # חיפוש המשתמש - וודא שבשיטס העמודה נקראת "קוד אישי"
        user_row = df[df['קוד אישי'].astype(str) == user_code]
        
        if not user_row.empty:
            user_data = user_row.iloc[0]
            st.subheader(f"שלום, {user_data['שם הלקוח']}")
            
            # לוגיקה למשיכת שווי התיק (מניח שיש עמודה בשם 'אחוז נוכחי בתיק')
            # הערה: כאן הגדרתי שווי תיק כללי של 100,000 דולר כדוגמה
            total_portfolio = 100000 
            current_gross = total_portfolio * (float(user_data['אחוז נוכחי בתיק']) / 100)
            
            net, tax, comm, act_fees = calculate_fees(
                float(user_data['סכום הפקדה מקורי ($)']), 
                current_gross, 
                int(user_data['כמות פעולות'])
            )
            
            # תצוגה
            st.metric("יתרה נטו למשיכה ($)", f"${net:,.2f}")
            
            with st.expander("ראה פירוט מלא (מיסים ועמלות)"):
                st.write(f"💰 שווי ברוטו בתיק: ${current_gross:,.2f}")
                st.write(f"📉 מס רווח הון (25%): ${tax:,.2f}")
                st.write(f"👤 עמלת הצלחה (20%): ${comm:,.2f}")
                st.write(f"⚙️ עמלות פעולה מצטברות: ${act_fees:,.2f}")
        else:
            st.error("הקוד לא נמצא במערכת.")
