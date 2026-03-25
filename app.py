import streamlit as st
import pandas as pd

# הגדרות קבועות
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0
ADMIN_NAME = "רפאל"
ADMIN_CODE = "0000"  # <--- רפאל, שנה כאן לסיסמה הסודית שלך

# הקישור לגיליון (CSV)
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

def load_data():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"שגיאה בטעינת הנתונים: {e}")
        return None

def calculate_all_metrics(initial_inv, current_gross, action_count):
    # עמלות פעולה
    total_action_fees = (action_count + 1) * ACTION_FEE_USD
    
    # רווח גולמי לפני הכל
    gross_profit = current_gross - initial_inv - total_action_fees
    
    if gross_profit > 0:
        tax = gross_profit * TAX_RATE
        commission = (gross_profit - tax) * SUCCESS_FEE
        net_balance = current_gross - tax - commission
    else:
        tax, commission = 0, 0
        net_balance = current_gross - total_action_fees
    
    # רווח נטו בדולרים (מה נשאר ביד פחות ההשקעה המקורית)
    net_profit_usd = net_balance - initial_inv
    # רווח באחוזים
    profit_percent = (net_profit_usd / initial_inv) * 100
    
    return net_balance, net_profit_usd, profit_percent, tax, commission, total_action_fees

st.set_page_config(page_title="Investment Tracker", page_icon="📈")
st.title("📈 מערכת ניהול השקעות")

# אתחול שווי תיק בזיכרון
if 'total_portfolio' not in st.session_state:
    st.session_state['total_portfolio'] = 100000.0

df = load_data()

if df is not None:
    user_code = st.text_input("הכנס קוד גישה:", type="password")
    
    if user_code:
        # בדיקה אם זה רפאל (מנהל)
        if user_code == ADMIN_CODE:
            st.success(f"שלום {ADMIN_NAME}, ברוך הבא למסך הניהול")
            st.session_state['total_portfolio'] = st.number_input(
                "עדכן שווי תיק כולל ב-IBKR ($):", 
                value=st.session_state['total_portfolio']
            )
            
            st.divider()
            st.subheader("דוח ריכוז לקוחות")
            
            summary_list = []
            for _, row in df.iterrows():
                try:
                    inv = float(row.iloc[2])
                    perc = float(str(row.iloc[3]).replace('%', ''))
                    actions = int(row.iloc[4])
                    current_gross = st.session_state['total_portfolio'] * (perc / 100)
                    net, net_p_usd, p_perc, _, _, _ = calculate_all_metrics(inv, current_gross, actions)
                    
                    summary_list.append({
                        "שם": row.iloc[0],
                        "הפקדה": f"${inv:,.0f}",
                        "שווי נטו": f"${net:,.2f}",
                        "רווח ($)": f"${net_p_usd:,.2f}",
                        "רווח (%)": f"{p_perc:.2f}%"
                    })
                except: continue
            st.table(pd.DataFrame(summary_list))
            
        else:
            # כניסת משתמש רגיל
            code_col = df.columns[1]
            user_row = df[df[code_col].astype(str) == user_code]
            
            if not user_row.empty:
                user_data = user_row.iloc[0]
                st.subheader(f"שלום, {user_data.iloc[0]}")
                
                try:
                    inv = float(user_data.iloc[2])
                    perc = float(str(user_data.iloc[3]).replace('%', ''))
                    actions = int(user_data.iloc[4])
                    
                    current_gross = st.session_state['total_portfolio'] * (perc / 100)
                    net, net_p_usd, p_perc, tax, comm, act_fees = calculate_all_metrics(inv, current_gross, actions)
                    
                    # הצגת הנתונים בקוביות (Metrics)
                    col1, col2, col3 = st.columns(3)
                    col1.metric("יתרה נטו ($)", f"${net:,.2f}")
                    col2.metric("רווח נטו ($)", f"${net_p_usd:,.2f}")
                    col3.metric("תשואה", f"{p_perc:.2f}%")
                    
                    st.divider()
                    with st.expander("ראה פירוט שקיפות מלא (מס ועמלות)"):
                        st.write(f"💰 שווי ברוטו יחסי בתיק: ${current_gross:,.2f}")
                        st.write(f"📉 מס רווח הון (25% מהרווח): ${tax:,.2f}")
                        st.write(f"👤 עמלת הצלחה רפאל (20%): ${comm:,.2f}")
                        st.write(f"⚙️ סך עמלות פעולה ($1): ${act_fees:,.2f}")
                        st.info("הרווח המוצג למעלה הוא לאחר ניכוי כל העמלות והמיסים.")
                except:
                    st.error("יש בעיה בנתונים בגיליון. פנה לרפאל.")
            else:
                st.error("קוד שגוי.")
