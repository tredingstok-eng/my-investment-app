import streamlit as st
import pandas as pd

# הגדרות מערכת
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0
ADMIN_CODE = "0000" 

# קישור לגיליון (CSV)
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

def load_data():
    try:
        # הוספת timestamp כדי למנוע Cache (מבטיח נתונים טריים מהשיטס)
        url = f"{SHEET_URL}&cache_bust={pd.Timestamp.now().timestamp()}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"שגיאה בחיבור לנתונים: {e}")
        return None

def calculate_metrics(initial_inv, current_gross, action_count):
    total_action_fees = (action_count + 1) * ACTION_FEE_USD
    gross_profit = current_gross - initial_inv - total_action_fees
    
    if gross_profit > 0:
        tax = gross_profit * TAX_RATE
        commission = (gross_profit - tax) * SUCCESS_FEE
        net_balance = current_gross - tax - commission
    else:
        tax, commission = 0, 0
        net_balance = current_gross - total_action_fees
    
    net_p_usd = net_balance - initial_inv
    p_perc = (net_p_usd / initial_inv) * 100 if initial_inv != 0 else 0
    
    return {
        "net": net_balance, "profit_usd": net_p_usd, "profit_perc": p_perc,
        "tax": tax, "comm": commission, "fees": total_action_fees, "gross": current_gross
    }

st.set_page_config(page_title="Investment Tracker", page_icon="📈")
st.title("📈 מערכת ניהול השקעות")

df = load_data()

if df is not None:
    # משיכת שווי תיק מעמודה G (שווי תיק)
    try:
        # לוקח את הערך האחרון שהוזן בעמודה 'שווי תיק'
        total_portfolio = float(df['שווי תיק'].dropna().iloc[-1])
    except:
        total_portfolio = 7038.0 # ערך ברירת מחדל מהתמונה שלך
        st.warning("המערכת משתמשת בערך ברירת מחדל. וודא שיש עמודה בשם 'שווי תיק' בשיטס.")

    user_input = st.text_input("הכנס קוד גישה:", type="password")
    
    if user_input:
        # --- מצב מנהל (רפאל) ---
        if user_input == ADMIN_CODE:
            st.success(f"🔓 שלום רפאל | שווי תיק בניהול: ${total_portfolio:,.2f}")
            if st.button("🔄 רענן נתונים"):
                st.rerun()
            
            summary = []
            for _, row in df.iterrows():
                try:
                    inv = float(row.iloc[2])
                    perc = float(str(row.iloc[3]).replace('%',''))
                    acts = int(row.iloc[4])
                    m = calculate_metrics(inv, total_portfolio * (perc/100), acts)
                    summary.append({
                        "שם": row.iloc[0], "הפקדה": f"${inv:,.0f}", 
                        "נטו": f"${m['net']:,.2f}", "רווח $": f"${m['profit_usd']:,.2f}", 
                        "תשואה": f"{m['profit_perc']:.2f}%"
                    })
                except: continue
            st.subheader("ריכוז לקוחות")
            st.table(pd.DataFrame(summary))
            
        # --- מצב לקוח ---
        else:
            code_col = df.columns[1]
            user_row = df[df[code_col].astype(str) == user_input]
            if not user_row.empty:
                data = user_row.iloc[0]
                st.header(f"שלום, {data.iloc[0]}")
                
                inv = float(data.iloc[2])
                perc = float(str(data.iloc[3]).replace('%',''))
                acts = int(data.iloc[4])
                m = calculate_metrics(inv, total_portfolio * (perc/100), acts)
                
                c1, c2, c3 = st.columns(3)
                c1.metric("יתרה נטו ($)", f"${m['net']:,.2f}")
                c2.metric("רווח נטו ($)", f"${m['profit_usd']:,.2f}")
                c3.metric("תשואה", f"{m['profit_perc']:.2f}%")
                
                st.divider()
                with st.expander("🔎 פירוט שקיפות מלא (מס ועמלות)"):
                    st.write(f"💰 שווי ברוטו בתיק: ${m['gross']:,.2f}")
                    st.write(f"📉 מס רווח הון (25%): ${m['tax']:,.2f}")
                    st.write(f"👤 עמלת הצלחה רפאל (20%): ${m['comm']:,.2f}")
                    st.write(f"⚙️ עמלות פעולה: ${m['fees']:,.2f}")
            else:
                st.error("קוד לא נמצא.")
