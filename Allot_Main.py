import streamlit as st
from dnm import dnm_allotment
from pga_stray import pga_allotment

# ==========================================
#            PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Admission System", layout="wide", page_icon="🎓")

# ==========================================
#     BASE CSS (ANIMATED BACKGROUND + CARD)
# ==========================================
CUSTOM_CSS = """
<style>

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Moving Gradient Background */
    .stApp {
        background: linear-gradient(-45deg, #0f172a, #1e293b, #0f766e, #1d4ed8);
        background-size: 400% 400%;
        animation: gradientMove 20s ease infinite;
        min-height: 100vh;
    }

    @keyframes gradientMove {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* Floating Shapes */
    .floating-shape {
        position: fixed;
        border-radius: 50%;
        background: rgba(255,255,255,0.08);
        box-shadow: 0 0 40px rgba(0,0,0,0.15);
        z-index: 0;
        animation: float 20s ease-in-out infinite;
    }

    .shape1 { width: 150px; height: 150px; top: 10%; left: 5%; }
    .shape2 { width: 200px; height: 200px; bottom: 10%; right: 10%; animation-duration: 25s; }
    .shape3 { width: 100px; height: 100px; bottom: 20%; left: 20%; animation-duration: 18s; }

    @keyframes float {
        0%   { transform: translateY(0px) translateX(0px); }
        50%  { transform: translateY(-25px) translateX(15px); }
        100% { transform: translateY(0px) translateX(0px); }
    }

    /* Top Bar */
    .top-bar {
        position: absolute;
        top: 12px;
        width: 100%;
        display: flex;
        justify-content: space-between;
        padding: 0 22px;
        z-index: 50;
    }

    /* Top-left Theme Selector */
    .theme-box {
        background: rgba(255,255,255,0.12);
        padding: 8px 14px;
        border-radius: 12px;
        backdrop-filter: blur(10px);
        color: white;
        font-weight: 600;
        box-shadow: 0px 5px 16px rgba(0,0,0,0.24);
    }

    /* Top-right Inputs */
    .top-input-box {
        display: flex;
        gap: 8px;
        background: rgba(255,255,255,0.12);
        padding: 10px 14px;
        border-radius: 12px;
        backdrop-filter: blur(10px);
        box-shadow: 0px 5px 18px rgba(0,0,0,0.25);
        align-items: center;
    }

    /* Small size text fields */
    .top-input-box .stTextInput>div>div>input,
    .top-input-box .stPasswordInput>div>div>input {
        height: 34px !important;
        font-size: 14px !important;
        padding: 4px 8px !important;
        border-radius: 8px !important;
    }

    /* Small login button */
    .top-login-btn button {
        height: 34px !important;
        padding: 2px 14px !important;
        font-size: 14px !important;
        border-radius: 8px !important;
    }

    /* Center Login Card */
    .login-overlay {
        position: relative;
        width: 100%;
        height: 95vh;
        z-index: 10;
    }
    .login-wrapper {
        position: absolute;
        top: 52%;
        left: 50%;
        transform: translate(-50%, -50%);
    }

    .login-card {
        width: 380px;
        padding: 28px 28px;
        border-radius: 20px;
        background: rgba(255,255,255,0.96);
        box-shadow: 0 16px 45px rgba(15,23,42,0.45);
        text-align: center;
    }

    .login-card h2 {
        font-size: 22px;
        font-weight: 800;
        color: var(--primary);
    }

    /* Main App Header */
    .app-header {
        background: linear-gradient(95deg, var(--primary), var(--accent));
        padding: 15px;
        border-radius: 16px;
        margin-bottom: 16px;
        box-shadow: 0 12px 28px rgba(15,23,42,0.35);
    }
    .app-header h1 {
        color: white;
        font-size: 26px;
        font-weight: 800;
        margin: 0;
    }

    /* Sidebar Menu */
    [data-testid="stSidebar"] {
        background: #f8fafc;
        border-right: 1px solid #d7dce3;
    }

    .menu-item {
        padding: 12px 14px;
        margin: 8px 0;
        border-radius: 12px;
        font-weight: 600;
        font-size: 16px;
        background: #ffffff;
        border: 1px solid #e5e7eb;
    }

    .menu-item:hover {
        background: var(--primary);
        color: white;
    }

    .menu-selected {
        background: #1e293b !important;
        color: white !important;
    }

</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ==========================================
#          THEMES (TOP-LEFT SELECTOR)
# ==========================================
THEMES = ["Blue", "Purple", "Dark"]

if "theme" not in st.session_state:
    st.session_state.theme = "Blue"

def inject_theme_css(theme_name):
    if theme_name == "Blue":
        primary = "#0f6fff"; accent = "#0ea5e9"
    elif theme_name == "Purple":
        primary = "#7c3aed"; accent = "#ec4899"
    else:
        primary = "#0f172a"; accent = "#22c55e"

    st.markdown(f"""
        <style>
            :root {{
                --primary: {primary};
                --accent: {accent};
            }}
        </style>
    """, unsafe_allow_html=True)

# ==========================================
#         LOGIN SYSTEM STATE
# ==========================================
VALID_USERS = {"admin": "admin123", "user": "user123"}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "menu_choice" not in st.session_state:
    st.session_state.menu_choice = "DNM"

# ==========================================
#               LOGIN PAGE
# ==========================================
def login_page():

    inject_theme_css(st.session_state.theme)

    # FLOATING SHAPES
    st.markdown("""
        <div class="floating-shape shape1"></div>
        <div class="floating-shape shape2"></div>
        <div class="floating-shape shape3"></div>
    """, unsafe_allow_html=True)

    # TOP BAR
    st.markdown("""
        <div class="top-bar">
            <div class="theme-box">🎨 Theme</div>
            <div class="top-input-box">
    """, unsafe_allow_html=True)

    # TOP RIGHT SMALL LOGIN BOX
    c1, c2, c3 = st.columns([1.3, 1.3, 0.8])
    with c1:
        username = st.text_input("User", key="u_top", label_visibility="collapsed")
    with c2:
        password = st.text_input("Pass", type="password", key="p_top", label_visibility="collapsed")
    with c3:
        top_login_btn = st.button("Login", key="top_login_btn", help="Login here")

    st.markdown("</div></div>", unsafe_allow_html=True)

    # THEME SELECTBOX (INTERACTIVE)
    selected_theme = st.selectbox(
        "Select Theme",
        THEMES,
        index=THEMES.index(st.session_state.theme),
    )
    st.session_state.theme = selected_theme
    inject_theme_css(selected_theme)

    # CENTER LOGIN CARD WITH LOTTIE
    st.markdown("""
        <div class="login-overlay">
            <div class="login-wrapper">
                <div class="login-card">
                    <script src="https://unpkg.com/@lottiefiles/lottie-player@latest/dist/lottie-player.js"></script>
                    <lottie-player src="https://assets1.lottiefiles.com/private_files/lf30_t26law.json"
                                   background="transparent"
                                   speed="1"
                                   style="width: 120px; height: 120px; margin: auto;"
                                   loop autoplay></lottie-player>
                    <h2>Secure Login</h2>
                    <p>Admission Management System</p>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # LOGIN CHECK
    if top_login_btn:
        if username in VALID_USERS and VALID_USERS[username] == password:
            st.session_state.logged_in = True
            st.experimental_rerun()
        else:
            st.error("❌ Invalid username or password")

# ==========================================
#           FUTURE PLACEHOLDER
# ==========================================
def future_program():
    st.markdown("<div class='app-header'><h1>🛠 Future Tools</h1></div>", unsafe_allow_html=True)
    st.info("New tools will be added here soon!")

# ==========================================
#             MAIN APPLICATION
# ==========================================
def main_app():

    # SIDEBAR THEME SELECTOR
    theme_choice = st.sidebar.selectbox("Theme", THEMES)
    st.session_state.theme = theme_choice
    inject_theme_css(theme_choice)

    # HEADER
    st.markdown("<div class='app-header'><h1>🎓 Admission Management System</h1></div>", unsafe_allow_html=True)

    # Sidebar menu
    menu = {
        "PGA": "📘 PGA Allotment",
        "DNM": "🧮 DNM Allotment",
        "Future": "🛠 Future Tools"
    }

    st.sidebar.title("Navigation")
    for key, label in menu.items():

        css = "menu-item"
        if st.session_state.menu_choice == key:
            css += " menu-selected"

        if st.sidebar.button(label, key=f"menu_{key}", use_container_width=True):
            st.session_state.menu_choice = key
            st.experimental_rerun()

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.experimental_rerun()

    # ROUTING
    if st.session_state.menu_choice == "PGA":
        pga_allotment()
    elif st.session_state.menu_choice == "DNM":
        dnm_allotment()
    else:
        future_program()

# ==========================================
#               APP FLOW
# ==========================================
if st.session_state.logged_in:
    main_app()
else:
    login_page()
