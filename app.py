import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import xml.etree.ElementTree as ET
import time

# --- הגדרות ליבה ---
IB_TOKEN = "837126977366730658372732"
IB_QUERY_ID = "1489351"
TAX_RATE = 0.25
SUCCESS_FEE = 0.20
ACTION_FEE_USD = 1.0
ADMIN_CODE = "0000"  # הקוד הסודי שלך
NO_FEE_USER = "רפאל כהן"
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv"

# עיצוב דף
st.set_page_config(page_title="Cohen Investments", page_icon="💎", layout="wide")

# --- פונקציות עזר ---
@st.cache_data(ttl=180) # שומר נתונים בזיכרון ל-3 דקות כדי לא להעמיס על IBKR
def get_ibkr_value():
    try:
        url = f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={IB_TOKEN}&q={IB_QUERY_ID}&v=3"
        res = requests.get(url, timeout=10)
        root = ET.fromstring(res.content)
        if root.find("Status").text == "Success":
            code = root.find("ReferenceCode").text
            base_url = root.find("Url").text
            time.sleep(1)
            data_res = requests.get(f"{base_url}?q={code}&t={IB_TOKEN}", timeout=10)
            data_root = ET.fromstring(data_res.content)
            nav = data_root.find(".//NetAssetValue")
            if nav is not None:
                return float(nav.get("total"))
    except:
        return None
    return None

def load_data():
    try:
        df = pd.read_csv(f"{SHEET_URL}&cb={time.time()}")
        df.columns = df.columns.str.strip()
        return df
    except:
        return None

def calc_metrics(name, inv, current_gross, acts):
    fees = (acts + 1) * ACTION_FEE_USD
    profit_before = current_gross - inv - fees
    if name == NO_FEE_USER or profit_before <= 0:
        tax, comm = 0, 0
    else:
        tax = profit_before * TAX_RATE
        comm = (profit_before - tax) * SUCCESS_FEE
    net = current_gross - tax - comm - (fees if name != NO_FEE_USER else 1.0)
    return {
        "net": net, "profit": net - inv, 
        "perc": ((net - inv) / inv * 100) if inv > 0 else 0,
        "tax": tax, "comm": comm, "fees": fees, "gross": current_gross
    }

# --- ממשק משתמש ---
st.title("💎 Cohen Investment Fund")
st.markdown(f"**תאריך עדכון:** {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}")

df = load_data()
ib_val = get_ibkr_value()

# סרגל צד
with st.sidebar:
    st.header("כניסה למערכת")
    user_code = st.text_input("קוד אישי:", type="password")
    if ib_val:
        st.success(f"מחובר לבורסה: ${ib_val:,.2f}")
    else:
        st.error("מתחבר לגיבוי נתונים...")
        ib_val = 6131.0 # ברירת מחדל אם הכל נכשל

if not user_code:
    st.info("אנא הכנס קוד כדי לצפות בנתונים")
else:
    # --- מצב מנהל (רפאל) ---
    if user_code == ADMIN_CODE:
        st.subheader("📊 ניהול תיק השקעות כולל")
        total_inv = df.iloc[:, 2].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("שווי תיק כולל (IBKR)", f"${ib_val:,.2f}")
        c2.metric("סך הפקדות לקוחות", f"${total_inv:,.2f}")
        c3.metric("רווח/הפסד נומינלי", f"${ib_val - total_inv:,.2f}", delta=f"{((ib_val-total_inv)/total_inv*100):.2f}%")
        
        st.divider()
        st.write("### ריכוז לקוחות")
        summary_list = []
        for _, row in df.iterrows():
            m = calc_metrics(row[0], float(row[2]), ib_val * (float(str(row[3]).replace('%',''))/100), int(row[4]))
            summary_list.append({"לקוח": row[0], "הפקדה": row[2], "נטו": m['net'], "רווח $": m['profit']})
        st.table(pd.DataFrame(summary_list))

    # --- מצב לקוח ---
    else:
        user_row = df[df.iloc[:, 1].astype(str) == user_code]
        if user_row.empty:
            st.error("קוד שגוי או משתמש לא קיים")
        else:
            data = user_row.iloc[0]
            name, inv, share_perc, acts = data[0], float(data[2]), float(str(data[3]).replace('%','')), int(data[4])
            m = calc_metrics(name, inv, ib_val * (share_perc/100), acts)
            
            st.header(f"שלום, {name}")
            
            # כרטיסי מידע
            cols = st.columns(4)
            cols[0].metric("יתרה נטו (למשיכה)", f"${m['net']:,.2f}")
            cols[1].metric("רווח נקי", f"${m['profit']:,.2f}", delta=f"{m['perc']:.2f}%")
            cols[2].metric("סך הפקדות", f"${inv:,.0f}")
            cols[3].metric("נתח בקרן", f"{share_perc}%")
            
            st.divider()
            
            # גרפים
            g1, g2 = st.columns(2)
            with g1:
                fig = px.bar(x=["הפקדה", "שווי נוכחי (נטו)"], y=[inv, m['net']], 
                           color=["הפקדה", "נטו"], title="הצמיחה שלך",
                           color_discrete_sequence=["#636EFA", "#00CC96"])
                st.plotly_chart(fig, use_container_width=True)
            with g2:
                fig2 = px.pie(values=[share_perc, 100-share_perc], names=[f"חלקך", "שאר הקרן"], 
                            hole=0.5, title="פיזור התיק", color_discrete_sequence=["#EF553B", "#AB63FA"])
                st.plotly_chart(fig2, use_container_width=True)
            
            # פירוט טכני
            with st.expander("📝 פירוט חשבונאי"):
                st.write(f"שווי ברוטו בתיק: ${m['gross']:,.2f}")
                if name == NO_FEE_USER:
                    st.success("חשבון זה מוגדר כחשבון מנהל (פטור מעמלות)")
                else:
                    st.write(f"הפרשה למס (25% מהרווח): ${m['tax']:,.2f}")
                    st.write(f"עמלת הצלחה (20% מהרווח): ${m['comm']:,.2f}")
                st.write(f"עמלות קנייה/מכירה מצטברות: ${m['fees']:,.2f}")
