import streamlit as st
import pandas as pd

# הגדרות
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0
ADMIN_CODE = "0000" 

SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

def load_data():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"שגיאה בטעינת הנתונים: {e}")
        return None

def calculate_metrics(initial_inv, current_gross, action_count):
    total_action_fees = (action_count + 1) * ACTION_FEE_USD
    gross_profit = current_gross - initial_inv - total_action_fees
    if gross_profit > 0:
        tax = gross_profit * TAX_RATE
        commission = (gross_profit - tax) * SUCCESS_FEE
        net_balance = current_gross - tax - commission
    else:
        tax, commission, net_balance = 0, 0, current_gross - total_action_fees
    
    net_profit_usd = net_balance - initial_inv
    profit_percent = (net_profit_usd / initial_inv) * 100 if initial_inv != 0 else 0
    return {"net_balance": net_balance, "net_profit_usd": net_profit_usd, "profit_percent": profit_percent, "tax": tax, "commission": commission, "action_fees": total_action_fees, "gross_rel": current_gross}

st.set_page_config(page_title="Investment Tracker", page_icon="📈")
st.title("📈 מערכת ניהול השקעות")

df = load_data()

if df is not None:
    # --- שליפת שווי התיק מהגיליון (עמודה G, שורה ראשונה בנתונים) ---
    try:
        # הקוד מחפש עמודה בשם 'שווי כולל'. וודא שכתבת ככה בדיוק בשיטס.
        total_portfolio = float(df['שווי כולל'].iloc[0])
    except:
        total_portfolio = 100000.0 # ברירת מחדל אם לא מצא
        st.warning("לא נמצאה עמודת 'שווי כולל' בשיטס, משתמש בברירת מחדל.")

    user_input = st.text_input("הכנס קוד גישה:", type="password")
    
    if user_input:
        if user_input == ADMIN_CODE:
            st.success(f"🔓 מצב מנהל | שווי תיק בשיטס: ${total_portfolio:,.0f}")
            summary_data = []
            for _, row in df.iterrows():
                try:
                    inv, perc, actions = float(row.iloc[2]), float(str(row.iloc[3]).replace('%', '')), int(row.iloc[4])
                    m = calculate_metrics(inv, total_portfolio * (perc / 100), actions)
                    summary_data.append({"שם": row.iloc[0], "נטו": f"${m['net_balance']:,.2f}", "רווח $": f"${m['net_profit_usd']:,.2f}", "רווח %": f"{m['profit_percent']:.2f}%"})
                except: continue
            st.table(pd.DataFrame(summary_data))
        else:
            user_row = df[df[df.columns[1]].astype(str) == user_input]
            if not user_row.empty:
                user_data = user_row.iloc[0]
                st.header(f"שלום, {user_data.iloc[0]}")
                inv, perc, actions = float(user_data.iloc[2]), float(str(user_data.iloc[3]).replace('%', '')), int(user_data.iloc[4])
                m = calculate_metrics(inv, total_portfolio * (perc / 100), actions)
                c1, c2, c3 = st.columns(3)
                c1.metric("יתרה נטו ($)", f"${m['net_balance']:,.2f}")
                c2.metric("רווח נטו ($)", f"${m['net_profit_usd']:,.2f}")
                c3.metric("תשואה", f"{m['profit_percent']:.2f}%")
