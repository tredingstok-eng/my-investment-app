import streamlit as st
import pandas as pd

# הגדרות קבועות
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0
ADMIN_CODE = "0000"  # הקוד הסודי שלך למצב אדמין

# הקישור לגיליון ה-CSV שלך
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
        tax, commission = 0, 0
        net_balance = current_gross - total_action_fees
    
    net_profit_usd = net_balance - initial_inv
    profit_percent = (net_profit_usd / initial_inv) * 100 if initial_inv != 0 else 0
    
    return {
        "net_balance": net_balance,
        "net_profit_usd": net_profit_usd,
        "profit_percent": profit_percent,
        "tax": tax,
        "commission": commission,
        "action_fees": total_action_fees,
        "gross_rel": current_gross
    }

st.set_page_config(page_title="Investment Tracker", page_icon="📈", layout="wide")
st.title("📈 מערכת ניהול השקעות")

# שמירת שווי התיק בזיכרון של האפליקציה
if 'total_portfolio' not in st.session_state:
    st.session_state['total_portfolio'] = 100000.0

df = load_data()

if df is not None:
    # שדה הזנת קוד אחיד לכולם
    user_input = st.text_input("הכנס קוד גישה:", type="password")
    
    if user_input:
        # בדיקה אם זה רפאל (מצב אדמין)
        if user_input == ADMIN_CODE:
            st.success("🔓 מחובר כנהל (Admin Mode)")
            
            # אזור עדכון שווי תיק
            new_val = st.number_input("עדכן שווי תיק כולל ב-IBKR ($):", value=st.session_state['total_portfolio'])
            st.session_state['total_portfolio'] = new_val
            
            st.divider()
            st.subheader("📊 ריכוז נתוני כל התיקים")
            
            summary_data = []
            for _, row in df.iterrows():
                try:
                    inv = float(row.iloc[2])
                    perc = float(str(row.iloc[3]).replace('%', ''))
                    actions = int(row.iloc[4])
                    current_gross = st.session_state['total_portfolio'] * (perc / 100)
                    
                    m = calculate_metrics(inv, current_gross, actions)
                    
                    summary_data.append({
                        "שם לקוח": row.iloc[0],
                        "הפקדה": f"${inv:,.0f}",
                        "שווי נטו": f"${m['net_balance']:,.2f}",
                        "רווח ($)": f"${m['net_profit_usd']:,.2f}",
                        "רווח (%)": f"{m['profit_percent']:.2f}%"
                    })
                except: continue
            
            st.table(pd.DataFrame(summary_data))

        else:
            # כניסת משתמש רגיל (חיפוש בטבלה לפי עמודה שנייה)
            code_col = df.columns[1]
            user_row = df[df[code_col].astype(str) == user_input]
            
            if not user_row.empty:
                user_data = user_row.iloc[0]
                st.header(f"שלום, {user_data.iloc[0]}")
                
                try:
                    inv = float(user_data.iloc[2])
                    perc = float(str(user_data.iloc[3]).replace('%', ''))
                    actions = int(user_data.iloc[4])
                    
                    current_gross = st.session_state['total_portfolio'] * (perc / 100)
                    m = calculate_metrics(inv, current_gross, actions)
                    
                    # תצוגה למשתמש
                    c1, c2, c3 = st.columns(3)
                    c1.metric("יתרה נטו ($)", f"${m['net_balance']:,.2f}")
                    c2.metric("רווח בדולר", f"${m['net_profit_usd']:,.2f}")
                    c3.metric("תשואה באחוזים", f"{m['profit_percent']:.2f}%")
                    
                    st.divider()
                    with st.expander("🔎 שקיפות מלאה (עמלות ומיסוי)"):
                        st.write(f"💰 שווי ברוטו יחסי בתיק: ${m['gross_rel']:,.2f}")
                        st.write(f"📉 מס רווח הון (25% מהרווח): ${m['tax']:,.2f}")
                        st.write(f"👤 עמלת הצלחה רפאל (20%): ${m['commission']:,.2f}")
                        st.write(f"⚙️ סך עמלות פעולה ($1): ${m['action_fees']:,.2f}")
                except:
                    st.error("שגיאה בנתונים בגיליון. פנה לרפאל.")
            else:
                st.error("קוד שגוי או לא נמצא במערכת.")
