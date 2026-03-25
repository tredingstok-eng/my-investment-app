import streamlit as st
import pandas as pd

# הגדרות
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0

# הקישור לגיליון (CSV)
# הערה: הקוד מושך את הגיליון כולו ומפריד בין הלשוניות
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
    # --- חלק א: משיכת שווי תיק מעודכן ---
    # נסה למשוך את הערך מתא ספציפי או הגדר ברירת מחדל
    # אם שמת את השווי בגיליון נפרד, הכי בטוח להוסיף שדה "שווי תיק" בתוך הטבלה של המשתמש או להזין כאן:
    with st.sidebar:
        st.write("ניהול מערכת")
        # אופציה א: להזין ידנית באפליקציה בכל פעם שאתה פותח אותה (הכי פשוט)
        total_portfolio = st.number_input("עדכן שווי תיק כולל ב-IBKR ($)", value=100000.0, step=100.0)
        st.info("שווי התיק משפיע על חישובי כל המשתמשים בזמן אמת.")

    user_code = st.text_input("הכנס קוד אישי (4 ספרות):", type="password")
    
    if user_code:
        code_col = df.columns[1] 
        user_row = df[df[code_col].astype(str) == user_code]
        
        if not user_row.empty:
            user_data = user_row.iloc[0]
            name = user_data.iloc[0]
            st.subheader(f"שלום, {name}")
            
            try:
                inv = float(user_data.iloc[2])
                perc = float(str(user_data.iloc[3]).replace('%', ''))
                actions = int(user_data.iloc[4])
                
                # החישוב מתבסס על ה-total_portfolio שהזנת בצד
                current_gross = total_portfolio * (perc / 100)
                net, tax, comm, act_fees = calculate_fees(inv, current_gross, actions)
                
                st.metric("יתרה נטו למשיכה ($)", f"${net:,.2f}")
                
                with st.expander("ראה פירוט מלא"):
                    st.write(f"💰 שווי ברוטו בתיק: ${current_gross:,.2f}")
                    st.write(f"📉 מס רווח הון (25%): ${tax:,.2f}")
                    st.write(f"👤 עמלת הצלחה (20%): ${comm:,.2f}")
                    st.write(f"⚙️ עמלות פעולה: ${act_fees:,.2f}")
            except Exception as e:
                st.error("שגיאה בנתוני הגיליון. וודא שהכל מספרים.")
        else:
            st.error("הקוד לא נמצא.")
