import streamlit as st
import pandas as pd
from io import BytesIO

# ----------------------------------------------------
# LOGIN CONFIG
# ----------------------------------------------------
VALID_USERS = {
    "admin": "admin123",
    "user": "user123"
}

# Session state for login
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
# UNIVERSAL FILE READER
# ----------------------------------------------------
def read_any(file):
    name = file.name.lower()

    if name.endswith(".csv"):
        file.seek(0)
        return pd.read_csv(file, encoding="ISO-8859-1")

    if name.endswith(".xlsx") or name.endswith(".xls"):
        file.seek(0)
        try:
            xls = pd.ExcelFile(file, engine="odf")
            return pd.read_excel(xls)
        except:
            file.seek(0)
            return pd.read_csv(file, encoding="ISO-8859-1")

    file.seek(0)
    return pd.read_csv(file, encoding="ISO-8859-1")


# ----------------------------------------------------
# CATEGORY ELIGIBILITY
# ----------------------------------------------------
def category_eligible(seat_cat, cand_cat):
    seat_cat = str(seat_cat).strip().upper()
    cand_cat = str(cand_cat or "").strip().upper()

    if seat_cat in ["AM", "SM"]:
        return True

    if cand_cat in ["NA", "NULL", "", None, "N/A"]:
        return False

    return seat_cat == cand_cat


# ----------------------------------------------------
# DNM MODULE  (YOUR WORKING PROGRAM)
# ----------------------------------------------------
def dnm_allotment():

    st.title("🧮 DNM Admission Allotment")

    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv","xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix", type=["csv","xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv","xlsx"])

    if cand_file and seat_file and opt_file:

        cand = read_any(cand_file)
        seats = read_any(seat_file)
        opts = read_any(opt_file)
        st.success("Files loaded successfully!")

        # ---------------- CLEAN SEATS ----------------
        for col in ["grp","typ","college","course","category","SEAT"]:
            if col not in seats.columns:
                st.error(f"Seat file missing column: {col}")
                st.stop()

        for col in ["grp","typ","college","course","category"]:
            seats[col] = seats[col].astype(str).str.upper().str.strip()

        seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

        seat_map = {}
        for _, r in seats.iterrows():
            key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
            seat_map[key] = seat_map.get(key, 0) + r["SEAT"]

        # ---------------- CLEAN OPTIONS ----------------
        opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper().str.strip()
        opts["Delflg"] = opts["Delflg"].astype(str).str.upper().str.strip()
        opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()

        opts = opts[(opts["OPNO"] != 0) &
                    (opts["ValidOption"] == "Y") &
                    (opts["Delflg"] != "Y")].copy()

        opts = opts.sort_values(["RollNo", "OPNO"])
        opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype("Int64")

        # ---------------- CLEAN CANDIDATES ----------------
        cand["ARank"] = pd.to_numeric(cand["ARank"], errors="coerce").fillna(9999999)
        cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype("Int64")

        if "Category" not in cand.columns:
            cand["Category"] = ""

        if "AIQ" not in cand.columns:
            cand["AIQ"] = ""

        cand_sorted = cand.sort_values("ARank")

        # ---------------- OPTION DECODER ----------------
        def decode_opt(opt):
            opt = opt.strip().upper()
            if len(opt) < 7:
                return None
            return opt[0], opt[1], opt[2:4], opt[4:7]

        # ---------------- RUN ALLOTMENT ----------------
        allotments = []

        for _, c in cand_sorted.iterrows():
            roll = int(c["RollNo"])
            arank = int(c["ARank"])
            ccat = str(c["Category"]).upper().strip()

            if str(c.get("AIQ","")).strip().upper() == "Y":
                continue

            c_opts = opts[opts["RollNo"] == roll]
            if c_opts.empty:
                continue

            for _, op in c_opts.iterrows():

                decoded = decode_opt(op["Optn"])
                if not decoded:
                    continue

                og, otyp, ocourse, oclg = decoded

                seat_rows = seats[
                    (seats["grp"] == og) &
                    (seats["typ"] == otyp) &
                    (seats["college"] == oclg) &
                    (seats["course"] == ocourse)
                ]

                if seat_rows.empty:
                    continue

                chosen_key = None
                chosen_cat = None

                priority_order = ["AM", "SM"]
                community_cats = sorted(set(seat_rows["category"]) - {"AM", "SM"})
                priority_order += community_cats

                for cat in priority_order:
                    for _, sr in seat_rows[seat_rows["category"] == cat].iterrows():

                        key = (sr["grp"], sr["typ"], sr["college"],
                               sr["course"], sr["category"])

                        if seat_map.get(key, 0) <= 0:
                            continue

                        if category_eligible(sr["category"], ccat):
                            chosen_key = key
                            chosen_cat = sr["category"]
                            break

                    if chosen_key:
                        break

                if chosen_key:
                    seat_map[chosen_key] -= 1
                    allotments.append({
                        "RollNo": roll,
                        "ARank": arank,
                        "CandidateCategory": ccat,
                        "grp": og,
                        "typ": otyp,
                        "College": oclg,
                        "Course": ocourse,
                        "SeatCategoryAllotted": chosen_cat
                    })
                    break

        result_df = pd.DataFrame(allotments)
        st.subheader("🟩 Allotment Result")
        st.write(f"Total Allotted: **{len(result_df)}**")
        st.dataframe(result_df)

        buffer = BytesIO()
        result_df.to_csv(buffer, index=False)
        buffer.seek(0)

        st.download_button("⬇️ Download Result CSV", buffer,
                           "DNM_allotment_result.csv", "text/csv")


# ----------------------------------------------------
# PGA MODULE (Placeholder)
# ----------------------------------------------------
def pga_module():
    st.title("📘 PGA Module")
    st.info("PGA Program will be added here.")


# ----------------------------------------------------
# MAIN APP WITH SIDEBAR MENU
# ----------------------------------------------------
def main_app():

    st.sidebar.title("📌 Menu")
    choice = st.sidebar.radio("Select Module", ["PGA", "DNM", "Future Program 1", "Future Program 2"])

    if choice == "PGA":
        pga_module()

    elif choice == "DNM":
        dnm_allotment()

    else:
        st.title("🛠 Future Module")
        st.info("New programs will be added here later.")


# ----------------------------------------------------
# APP FLOW
# ----------------------------------------------------
if not st.session_state.logged_in:
    login_page()
else:
    main_app()
