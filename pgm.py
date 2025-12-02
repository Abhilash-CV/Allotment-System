import streamlit as st
import pandas as pd
from io import BytesIO

# ======================================================
#                GENERIC FILE READER
# ======================================================
def read_any(f):
    """
    Read CSV or Excel safely, based on extension.
    """
    name = getattr(f, "name", "").lower()

    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    else:
        # Default to CSV, robust against bad lines
        return pd.read_csv(
            f,
            encoding="ISO-8859-1",
            on_bad_lines="skip"
        )


# ======================================================
#              CATEGORY ELIGIBILITY (PG)
# ======================================================
def category_eligible_pg(seat_cat: str, cand_cat: str) -> bool:
    """
    PG Medical category eligibility logic:

    - NA or NULL candidates:
        -> eligible for SM seats only.
    - SC/ST/EZ/MU/...:
        -> eligible for both their category and SM seats.
    """
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    # Treat empty / null as NA
    if cand_cat in ("", "NULL"):
        cand_cat = "NA"

    # SM = State Merit / general – everyone can compete if otherwise eligible
    if seat_cat == "SM":
        return True

    # If candidate is NA → only SM seats allowed
    if cand_cat == "NA":
        return False

    # Reserved category seats (SC, ST, EZ, MU, etc.)
    if seat_cat == cand_cat:
        return True

    return False


# ======================================================
#             OPTION DECODER (PG STYLE)
# ======================================================
def decode_opt_pg(raw_opt: str):
    """
    Decode an option string into:
        grp, typ, college, course, category_code, flags(service, minority)

    Rule (generic, adaptable to your codes):
    - Last char 'M' => service quota option
    - Last char 'Y' => minority option
    - Remaining structure:
        0   : grp
        1   : typ
        2-3 : college
        4-6 : course
        7+  : seat category code (SM, SC, ST, EZ, MU, HQ, MQ, IQ, etc.)
    """
    if not isinstance(raw_opt, str):
        return None

    opt = raw_opt.strip().upper()
    if len(opt) < 8:
        return None

    is_service = opt.endswith("M")
    is_minority = opt.endswith("Y")

    core = opt
    if is_service or is_minority:
        core = opt[:-1]  # remove suffix

    if len(core) < 8:
        return None

    grp = core[0]
    typ = core[1]
    college = core[2:4]   # 2 chars
    course = core[4:7]    # 3 chars
    category_code = core[7:]  # remaining (SM, SC, ST, HQ, MQ, etc.)

    return {
        "grp": grp,
        "typ": typ,
        "college": college,
        "course": course,
        "seat_cat": category_code,
        "is_service": is_service,
        "is_minority": is_minority,
        "raw": opt,
    }


# ======================================================
#               MAIN PG MED ALLOTMENT
# ======================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Admission Allotment – Simulation")

    st.markdown("### 📂 Upload Input Files")
    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"], key="pg_cand")
    seat_file = st.file_uploader("2️⃣ Seat Matrix File", type=["csv", "xlsx"], key="pg_seat")
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"], key="pg_opt")

    if not (cand_file and seat_file and opt_file):
        st.info("⬆️ Please upload **all three** files to start the allotment.")
        return

    # --------------------------------------------------
    #                READ FILES
    # --------------------------------------------------
    try:
        cand = read_any(cand_file)
        seats = read_any(seat_file)
        opts  = read_any(opt_file)
    except Exception as e:
        st.error(f"❌ Error reading files: {e}")
        return

    st.success("✅ Files loaded successfully!")

    # --------------------------------------------------
    #           BASIC COLUMN CHECKS
    # --------------------------------------------------
    required_seat_cols = ["grp", "typ", "college", "course", "category", "SEAT"]
    for col in required_seat_cols:
        if col not in seats.columns:
            st.error(f"Seat file missing column: **{col}**")
            return

    required_opt_cols = ["RollNo", "OPNO", "Optn"]
    for col in required_opt_cols:
        if col not in opts.columns:
            st.error(f"Option Entry file missing column: **{col}**")
            return

    if "RollNo" not in cand.columns:
        st.error("Candidate file missing column: **RollNo**")
        return

    # Optional columns
    if "ValidOption" not in opts.columns:
        opts["ValidOption"] = "Y"
    if "Delflg" not in opts.columns:
        opts["Delflg"] = ""

    # --------------------------------------------------
    #              CLEAN / NORMALIZE SEATS
    # --------------------------------------------------
    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    # Build seat capacity map
    seat_map = {}
    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_map[key] = seat_map.get(key, 0) + int(r["SEAT"])

    # --------------------------------------------------
    #              CLEAN / NORMALIZE OPTIONS
    # --------------------------------------------------
    opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper().str.strip()
    opts["Delflg"]      = opts["Delflg"].astype(str).str.upper().str.strip()
    opts["Optn"]        = opts["Optn"].astype(str).str.upper().str.strip()

    # Exclude invalid / deleted / OPNO = 0
    opts = opts[
        (pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int) != 0) &
        (opts["ValidOption"] == "Y") &
        (opts["Delflg"] != "Y")
    ].copy()

    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype("Int64")
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    # Sort options by preference
    opts = opts.sort_values(["RollNo", "OPNO"])

    # --------------------------------------------------
    #              CLEAN / NORMALIZE CANDIDATES
    # --------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype("Int64")

    # Main rank: use PRank if present, else NRank
    rank_col = None
    if "PRank" in cand.columns:
        rank_col = "PRank"
    elif "NRank" in cand.columns:
        rank_col = "NRank"
    else:
        st.error("Candidate file must have either **PRank** or **NRank** column.")
        return

    cand[rank_col] = pd.to_numeric(cand[rank_col], errors="coerce").fillna(0).astype(int)

    # Extra quota ranks (if present)
    for rc in ["HQ_Rank", "MQ_Rank", "IQ_Rank", "STRank"]:
        if rc not in cand.columns:
            cand[rc] = 0
        cand[rc] = pd.to_numeric(cand[rc], errors="coerce").fillna(0).astype(int)

    # Category + minority
    if "Category" not in cand.columns:
        cand["Category"] = ""

    if "CheckMinority" not in cand.columns:
        cand["CheckMinority"] = ""

    if "Status" not in cand.columns:
        cand["Status"] = ""

    cand["Category"]      = cand["Category"].astype(str).str.upper().str.strip()
    cand["CheckMinority"] = cand["CheckMinority"].astype(str).str.upper().str.strip()
    cand["Status"]        = cand["Status"].astype(str).str.upper().str.strip()

    # Filter candidates:
    # - PRank/NRank > 0
    # - Status != 'S'
    eligible_cand = cand[
        (cand[rank_col] > 0) &
        (cand["Status"] != "S")
    ].copy()

    # Sort by main rank ascending
    eligible_cand = eligible_cand.sort_values(rank_col)

    # --------------------------------------------------
    #            RUN PG MEDICAL  ALLOTMENT
    # --------------------------------------------------
    st.markdown("### 🧮 Running Allotment...")

    allotments = []

    for _, c in eligible_cand.iterrows():
        roll = int(c["RollNo"])
        main_rank = int(c[rank_col])
        ccat = str(c["Category"]).upper().strip()
        hqr  = int(c.get("HQ_Rank", 0))
        mqr  = int(c.get("MQ_Rank", 0))
        iqr  = int(c.get("IQ_Rank", 0))
        strk = int(c.get("STRank", 0))
        is_minority_candidate = (str(c.get("CheckMinority", "")).upper().strip() == "Y")

        # Get this candidate's valid options
        c_opts = opts[opts["RollNo"] == roll]
        if c_opts.empty:
            continue

        got_seat = False

        for _, op in c_opts.iterrows():
            dec = decode_opt_pg(op["Optn"])
            if not dec:
                continue

            grp      = dec["grp"]
            typ      = dec["typ"]
            college  = dec["college"]
            course   = dec["course"]
            seat_cat = dec["seat_cat"]
            is_sq    = dec["is_service"]
            is_min   = dec["is_minority"]
            raw_opt  = dec["raw"]

            # Service quota: require STRank > 0
            if is_sq and strk <= 0:
                continue

            # Minority seat: require CheckMinority == 'Y'
            if is_min and not is_minority_candidate:
                continue

            # Quota-specific eligibility:
            seat_cat_upper = seat_cat.upper().strip()

            if seat_cat_upper == "HQ" and hqr <= 0:
                continue
            if seat_cat_upper == "MQ" and mqr <= 0:
                continue
            if seat_cat_upper == "IQ" and iqr <= 0:
                continue

            # Filter seat rows for this option (grp, typ, college, course, category)
            seat_rows = seats[
                (seats["grp"] == grp) &
                (seats["typ"] == typ) &
                (seats["college"] == college) &
                (seats["course"] == course)
            ]

            if seat_rows.empty:
                continue

            # Category priority for this candidate:
            # - first: their own category (if not NA)
            # - then HQ, MQ, IQ (if present)
            # - then SM
            community_first = []
            cand_cat_norm = ccat if ccat not in ("", "NULL") else "NA"
            if cand_cat_norm != "NA":
                community_first.append(cand_cat_norm)

            quota_codes = ["HQ", "MQ", "IQ"]
            priority_order = community_first + quota_codes + ["SM"]

            chosen_key = None
            chosen_seat_cat_final = None

            for cat_try in priority_order:
                possible_rows = seat_rows[seat_rows["category"].astype(str).str.upper().str.strip() == cat_try]

                for _, sr in possible_rows.iterrows():
                    key = (sr["grp"], sr["typ"], sr["college"], sr["course"], sr["category"])
                    if seat_map.get(key, 0) <= 0:
                        continue

                    if not category_eligible_pg(sr["category"], ccat):
                        continue

                    # Extra gate for quota again at seat-level
                    cat_upper = str(sr["category"]).upper().strip()
                    if cat_upper == "HQ" and hqr <= 0:
                        continue
                    if cat_upper == "MQ" and mqr <= 0:
                        continue
                    if cat_upper == "IQ" and iqr <= 0:
                        continue

                    # This seat is okay
                    chosen_key = key
                    chosen_seat_cat_final = sr["category"]
                    break

                if chosen_key:
                    break

            # If no category seat taken via priority, try the explicit seat_cat in the option
            if not chosen_key:
                for _, sr in seat_rows.iterrows():
                    key = (sr["grp"], sr["typ"], sr["college"], sr["course"], sr["category"])
                    if seat_map.get(key, 0) <= 0:
                        continue

                    if not category_eligible_pg(sr["category"], ccat):
                        continue

                    chosen_key = key
                    chosen_seat_cat_final = sr["category"]
                    break

            if chosen_key:
                # Deduct seat
                seat_map[chosen_key] -= 1

                allotments.append({
                    "RollNo": roll,
                    "MainRank": main_rank,
                    "CandidateCategory": ccat,
                    "grp": grp,
                    "typ": typ,
                    "College": college,
                    "Course": course,
                    "SeatCategoryAllotted": chosen_seat_cat_final,
                    "IsServiceQuota": "Y" if is_sq else "N",
                    "IsMinoritySeat": "Y" if is_min else "N",
                    "OptionCode": raw_opt
                })

                got_seat = True
                break  # move to next candidate

        # next candidate

    # --------------------------------------------------
    #                 SHOW RESULT
    # --------------------------------------------------
    result_df = pd.DataFrame(allotments)

    st.markdown("### 🟩 Allotment Result")

    if result_df.empty:
        st.warning("No candidates were allotted any seats with the given data & rules.")
        return

    st.write(f"Total Allotted: **{len(result_df)}**")
    st.dataframe(result_df, use_container_width=True)

    # Download
    buffer = BytesIO()
    result_df.to_csv(buffer, index=False)
    buffer.seek(0)

    st.download_button(
        "⬇️ Download Allotment Result (CSV)",
        data=buffer,
        file_name="PG_Med_Allotment_Result.csv",
        mime="text/csv"
    )


# ======================================================
#     DIRECT RUN (if you want this as main app)
# ======================================================
if __name__ == "__main__":
    pg_med_allotment()
