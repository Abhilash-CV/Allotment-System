import streamlit as st
from dnm import dnm_allotment
from pga_stray import pga_allotment

# ==========================================
#            PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Admission System", layout="wide", page_icon="🎓")

# ==========================================
#        BASE GLOBAL CSS (ANIMATED BG)
# ==========================================
BASE_CSS = """
<style>
    /* Remove default menu/footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Moving gradient background */
    .stApp {
        background: linear-gradient(-45deg, #0f172a, #1e293b, #0f766e, #1d4ed8);
        background-size: 300% 300%;
        animation: gradientMove 20s ease infinite;
        min-height: 100vh;
    }

    @keyframes gradientMove {
        0%   { background-position: 0% 50%; }
        50%  { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    :root {
        --primary: #0f6fff;
        --accent: #0ea5e9;
    }

    /* Floating shapes */
    .floating-shape {
        position: fixed;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.06);
        box-shadow: 0 0 40px rgba(0,0,0,0.15);
        z-index: 0;
        animation: float 18s ease-in-out infinite;
    }
    .shape1 { width: 160px; height: 160px; top: 8%; left: 6%; animation-duration: 22s; }
    .shape2 { width: 220px; height: 220px; bottom: 5%; right: 10%; animation-duration: 26s; }
    .shape3 { width: 110px; height: 110px; bottom: 20%; left: 15%; animation-duration: 20s; }

    @keyframes float {
        0%   { transform: translateY(0px) translateX(0px); }
        50%  { transform: translateY(-25px) translateX(15px); }
        100% { transform: translateY(0px) translateX(0px); }
    }

    /* LOGIN OVERLAY & CARD */
    .login-overlay {
        position: relative;
        width: 100%;
        min-height: 100vh;
        z-index: 1;
    }

    .login-wrapper {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        max-width: 430px;
        width: 92%;
    }

    .login-card {
        background: rgba(255,255,255,0.96);
        border-radius: 22px;
        padding: 30px 32px 26px 32px;
        box-shadow: 0 18px 45px rgba(15,23,42,0.38);
        backdrop-filter: blur(16px);
        text-align: center;
    }

    .login-icon {
        margin-bottom: 6px;
    }

    .login-title {
        font-size: 27px;
        font-weight: 800;
        margin-bottom: 4px;
        color: var(--primary);
    }

    .login-subtitle {
        color: #6b7280;
        font-size: 14px;
        margin-bottom: 18px;
    }

    .login-lottie {
        margin-bottom: 6px;
    }

    /* Google-style text fields are mostly handled by Streamlit
       but we keep spacing tight here */
    .stTextInput, .stPasswordInput {
        margin-bottom: 8px;
    }

    /* Login button styling */
    .login-btn button {
        width: 100%;
        padding: 10px 0;
        border-radius: 999px !important;
        font-size: 16px;
        font-weight: 600;
        background: linear-gradient(90deg, var(--primary), var(--accent));
        color: white !important;
        border: none;
        box-shadow: 0 10px 20px rgba(15,23,42,0.35);
    }

    .login-btn button:hover {
        filter: brightness(1.05);
    }

    /* HEADER IN MAIN APP */
    .app-header {
        background: linear-gradient(90deg, var(--primary), var(--accent));
        padding: 16px 24px;
        border-radius: 18px;
        margin-bottom: 18px;
        box-shadow: 0 14px 30px rgba(15,23,42,0.4);
    }
    .app-header h1 {
        color: white;
        font-size: 26px;
        font-weight: 800;
        margin: 0;
        text-align: left;
    }

    /* Sidebar styling & menu */
    [data-testid="stSidebar"] {
        background: #f3f7fb;
        border-right: 1px solid #d4d4d8;
    }

    .menu-item {
        padding: 12px 14px;
        margin: 8px 0;
        border-radius: 12px;
        font-weight: 600;
        font-size: 16px;
        display: block;
        color: #111827;
        background: #ffffff;
        border: 1px solid #e5e7eb;
        cursor: pointer;
    }

    .menu-item:hover {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
    }

    .menu-selected {
        background: #111827 !important;
        color: white !important;
        border-color: #111827 !important;
    }

</style>
"""
st.markdown(BASE_CSS, unsafe_allow_html=True)


# ==========================================
#        THEME HANDLING (ADMIN SELECTOR)
# ==========================================
if "theme" not in st.session_state:
    st.session_state.theme = "Blue"  # default

THEMES = ["Blue", "Purple", "Dark"]


def inject_theme_css(theme: str):
    if theme == "Blue":
        primary = "#0f6fff"
        accent = "#0ea5e9"
    elif theme == "Purple":
        primary = "#7c3aed"
        accent = "#ec4899"
    else:  # Dark
        primary = "#0f172a"
        accent = "#22c55e"

    st.markdown(
        f"""
        <style>
            :root {{
                --primary: {primary};
                --accent: {accent};
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ==========================================
#            LOGIN STATE
# ==========================================
VALID_USERS = {
    "admin": "admin123",
    "user": "user123",
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "menu_choice" not in st.session_state:
    st.session_state.menu_choice = "DNM"


# ==========================================
#            LOGIN PAGE
# ==========================================
def login_page():
    # Theme selector (top center small)
    c1, c2, c3 = st.columns([2, 3, 2])
    with c2:
        theme_choice = st.selectbox(
            "Theme",
            THEMES,
            index=THEMES.index(st.session_state.theme),
            key="theme_choice_login",
        )
    st.session_state.theme = theme_choice
    inject_theme_css(theme_choice)

    # Floating shapes HTML
    st.markdown(
        """
        <div class="floating-shape shape1"></div>
        <div class="floating-shape shape2"></div>
        <div class="floating-shape shape3"></div>
        """,
        unsafe_allow_html=True,
    )

    # Lottie + login card wrapper
    st.markdown(
        """
        <div class="login-overlay">
            <div class="login-wrapper">
                <div class="login-card">
                    <div class="login-lottie">
                        <script src="https://unpkg.com/@lottiefiles/lottie-player@latest/dist/lottie-player.js"></script>
                        <lottie-player src="https://assets1.lottiefiles.com/private_files/lf30_t26law.json"
                                       background="transparent"
                                       speed="1"
                                       style="width: 130px; height: 130px; margin: auto;"
                                       loop autoplay>
                        </lottie-player>
                    </div>
                    <div class="login-icon"></div>
                    <div class="login-title">Secure Login</div>
                    <div class="login-subtitle">Admission Management System</div>
        """,
        unsafe_allow_html=True,
    )

    # Inputs + button are injected inside card
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    st.markdown("<div class='login-btn'>", unsafe_allow_html=True)
    login_clicked = st.button("Login", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Close card + wrappers
    st.markdown(
        """
                </div> <!-- .login-card -->
            </div> <!-- .login-wrapper -->
        </div> <!-- .login-overlay -->
        """,
        unsafe_allow_html=True,
    )

    if login_clicked:
        if username in VALID_USERS and VALID_USERS[username] == password:
            st.session_state.logged_in = True
            st.experimental_rerun()
        else:
            st.error("❌ Invalid username or password")


# ==========================================
#            FUTURE MODULE
# ==========================================
def future_program():
    st.markdown(
        "<div class='app-header'><h1>🛠 Future Tools</h1></div>",
        unsafe_allow_html=True,
    )
    st.info("Upcoming modules will appear here.")


# ==========================================
#            MAIN APPLICATION
# ==========================================
def main_app():
    # Theme selector in sidebar (admin theme)
    theme_choice = st.sidebar.selectbox(
        "Theme",
        THEMES,
        index=THEMES.index(st.session_state.theme),
        key="theme_choice_main",
    )
    st.session_state.theme = theme_choice
    inject_theme_css(theme_choice)

    # HEADER
    st.markdown(
        "<div class='app-header'><h1>🎓 Admission Management System</h1></div>",
        unsafe_allow_html=True,
    )

    # SIDEBAR MENU
    st.sidebar.title("Navigation")

    menu_options = {
        "PGA": "📘 PGA Allotment",
        "DNM": "🧮 DNM Allotment",
        "Future": "🛠 Future Tools",
    }

    for key, label in menu_options.items():
        css_class = "menu-item"
        if st.session_state.menu_choice == key:
            css_class += " menu-selected"

        if st.sidebar.button(label, key=f"menu_{key}", use_container_width=True):
            st.session_state.menu_choice = key
            st.experimental_rerun()

        # (Optional) JS for extra styling hook (won't break if not found)
        st.sidebar.markdown(
            f"""
            <script>
            const btn = window.parent.document.querySelector('button[data-testid="menu_{key}"]');
            if (btn) {{
                btn.className = "{css_class}";
            }}
            </script>
            """,
            unsafe_allow_html=True,
        )

    # LOGOUT BUTTON
    if st.sidebar.button("🚪 Logout", key="logout", use_container_width=True):
        st.session_state.logged_in = False
        st.experimental_rerun()

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
