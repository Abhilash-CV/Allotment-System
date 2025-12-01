import streamlit as st
from dnm import dnm_allotment

# ==========================================
#            PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Admission System", layout="wide", page_icon="🎓")


# ==========================================
#            CUSTOM UI THEME
# ==========================================
CUSTOM_CSS = """
<style>

    /* Remove Streamlit default menu/footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Smooth animation */
    * { transition: all 0.25s ease-in-out; }

    /* APP HEADER */
    .app-header {
        background: linear-gradient(90deg, #0052A2, #0088F0);
        padding: 18px;
        border-radius: 10px;
        margin-bottom: 15px;
    }
    .app-header h1 {
        color: white;
        font-size: 30px;
        font-weight: bold;
        text-align: center;
    }

    /* SIDEBAR */
    [data-testid="stSidebar"] {
        background: #f3f7fb;
        border-right: 1px solid #d6d6d6;
    }

    .menu-item {
        padding: 14px 16px;
        margin: 8px 0;
        border-radius: 10px;
        font-weight: 600;
        font-size: 17px;
        display: block;
        color: #333333;
        background: #ffffff;
        border: 1px solid #e4e4e4;
        cursor: pointer;
    }

    .menu-item:hover {
        background: #0052A2;
        color: white;
        border-color: #0052A2;
    }

    .menu-selected {
        background: #004080 !important;
        color: white !important;
        border-color: #004080 !important;
    }

    /* LOGOUT BUTTON */
    .logout-btn {
        margin-top: 35px;
        padding: 12px;
        background: #ff4b4b;
        color: white;
        font-size: 16px;
        font-weight: 600;
        border-radius: 10px;
        text-align: center;
        cursor: pointer;
    }
    .logout-btn:hover {
        background: #cc0000;
    }

    /* LOGIN BOX */
    .login-box {
        max-width: 420px;
        margin: auto;
        margin-top: 140px;
        padding: 40px;
        background: white;
        border-radius: 15px;
        box-shadow: 0px 4px 18px rgba(0,0,0,0.1);
        border: 1px solid #ddd;
    }
    .login-title {
        text-align: center;
        font-size: 28px;
        font-weight: bold;
        color: #0052A2;
        margin-bottom: 25px;
    }

</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


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


# -------------- LOGIN PAGE ---------------
def login_page():
    st.markdown("<div class='login-box'>", unsafe_allow_html=True)
    st.markdown("<div class='login-title'>🔐 Login</div>", unsafe_allow_html=True)

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login", use_container_width=True):
        if username in VALID_USERS and VALID_USERS[username] == password:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("❌ Invalid username or password")

    st.markdown("</div>", unsafe_allow_html=True)


# ==========================================
#            PROGRAM MODULES
# ==========================================
def pga_module():
    st.markdown("<div class='app-header'><h1>📘 PGA Program</h1></div>", unsafe_allow_html=True)
    st.info("PGA program features will be added here.")


def future_program():
    st.markdown("<div class='app-header'><h1>🛠 Future Tools</h1></div>", unsafe_allow_html=True)
    st.info("Upcoming modules will appear here.")


# ==========================================
#            MAIN APPLICATION
# ==========================================
def main_app():

    # ----- HEADER -----
    st.markdown("<div class='app-header'><h1>🎓 Admission Management System</h1></div>", unsafe_allow_html=True)

    # ----- SIDEBAR MENU -----
    st.sidebar.title("Navigation")

    menu_options = {
        "PGA": "📘 PGA",
        "DNM": "🧮 DNM Allotment",
        "Future": "🛠 Future Tools"
    }

    for key, label in menu_options.items():

        css_class = "menu-item"
        if st.session_state.menu_choice == key:
            css_class += " menu-selected"

        if st.sidebar.button(label, key=f"menu_{key}", use_container_width=True):
            st.session_state.menu_choice = key
            st.rerun()

        st.sidebar.markdown(
            f"<script>"
            f"var el = window.parent.document.querySelector('button[data-testid=\"menu_{key}\"]');"
            f"if (el) el.className = '{css_class}';"
            f"</script>",
            unsafe_allow_html=True
        )

    # ----- LOGOUT BUTTON -----
    if st.sidebar.button("🚪 Logout", key="logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

    # ----- PAGE ROUTING -----
    selected = st.session_state.menu_choice

    if selected == "PGA":
        pga_module()

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
