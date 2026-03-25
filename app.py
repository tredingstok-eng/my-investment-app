import streamlit as st
import pandas as pd

# הגדרות
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0

# הקישור המעודכן שלך
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

def load_data():
    try:
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
        tax, commission, net = 0, 0, current_gross - total_action_fees
    return net, tax, commission, total_action_fees

st.set_page_config(page_title="Investment Tracker", page_icon="📈")
st.title("📈 מעקב השקעות אישי")

df = load_data()

if df is not None:
    user_code = st.text_input("הכנס קוד אישי (4 ספרות):", type="password")
    
    if user_code:
        # פתרון "חכם": אנחנו מחפשים את הקוד בעמודה השנייה (B) בטבלה
        # זה חוסך בעיות של שמות עמודות בעברית
        code_col = df.columns[1] 
        user_row = df[df[code_col].astype(str) == user_code]
        
        if not user_row.empty:
            user_data = user_row.iloc[0]
            # עמודה 0 = שם, 1 = קוד, 2 = הפקדה, 3 = אחוז, 4 = פעולות
            name = user_data.iloc[0]
            st.subheader(f"שלום, {name}")
            
            # שווי תיק לדוגמה (אפשר לשנות לערך האמיתי ב-IBKR)
            total_portfolio = 100000 
            
            inv = float(user_data.iloc[2])
            perc = float(str(user_data.iloc[3]).replace('%', ''))
            actions = int(user_data.iloc[4])
            
            current_gross = total_portfolio * (perc / 100)
            net, tax, comm, act_fees = calculate_fees(inv, current_gross, actions)
            
            st.metric("יתרה נטו למשיכה ($)", f"${net:,.2f}")
            
            with st.expander("ראה פירוט מלא"):
                st.write(f"💰 שווי ברוטו בתיק: ${current_gross:,.2f}")
                st.write(f"📉 מס רווח הון (25%): ${tax:,.2f}")
                st.write(f"👤 עמלת הצלחה (20%): ${comm:,.2f}")
                st.write(f"⚙️ עמלות פעולה: ${act_fees:,.2f}")
        else:
            st.error("הקוד לא נמצא.")
