import streamlit as st
import pandas as pd

# הגדרות קבועות
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0
ADMIN_CODE = "0000" 

# קישור לגיליון CSV עם מנגנון רענון
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

def load_data():
    try:
        # הוספת timestamp לקישור כדי למנוע שמירת נתונים ישנים בזיכרון (Cache)
        url = f"{SHEET_URL}&cache_bust={pd.Timestamp.now().timestamp()}"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"שגיאה בטעינת הנתונים: {e}")
        return None

def calculate_all_metrics(initial_inv, current_gross, action_count):
    # חישוב עמלות פעולה
    total_action_fees = (action_count + 1) * ACTION_FEE_USD
    
    # רווח לפני מיסים ועמלות
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

st.set_page_config(page_title="Investment Tracker", page_icon="📈", layout="centered")
st.title("📈 מערכת ניהול השקעות")

df = load_data()

if df is not None:
    # שליפת שווי התיק מהשיטס (עמודה G)
    try:
        if 'שווי תיק' in df.columns:
            total_portfolio = float(df['שווי תיק'].dropna().iloc[0])
        else:
            total_portfolio = float(df.iloc[0, 6])
    except:
        total_portfolio = 100000.0
        st.warning("לא נמצא שווי תיק בשיטס, משתמש בברירת מחדל של $100,000")

    user_input = st.text_input("הכנס קוד גישה:", type="password")
    
    if user_input:
        # --- מצב מנהל (רפאל) ---
        if user_input == ADMIN_CODE:
            st.success(f"🔓 מצב מנהל | שווי תיק בשיטס: ${total_portfolio:,.0f}")
            
            if st.button("🔄 רענן נתונים עכשיו"):
                st.rerun()
                
            st.subheader("📊 סיכום כל התיקים")
            summary_list = []
            for _, row in df.iterrows():
                try:
                    inv = float(row.iloc[2])
                    perc = float(str(row.iloc[3]).replace('%', ''))
                    actions = int(row.iloc[4])
                    m = calculate_all_metrics(inv, total_portfolio * (perc / 100), actions)
                    
                    summary_list.append({
                        "שם": row.iloc[0],
                        "הפקדה": f"${inv:,.0f}",
                        "נטו": f"${m['net_balance']:,.2f}",
                        "רווח $": f"${m['net_profit_usd']:,.2f}",
                        "רווח %": f"{m['profit_percent']:.2f}%"
                    })
                except: continue
            st.table(pd.DataFrame(summary_list))

        # --- מצב לקוח ---
        else:
            code_col = df.columns[1]
            user_row = df[df[code_col].astype(str) == user_input]
            
            if not user_row.empty:
                user_data = user_row.iloc[0]
                st.header(f"שלום, {user_data.iloc[0]}")
                
                try:
                    inv = float(user_data.iloc[2])
                    perc = float(str(user_data.iloc[3]).replace('%', ''))
                    actions = int(user_data.iloc[4])
                    
                    # חישוב הנתונים
                    current_gross = total_portfolio * (perc / 100)
                    m = calculate_all_metrics(inv, current_gross, actions)
                    
                    # תצוגת קוביות (Metrics)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("יתרה נטו ($)", f"${m['net_balance']:,.2f}")
                    c2.metric("רווח בדולר", f"${m['net_profit_usd']:,.2f}")
                    c3.metric("תשואה", f"{m['profit_percent']:.2f}%")
                    
                    st.divider()
                    
                    # החזרת הפירוט המלא שביקשת
                    with st.expander("🔎 פירוט מלא (שקיפות, מיסים ועמלות)"):
                        st.write(f"💰 **שווי ברוטו יחסי בתיק:** ${m['gross_rel']:,.2f}")
                        st.write(f"📉 **מס רווח הון (25%):** ${m['tax']:,.2f}")
                        st.write(f"👤 **עמלת הצלחה רפאל (20%):** ${m['commission']:,.2f}")
                        st.write(f"⚙️ **עמלות פעולה מצטברות:** ${m['action_fees']:,.2f}")
                        st.caption("החישוב מתבצע לפי שווי התיק העדכני ב-Interactive Brokers בניכוי עמלות ומיסים.")
                
                except Exception as e:
                    st.error("שגיאה בחישוב הנתונים. וודא שהנתונים בשיטס הם מספרים בלבד.")
            else:
                st.error("קוד שגוי או לא נמצא.")
