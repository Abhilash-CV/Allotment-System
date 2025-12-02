import streamlit as st
from dnm import dnm_allotment
from pga_stray import pga_allotment

# ==========================================
#            PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Admission System", layout="wide", page_icon="🎓")

# ==========================================
#            CLEAN MINIMAL LOGIN CSS
# ==========================================
CLEAN_CSS = """
<style>

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    body {
        background: #f6f7fb !important;
    }

    /* Center the login container */
    .center-login {
        display: flex;
        justify-content: center;
        margin-top: 120px;
    }

    /* Login Card */
    .login-card {
        width: 380px;
        background: #ffffff;
        padding: 35px 32px;
        border-radius: 15px;
        box-shadow: 0px 8px 20px rgba(0,0,0,0.08);
        text-align: left;
    }

    .login-title {
        font-size: 30px !important;
        font-weight: 800 !important;
        color: #1e293b;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .login-input {
        margin-bottom: 14px;
    }

    .login-btn button {
        width: 100%;
        padding: 10px;
        border-radius: 8px !important;
        font-size: 16px !important;
    }

    /* Header for main app */
    .app-header {
        background: #1e40af;
        padding: 16px;
        border-radius: 10px;
        margin-bottom: 18px;
    }
    .app-header h1 {
        color: white;
        font-size: 24px;
        margin: 0;
        font-weight: 600;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #f1f5f9;
        border-right: 1px solid #d4d4d8;
    }

    .menu-item {
        padding: 10px 12px;
        margin: 6px 0;
        border-radius: 8px;
        background: white;
        border: 1px solid #e2e8f0;
        font-size: 16px;
        font-weight: 600;
    }

    .menu-item:hover {
        background: #1e3a8a;
        color: white;
    }

    .menu-selected {
        background: #1e293b !important;
        color: white !important;
    }

</style>
"""
st.markdown(CLEAN_CSS, unsafe_allow_html=True)


# ==========================================
#            LOGIN SYSTEM
# ==========================================
VALID_USERS = {
    "admin": "admin123",
    "user": "user123"
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "menu_choice" not in st.session_state:
    st.session_state.menu_choice = "DNM"


# ==========================================
#            LOGIN PAGE
# ==========================================
def login_page():

    st.markdown("<div class='center-login'>", unsafe_allow_html=True)
    st.markdown("<div class='login-card'>", unsafe_allow_html=True)

    st.markdown("""
        <div class='login-title'>
            🔐 Login
        </div>
    """, unsafe_allow_html=True)

    # Inputs
    username = st.text_input("Username", key="login_user")
    password = st.text_input("Password", type="password", key="login_pass")

    # Login Button
    st.markdown("<div class='login-btn'>", unsafe_allow_html=True)
    if st.button("Login"):
        if username in VALID_USERS and VALID_USERS[username] == password:
            st.session_state.logged_in = True
            st.experimental_rerun()
        else:
            st.error("❌ Invalid username or password")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div></div>", unsafe_allow_html=True)


# ==========================================
#            FUTURE MODULE
# ==========================================
def future_program():
    st.markdown("<div class='app-header'><h1>🛠 Future Tools</h1></div>", unsafe_allow_html=True)
    st.info("Upcoming modules will appear here.")


# ==========================================
#            MAIN APPLICATION
# ==========================================
def main_app():

    st.markdown("<div class='app-header'><h1>🎓 Admission Management System</h1></div>", unsafe_allow_html=True)

    st.sidebar.title("Navigation")

    menu_options = {
        "PGA": "📘 PGA Allotment",
        "DNM": "🧮 DNM Allotment",
        "Future": "🛠 Future Tools"
    }

    for key, label in menu_options.items():

        css_class = "menu-item"
        if st.session_state.menu_choice == key:
            css_class += " menu-selected"

        if st.sidebar.button(label, key=f"menu_{key}", use_container_width=True):
            st.session_state.menu_choice = key
            st.experimental_rerun()

    if st.sidebar.button("🚪 Logout", key="logout", use_container_width=True):
        st.session_state.logged_in = False
        st.experimental_rerun()

    # Routing
    selected = st.session_state.menu_choice

    if selected == "PGA":
        pga_allotment()
    elif selected == "DNM":
        dnm_allotment()
    else:
        future_program()


# ==========================================
#            APP FLOW
# ==========================================
if st.session_state.logged_in:
    main_app()
else:
    login_page()
