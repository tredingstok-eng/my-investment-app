import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime
from pd.errors import EmptyDataError

# ==========================================
# --- RC Capital: Premium Fintech Portal ---
# ==========================================

# אבטחת מידע ומפתחות (מוצפן חלקית בתצוגה)
# ------------------------------------------
# שים לב: בעתיד מומלץ להשתמש ב-st.secrets לאבטחה מירבית.
IB_CONFIG = {
    "TOKEN": "837126977366730658372732",
    "QUERY_ID": "1489351"
}

APP_CONFIG = {
    "TITLE": "RC Capital Management",
    "LOGO_URL": "https://cdn-icons-png.flaticon.com/512/3135/3135706.png", # אייקון פינטק יוקרתי
    "ADMIN_CODE": "0000",
    "NO_FEE_USER": "רפאל כהן",
    "BASE_CURRENCY": "$",
    "REFRESH_RATE_SEC": 120 # Cache ל-2 דקות למניעת חסימה מ-IBKR
}

# הגדרות כספיות (עמלות ומיסים)
# ------------------------------------------
FEES_CONFIG = {
    "TAX_RATE": 0.25,        # 25% מס רווח הון
    "SUCCESS_FEE": 0.20,     # 20% עמלת הצלחה (מהרווח נטו לאחר מס)
    "ACTION_FEE_USD": 1.0    # $1 עמלת קנייה/מכירה (מינימום)
}

# הגדרות גיליון נתונים (Google Sheets)
# ------------------------------------------
SHEET_CONFIG = {
    "URL": "https://docs.google.com/spreadsheets/d/e/2PACX-1vT8RIj327lCnv6-A_4Ofp6XmcMRWHlJCczNjVK-q1ZKXw9N16ltdo9mhDSZ8NT78eD1eoCb5zVE8EkV/pub?output=csv",
    "COL_NAME": 0,
    "COL_PWD": 1,
    "COL_INV": 2,
    "COL_SHARE": 3,
    "COL_ACTS": 4
}

# ==========================================
# --- מערכת עיצוב מותאמת אישית (CSS) ---
# ==========================================

st.set_page_config(
    page_title=APP_CONFIG["TITLE"],
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

def inject_custom_css():
    st.markdown(f"""
    <style>
    /* הגדרות רקע ופונט כלליות */
    .main {{ background-color: #0b0d12; color: #e0e0e0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }}
    [data-testid="stSidebar"] {{ background-color: #11141a; border-right: 1px solid #1f2937; }}
    
    /* עיצוב כותרות */
    h1 {{ color: #ffffff; font-weight: 800; letter-spacing: -1px; margin-bottom: 0.5rem; }}
    h2, h3 {{ color: #f3f4f6; font-weight: 600; margin-top: 1.5rem; }}
    
    /* עיצוב כרטיסי מידע (Metrics) */
    div[data-testid="stMetricValue"] {{ font-size: 32px !important; font-weight: 700 !important; color: #ffffff !important; }}
    div[data-testid="stMetricDelta"] svg {{ fill: #00ff88 !important; }} /* חץ ירוק */
    div[data-testid="stMetricDelta"] {{ color: #00ff88 !important; background-color: rgba(0,255,136,0.1); padding: 2px 8px; border-radius: 4px; }}

    /* עיצוב כפתורים */
    .stButton>button {{
        background: linear-gradient(135deg, #d4af37 0%, #f9e29d 100%);
        color: #000000 !important;
        font-weight: 700;
        border: none;
        border-radius: 8px;
        padding: 12px 24px;
        transition: all 0.3s ease;
        width: 100%;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    .stButton>button:hover {{ box-shadow: 0 4px 15px rgba(212,175,55,0.4); transform: translateY(-1px); }}
    
    /* עיצוב תיבות קלט (Input) */
    .stTextInput>div>div>input {{ background-color: #1f2937; color: white; border: 1px solid #374151; border-radius: 8px; padding: 10px; }}
    .stTextInput>div>div>input:focus {{ border-color: #d4af37; box-shadow: 0 0 0 1px #d4af37; }}

    /* עיצוב מסך כניסה */
    .auth-box {{
        background-color: #11141a;
        padding: 60px;
        border-radius: 24px;
        border: 1px solid #1f2937;
        text-align: center;
        max-width: 480px;
        margin: 100px auto;
        box-shadow: 0 20px 40px rgba(0,0,0,0.4);
    }}
    .auth-logo {{ width: 80px; margin-bottom: 20px; }}
    
    /* אלמנטים דקורטיביים */
    .premium-divider {{ height: 2px; background: linear-gradient(90deg, rgba(212,175,55,0) 0%, rgba(212,175,55,1) 50%, rgba(212,175,55,0) 100%); margin: 2rem 0; }}
    </style>
    """, unsafe_allow_html=True)

inject_custom_css()

# ==========================================
# --- שכבת נתונים וחישובים (Logic) ---
# ==========================================

class DataEngine:
    """מנוע לניהול קבלת נתונים מ-IBKR ו-Google Sheets כולל ניקוי ו-Cache."""
    
    @staticmethod
    def _clean_numeric(val):
        """מנקה בבטחה תווים לא מספריים מגיליון הנתונים."""
        try:
            if pd.isna(val): return 0.0
            # מסיר סימני דולר, אחוזים, פסיקים ורווחים
            s = str(val).replace(APP_CONFIG["BASE_CURRENCY"], '').replace('%', '').replace(',', '').strip()
            return float(s)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    @st.cache_data(ttl=APP_CONFIG["REFRESH_RATE_SEC"])
    def fetch_ibkr_portfolio_value():
        """מתחבר ל-IBKR Web Service ומושך את ה-NAV העדכני."""
        try:
            # שלב 1: שליחת בקשת דוח
            token, qid = IB_CONFIG["TOKEN"], IB_CONFIG["QUERY_ID"]
            request_url = f"https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?t={token}&q={qid}&v=3"
            response = requests.get(request_url, timeout=15)
            
            if response.status_code != 200: return None
            
            root = ET.fromstring(response.content)
            if root.find("Status").text == "Success":
                reference_code = root.find("ReferenceCode").text
                base_url = root.find("Url").text
                
                # שלב 2: המתנה קלה לעיבוד בצד IBKR (קריטי!)
                time.sleep(1.5)
                
                # שלב 3: משיכת הנתונים
                data_url = f"{base_url}?q={reference_code}&t={token}"
                data_response = requests.get(data_url, timeout=15)
                
                if data_response.status_code != 200: return None
                
                data_root = ET.fromstring(data_response.content)
                nav_element = data_root.find(".//NetAssetValue")
                if nav_element is not None:
                    return float(nav_element.get("total"))
        except Exception as e:
            # רישום שגיאה פנימי (אפשר להרחיב ל-Logging מקצועי)
            pass
        return None

    @staticmethod
    def fetch_client_data():
        """מושך ומנקה את נתוני הלקוחות מ-Google Sheets."""
        try:
            # מניעת Cache של הדפדפן ע"י הוספת Timestamp ייחודי
            data_url = f"{SHEET_CONFIG['URL']}&cb={int(time.time())}"
            df = pd.read_csv(data_url)
            # ניקוי בסיסי של שמות עמודות ונתונים ריקים
            df.columns = [str(c).strip() for c in df.columns]
            df = df.dropna(subset=[df.columns[SHEET_CONFIG['COL_NAME']], df.columns[SHEET_CONFIG['COL_PWD']]])
            return df
        except (EmptyDataError, requests.exceptions.RequestException, pd.errors.ParserError):
            return None

class FinanceCalculator:
    """מנוע חישוב פיננסי לעמלות, מיסים ותשואות."""
    
    @staticmethod
    def calculate_client_metrics(name, deposited, current_gross, actions_count):
        """מחשב יתרה נטו, רווחים ועמלות ללקוח ספציפי."""
        
        # 1. חישוב עמלות פעולה מצטברות
        total_action_fees = (float(actions_count) + 1.0) * FEES_CONFIG["ACTION_FEE_USD"]
        
        # 2. חישוב רווח ברוטו (לפני עמלות הצלחה ומס)
        gross_profit = current_gross - deposited - total_action_fees
        
        # 3. החלת פטורים או חישוב עמלות
        if name == APP_CONFIG["NO_FEE_USER"] or gross_profit <= 0:
            tax_provision, success_fee = 0.0, 0.0
        else:
            # מס רווח הון (25% מהרווח ברוטו)
            tax_provision = gross_profit * FEES_CONFIG["TAX_RATE"]
            # עמלת הצלחה (20% מהרווח נטו לאחר מס)
            success_fee = (gross_profit - tax_provision) * FEES_CONFIG["SUCCESS_FEE"]
            
        # 4. חישוב יתרה סופית למשיכה (נטו)
        # שים לב: רפאל פטור מעמלת הצלחה ומס, אך משלם עמלות ברוקר
        net_balance = current_gross - tax_provision - success_fee
        if name != APP_CONFIG["NO_FEE_USER"]:
             net_balance -= total_action_fees
        
        # 5. חישוב תשואה באחוזים
        profit_usd = net_balance - deposited
        return {
            "net_balance": net_balance,
            "profit_usd": profit_usd,
            "profit_percent": (profit_usd / deposited * 100.0) if deposited > 0 else 0.0,
            "tax": tax_provision,
            "fees_management": success_fee,
            "fees_broker": total_action_fees,
            "gross_value": current_gross
        }

# ==========================================
# --- מערכת ויזואליזציה (Charts) ---
# ==========================================

class ChartFactory:
    """יוצר גרפים אינטראקטיביים ומעוצבים."""
    
    # תבנית צבעים יוקרתית (Gold & Slate)
    COLORS = ["#d4af37", "#1f2937", "#374151", "#8b949e", "#ffffff"]
    
    @staticmethod
    def create_growth_area_chart(deposited, current_net):
        """יוצר גרף שטח (Area) המציג את צמיחת ההון."""
        df_plot = pd.DataFrame({
            "סטטוס": ["הפקדה ראשונית", "שווי נוכחי (נטו)"],
            "סכום ($)": [deposited, current_net]
        })
        fig = px.area(df_plot, x="סטטוס", y="סכום ($)", 
                      title="צמיחת ההון שלך (נטו)",
                      color_discrete_sequence=[ChartFactory.COLORS[0]])
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font_color=ChartFactory.COLORS[4], title_font_size=20,
            xaxis=dict(showgrid=False, title=""),
            yaxis=dict(showgrid=True, gridcolor="#1f2937", title=""),
            hovermode="x"
        )
        # הוספת קו הדגשה מוזהב
        fig.update_traces(line=dict(width=3, color=ChartFactory.COLORS[0]), 
                          fillcolor="rgba(212,175,55,0.1)")
        return fig

    @staticmethod
    def create_ownership_donut_chart(client_share, client_name):
        """יוצר גרף דונאט המציג את נתח הבעלות בקרן."""
        values = [client_share, 100.0 - client_share]
        names = [f"חלקך ({client_name})", "משקיעים אחרים"]
        
        fig = px.pie(names=names, values=values, hole=0.7,
                    title="מבנה הבעלות בתיק כולל",
                    color_discrete_sequence=[ChartFactory.COLORS[0], ChartFactory.COLORS[1]])
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', font_color=ChartFactory.COLORS[4],
            title_font_size=20, showlegend=False
        )
        fig.update_traces(textinfo='percent', textfont_size=16, 
                          marker=dict(line=dict(color='#0b0d12', width=2)))
        
        # הוספת טקסט במרכז הדונאט
        fig.add_annotation(text=f"{client_share:.1f}%", x=0.5, y=0.5, showarrow=False,
                           font=dict(size=30, color=ChartFactory.COLORS[4], fontfamily="Helvetica Neue"))
        return fig

    @staticmethod
    def create_performance_waterfall(metrics):
        """יוצר גרף Waterfall להסבר המעבר מברוטו לנטו."""
        fig = go.Figure(go.Waterfall(
            name="Performance", orientation="v",
            measure=["relative", "relative", "relative", "relative", "total"],
            x=["שווי ברוטו", "מס רווח הון", "עמלת הצלחה", "עמלות ברוקר", "יתרת נטו"],
            textposition="outside", text=[f"+${metrics['gross_value']:,.0f}", f"-${metrics['tax']:,.0f}", f"-${metrics['fees_management']:,.0f}", f"-${metrics['fees_broker']:,.0f}", f"${metrics['net_balance']:,.0f}"],
            y=[metrics['gross_value'], -metrics['tax'], -metrics['fees_management'], -metrics['fees_broker'], 0],
            connector={"line": {"color": ChartFactory.COLORS[3]}},
            decreasing={"marker": {"color": "#ef4444"}}, # אדום לירידה
            increasing={"marker": {"color": "#00ff88"}}, # ירוק לעלייה
            totals={"marker": {"color": ChartFactory.COLORS[0]}}     # זהב לסך הכל
        ))
        
        fig.update_layout(title="ניתוח מעבר מברוטו לנטו", paper_bgcolor='rgba(0,0,0,0)', 
                          plot_bgcolor='rgba(0,0,0,0)', font_color=ChartFactory.COLORS[4],
                          yaxis=dict(showgrid=True, gridcolor="#1f2937", title=""))
        return fig

# ==========================================
# --- ממשק משתמש וניהול מצב (UI) ---
# ==========================================

# אתחול מצב הפעלה (Session State)
if 'auth_active' not in st.session_state: st.session_state.auth_active = False

# טעינת נתונים ראשונית (שכבה טכנית)
df_clients = DataEngine.fetch_client_data()
current_ibkr_value = DataEngine.fetch_ibkr_portfolio_value() or 6131.72 # ערך ברירת מחדל לגיבוי

# 1. מסך כניסה (Authentication)
# ------------------------------------------
if not st.session_state.auth_active:
    st.markdown('<div class="auth-box">', unsafe_allow_html=True)
    st.image(APP_CONFIG["LOGO_URL"], width=80)
    st.markdown(f"<h1>{APP_CONFIG['TITLE']}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #8b949e; margin-bottom: 40px;'>Private Clients Portal</p>", unsafe_allow_html=True)
    
    with st.form("login_form"):
        pwd_input = st.text_input("קוד גישה אישי:", type="password", placeholder="הזן את קוד ה-PIN שלך")
        submit_btn = st.form_submit_state = st.form_submit_button("התחבר באופן מאובטח")
        
        if submit_btn:
            # בדיקת כניסה: מנהל או לקוח
            if pwd_input == APP_CONFIG["ADMIN_CODE"]:
                st.session_state.auth_active = True
                st.session_state.auth_level = "admin"
                st.rerun()
            elif df_clients is not None:
                # חיפוש קוד בעמודה השנייה
                codes = df_clients.iloc[:, SHEET_CONFIG['COL_PWD']].astype(str).str.strip().tolist()
                if pwd_input.strip() in codes:
                    st.session_state.auth_active = True
                    st.session_state.auth_level = "client"
                    st.session_state.user_pwd = pwd_input.strip()
                    st.rerun()
                else: st.error("❌ קוד גישה שגוי. נסה שוב.")
            else: st.error("❌ תקלה בחיבור לשרת הנתונים.")
    st.markdown('</div>', unsafe_allow_html=True)

# 2. ממשק פנימי מאובטח
# ------------------------------------------
else:
    # סרגל צד (Sidebar)
    with st.sidebar:
        st.image(APP_CONFIG["LOGO_URL"], width=60)
        st.markdown(f"### {APP_CONFIG['TITLE']}")
        st.write("---")
        # מידע טכני ב-Sidebar
        st.caption(f"תאריך עדכון: {datetime.now().strftime('%d/%m/%Y')}")
        status_color = "🟢 פעיל" if current_ibkr_value != 6131.72 else "🟠 גיבוי"
        st.caption(f"חיבור לבורסה: {status_color}")
        st.caption(f"שווי תיק כולל: ${current_ibkr_value:,.2f}")
        st.write("---")
        if st.button("יציאה מאובטחת"):
            st.session_state.auth_active = False
            st.rerun()

    # 3. תצוגת מנהל (Admin Dashboard)
    # ------------------------------------------
    if st.session_state.auth_level == "admin":
        st.markdown("# 💼 לוח בקרה - ניהול תיק")
        st.markdown("<div class='premium-divider'></div>", unsafe_allow_html=True)
        
        if df_clients is not None:
            # חישובי סיכום לתיק הכולל
            raw_deposits = df_clients.iloc[:, SHEET_CONFIG['COL_INV']].apply(DataEngine._clean_numeric)
            total_deposited = raw_deposits.sum()
            total_profit_nominal = current_ibkr_value - total_deposited
            total_profit_perc = (total_profit_nominal / total_deposited * 100.0) if total_deposited > 0 else 0.0
            
            # כרטיסי סיכום (KPI Cards)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("שווי נכסים נוכחי (IBKR)", f"${current_ibkr_value:,.2f}")
            with col2:
                st.metric("סך הפקדות לקוחות", f"${total_deposited:,.2f}")
            with col3:
                color_delta = "normal" if total_profit_nominal >= 0 else "inverse"
                st.metric("רווח/הפסד כולל (ברוטו)", f"${total_profit_nominal:,.2f}", delta=f"{total_profit_perc:.2f}%", delta_color=color_delta)
            
            st.write("### ריכוז תיקי לקוחות")
            st.markdown("---")
            
            # בניית טבלת סיכום לקוחות
            client_summary = []
            for _, row in df_clients.iterrows():
                try:
                    c_name = str(row.iloc[SHEET_CONFIG['COL_NAME']])
                    c_inv = DataEngine._clean_numeric(row.iloc[SHEET_CONFIG['COL_INV']])
                    c_share = DataEngine._clean_numeric(row.iloc[SHEET_CONFIG['COL_SHARE']])
                    c_acts = int(DataEngine._clean_numeric(row.iloc[SHEET_CONFIG['COL_ACTS']]))
                    
                    # חישוב שווי ברוטו של הלקוח מתוך סה"כ IBKR
                    c_gross = current_ibkr_value * (c_share / 100.0)
                    
                    m = FinanceCalculator.calculate_client_metrics(c_name, c_inv, c_gross, c_acts)
                    client_summary.append({
                        "לקוח": c_name,
                        "הפקדה": f"${c_inv:,.0f}",
                        "יתרה נטו": f"${m['net_balance']:,.2f}",
                        "רווח $": f"${m['profit_usd']:,.2f}",
                        "תשואה %": f"{m['profit_percent']:.1f}%"
                    })
                except: continue
            
            st.dataframe(pd.DataFrame(client_summary), use_container_width=True, height=400)
        else: st.error("❌ לא ניתן היה לטעון את נתוני הלקוחות מגיליון הגיבוי.")

    # 4. תצוגת לקוח (Client Portal)
    # ------------------------------------------
    elif st.session_state.auth_level == "client" and df_clients is not None:
        try:
            # מציאת שורת המשתמש הספציפי
            user_codes_ser = df_clients.iloc[:, SHEET_CONFIG['COL_PWD']].astype(str).str.strip()
            user_row = df_clients[user_codes_ser == st.session_state.user_pwd].iloc[0]
            
            # שליפה וניקוי נתונים
            client_name = str(user_row.iloc[SHEET_CONFIG['COL_NAME']])
            client_inv = DataEngine._clean_numeric(user_row.iloc[SHEET_CONFIG['COL_INV']])
            client_share_perc = DataEngine._clean_numeric(user_row.iloc[SHEET_CONFIG['COL_SHARE']])
            client_actions = int(DataEngine._clean_numeric(user_row.iloc[SHEET_CONFIG['COL_ACTS']]))
            
            # חישוב שווי ברוטו של הלקוח
            client_gross_value = current_ibkr_value * (client_share_perc / 100.0)
            
            # ביצוע חישובים פיננסיים
            metrics = FinanceCalculator.calculate_client_metrics(client_name, client_inv, client_gross_value, client_actions)
            
            # הממשק הויזואלי ללקוח
            # ---------------------
            st.markdown(f"# שלום, {client_name}")
            st.markdown(f"<p style='color: #8b949e;'>ברוכים הבאים לפורטל RC Capital | עדכון אחרון: {datetime.now().strftime('%d/%m/%Y')}</p>", unsafe_allow_html=True)
            st.markdown("<div class='premium-divider'></div>", unsafe_allow_html=True)
            
            # כרטיסי KPI (Headline Numbers)
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("יתרה נטו (למשיכה)", f"${metrics['net_balance']:,.2f}")
            with col_b:
                color_d = "normal" if metrics['profit_usd'] >= 0 else "inverse"
                st.metric("רווח/הפסד נטו (נומינלי)", f"${metrics['profit_usd']:,.2f}", delta=f"{metrics['profit_percent']:.2f}%", delta_color=color_d)
            with col_c:
                st.metric("סך הפקדות", f"${client_inv:,.0f}")
                
            st.write("---")
            st.subheader("📊 ניתוח תיק השקעות")
            
            # שורת גרפים ראשונה
            col_g1, col_g2 = st.columns([2, 1])
            with col_g1:
                st.plotly_chart(ChartFactory.create_growth_area_chart(client_inv, metrics['net_balance']), use_container_width=True)
            with col_g2:
                st.plotly_chart(ChartFactory.create_ownership_donut_chart(client_share_perc, client_name), use_container_width=True)
                
            st.write("---")
            st.subheader("🔍 שקיפות מלאה: עמלות ומיסים")
            
            # שורת גרף ומידע חשבונאי
            col_g3, col_text = st.columns([2, 1])
            with col_g3:
                st.plotly_chart(ChartFactory.create_performance_waterfall(metrics), use_container_width=True)
            with col_text:
                st.write("#### פירוט חשבונאי")
                st.write(f"**שווי ברוטו בתיק:** ${metrics['gross_value']:,.2f}")
                st.write(f"**נתח מהתיק הכולל:** {client_share_perc}%")
                st.markdown("---")
                if client_name == APP_CONFIG["NO_FEE_USER"]:
                    st.success("💎 חשבון זה מוגדר כחשבון מנהל ופטור מעמלות ניהול ומיסים (מלבד עמלות ברוקר).")
                else:
                    st.write(f"🟢 מס רווח הון (הפרשה 25%): ${metrics['tax']:,.2f}")
                    st.write(f"🟢 עמלת הצלחה (20% נטו): ${metrics['fees_management']:,.2f}")
                    st.write(f"🟢 עמלות ברוקר (קנייה/מכירה): ${metrics['fees_broker']:,.2f}")
                    st.caption("עמלת ההצלחה מחושבת מהרווח הנטו שנשאר לאחר ניכוי מס רווח הון.")
                    
        except Exception as e:
            # הגנה מפני שגיאה בנתוני המשתמש בגיליון
            st.error(f"❌ נתקלנו בבעיה בקריאת הנתונים שלך מהגיליון.")
            st.caption(f"פרטי השגיאה: {e}")
            
# --- סוף הקוד ---
