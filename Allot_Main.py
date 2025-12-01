import streamlit as st
from dnm import dnm_allotment      # ← IMPORT DNM MODULE


# ----------------------------------------------------
# LOGIN CONFIG
# ----------------------------------------------------
VALID_USERS = {
    "admin": "admin123",
    "user": "user123"
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


# ----------------------------------------------------
# LOGIN PAGE
# ----------------------------------------------------
def login_page():
    st.title("🔐 Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username in VALID_USERS and VALID_USERS[username] == password:
            st.session_state.logged_in = True
            st.success("Login successful!")
        else:
            st.error("Invalid username or password")


# ----------------------------------------------------
# PGA MODULE (Placeholder)
# ----------------------------------------------------
def pga_module():
    st.title("🎓 PGA Module")
    st.info("PGA program will be added soon.")


# ----------------------------------------------------
# MAIN APP WITH MENU
# ----------------------------------------------------
def main_app():

    st.sidebar.title("📌 Menu")

    menu = st.sidebar.radio("Select Program", ["PGA", "DNM", "Future Program 1"])

    if menu == "PGA":
        pga_module()

    elif menu == "DNM":
        dnm_allotment()   # ← CALL DNM MODULE

    else:
        st.title("🛠 Future Program 1")
        st.info("New tools will be added here later.")


# ----------------------------------------------------
# APP FLOW
# ----------------------------------------------------
if not st.session_state.logged_in:
    login_page()
else:
    main_app()
