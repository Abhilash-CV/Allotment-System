import streamlit as st
import pandas as pd
from io import BytesIO

# ==========================================================
# Read CSV/Excel
# ==========================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# ==========================================================
# CATEGORY ELIGIBLE CHECK  ✅ FIXED
# ==========================================================
def eligible_category(seat_cat, cand_cat):
    seat_cat = seat_cat.upper().strip()
    cand_cat = cand_cat.upper().strip()

    if cand_cat in ("", "NULL", "NA"):
        cand_cat = "NA"

    # Special quota seats are controlled by passes_special_rules(),
    # not by community category match.
    if seat_cat in ("NR", "NC", "NM", "AC", "MM", "PD", "CD"):
        return True

    # SM is open to all
    if seat_cat == "SM":
        return True

    # NA candidate only eligible for SM (and specials above)
    if cand_cat == "NA":
        return False

    # Community quota seats: SC/ST/EZ/MU/etc must match
    return seat_cat == cand_cat


# ==========================================================
# Decode Option — PG Format (8 characters)
# ==========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],        # M
        "typ": opt[1],         # G/S
        "course": opt[2:4],    # Course
        "college": opt[4:7],   # College
        "flag": opt[7]         # M/Y/R/N
    }


# ==========================================================
# FINAL 11-DIGIT ALLOT CODE
# MG + CC(2) + COL(3) + CAT(4)
# ==========================================================
def make_allot_code(prog, typ, course, college, category):
    cat2 = category[:2].upper()
    cat4 = cat2 + cat2
    return f"{prog}{typ}{course}{college}{cat4}"


# ==========================================================
# SPECIAL RULES (NR/NC/NM, AC/MM, PD, CD)
# ==========================================================
def passes_special_rules(seat_cat, flag, c_row):
    seat_cat = str(seat_cat).upper().strip()
    flag = str(flag).upper().strip()

    cand_nri  = str(c_row.get("NRI", "")).upper().strip()
    cand_min  = str(c_row.get("Minority", "")).upper().strip()
    cand_sp3  = str(c_row.get("Special3", "")).upper().strip()
    cand_cat  = str(c_row.get("Category", "")).upper().strip()

    # -------------------------------------------------------
    # NRI SEATS (NR, NC, NM)
    # -------------------------------------------------------
    if seat_cat == "NR":
        return (flag == "R" and cand_nri == "NR")

    if seat_cat == "NC":
        return (flag == "R" and cand_nri == "NRNC")

    if seat_cat == "NM":
        return (flag == "R" and cand_nri == "NM")

    # -------------------------------------------------------
    # MINORITY SEATS (AC, MM)
    # -------------------------------------------------------
    if seat_cat == "AC":
        return (flag == "Y" and cand_min == "AC")

    if seat_cat == "MM":
        return (flag == "Y" and cand_min == "MM")

    # -------------------------------------------------------
    # PD seats
    # -------------------------------------------------------
    if seat_cat == "PD":
        return (cand_sp3 == "PD")

    # -------------------------------------------------------
    # CD seats → Only SC + PD
    # -------------------------------------------------------
    if seat_cat == "CD":
        return (cand_cat == "SC" and cand_sp3 == "PD")

    return True


# ==========================================================
# PG MEDICAL ALLOTMENT ENGINE
# ==========================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Allotment – FINAL ENGINE (Correct 11-digit Format)")

    cand_file = st.file_uploader("1️⃣ Upload Candidates File", type=["csv","xlsx"])
    seat_file = st.file_uploader("2️⃣ Upload Seat Matrix File", type=["csv","xlsx"])
    opt_file  = st.file_uploader("3️⃣ Upload Option Entry File", type=["csv","xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("✔ Files Loaded Successfully")

    # ======================================================
    # CLEAN CANDIDATES
    # ======================================================
    for col in ["RollNo","PRank","HQ_Rank","MQ_Rank","IQ_Rank","STRank"]:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    cand["Category"] = cand["Category"].astype(str).str.upper().fillna("NA")
    cand["NRI"] = cand.get("NRI", "").astype(str).str.upper()
    cand["Minority"] = cand.get("Minority", "").astype(str).str.upper()
    cand["Special3"] = cand.get("Special3", "").astype(str).str.upper()
    cand["Status"] = cand.get("Status", "").astype(str).str.upper()

    # Remove PRank=0 and 'S' status
    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")]
    cand = cand.sort_values("PRank")

    # ======================================================
    # CLEAN OPTIONS
    # ======================================================
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ]

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo","OPNO"])

    # ======================================================
    # CLEAN SEATS
    # ======================================================
    for col in ["grp","typ","course","college","category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}
    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_map[key] = seat_map.get(key, 0) + r["SEAT"]

    # ======================================================
    # ALLOTMENT LOOP
    # ======================================================
    allotments = []

    for _, c in cand.iterrows():

        roll = c["RollNo"]
        cat = c["Category"]

        myopts = opts[opts["RollNo"] == roll]
        if myopts.empty:
            continue

        for _, op in myopts.iterrows():

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            prog    = dec["prog"]
            typ     = dec["typ"]
            course  = dec["course"]
            college = dec["college"]
            flag    = dec["flag"]

            sr = seats[
                (seats["grp"] == prog + "M") &
                (seats["typ"] == typ) &
                (seats["course"] == course) &
                (seats["college"] == college)
            ]
            if sr.empty:
                continue

            # Priority order
            priority = []
            if cat not in ("NA","NULL",""): priority.append(cat)
            if c["HQ_Rank"] > 0: priority.append("HQ")
            if c["MQ_Rank"] > 0: priority.append("MQ")
            if c["IQ_Rank"] > 0: priority.append("IQ")
            priority.append("SM")

            chosen = None

            for pcat in priority:

                row = sr[sr["category"] == pcat]
                if row.empty:
                    continue

                key = (prog + "M", typ, college, course, pcat)

                if seat_map.get(key, 0) <= 0:
                    continue

                # Special rules apply here
                if not passes_special_rules(pcat, flag, c):
                    continue

                if not eligible_category(pcat, cat):
                    continue

                chosen = (pcat, key)
                break

            if not chosen:
                continue

            seat_cat, key = chosen
            seat_map[key] -= 1

            allot_code = make_allot_code(prog, typ, course, college, seat_cat)

            allotments.append({
                "RollNo": roll,
                "OPNO": op["OPNO"],
                "AllotCode": allot_code,
                "College": college,
                "Course": course,
                "SeatCategory": seat_cat
            })

            break  # stop after allotment

    # ======================================================
    # OUTPUT
    # ======================================================
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Completed Successfully")
    st.write(f"Total Allotted = **{len(result)}**")

    st.dataframe(result)

    buf = BytesIO()
    result.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download PG Allotment",
        buf,
        "PG_Allotment.csv",
        "text/csv",
    )
