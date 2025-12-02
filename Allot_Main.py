import streamlit as st
from dnm import dnm_allotment
from pga_stray import pga_allotment


# ==========================================
#            PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Admission System", layout="wide", page_icon="🎓")


# ==========================================
#            MODERN LOGIN + UI THEME CSS
# ==========================================
CUSTOM_CSS = """
<style>

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Background gradient for login page */
    .main {
        background: linear-gradient(135deg, #0052A2 0%, #00A4E4 100%);
        min-height: 100vh;
    }

    /* Centered wrapper */
    .center-wrapper {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 90vh;
    }

    /* LOGIN CARD */
    .login-card {
        width: 420px;
        padding: 40px 35px;
        border-radius: 20px;
        background: white;
        box-shadow: 0px 8px 25px rgba(0,0,0,0.18);
        text-align: center;
        animation: fadeIn 0.7s ease-in-out;
    }

    .login-icon {
        font-size: 55px;
        margin-bottom: 10px;
        color: #0052A2;
    }

    .login-card h2 {
        font-size: 30px;
        font-weight: 800;
        color: #0052A2;
        margin-bottom: 5px;
    }

    .login-card p {
        color: #666;
        margin-bottom: 20px;
    }

    /* Login button */
    .login-btn button {
        width: 100%;
        padding: 12px;
        border-radius: 12px !important;
        font-size: 17px;
        font-weight: bold;
        background: linear-gradient(90deg, #0052A2, #0088F0);
        color: white !important;
        border: none;
    }

    .login-btn button:hover {
        background: linear-gradient(90deg, #003F7F, #0070C8);
    }

    /* Fade animation */
    @keyframes fadeIn {
        from {opacity: 0; transform: translateY(20px);}
        to {opacity: 1; transform: translateY(0);}
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


# ==========================================
#            LOGIN PAGE
# ==========================================
def login_page():

    st.markdown("<div class='center-wrapper'>", unsafe_allow_html=True)

    # Card UI
    st.markdown("""
        <div class='login-card'>
            <div class='login-icon'>🔐</div>
            <h2>Login</h2>
            <p>Welcome to Admission Management System</p>
        </div>
    """, unsafe_allow_html=True)

    # Inputs OUTSIDE the HTML so Streamlit can render inputs normally
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    # Login Button
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
def future_program():
    st.markdown("<div class='app-header'><h1>🛠 Future Tools</h1></div>", unsafe_allow_html=True)
    st.info("Upcoming modules will appear here.")


# ==========================================
#            MAIN APPLICATION
# ==========================================
def main_app():

    # HEADER
    st.markdown("<div class='app-header'><h1>🎓 Admission Management System</h1></div>", unsafe_allow_html=True)

    # SIDEBAR
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
            st.rerun()

        st.sidebar.markdown(
            f"""
            <script>
            let el = window.parent.document.querySelector('button[data-testid="menu_{key}"]');
            if (el) el.className = '{css_class}';
            </script>
            """,
            unsafe_allow_html=True
        )

    # LOGOUT BUTTON
    if st.sidebar.button("🚪 Logout", key="logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

    # ROUTING
    page = st.session_state.menu_choice

    if page == "PGA":
        pga_allotment()

    elif page == "DNM":
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
