import streamlit as st
import pandas as pd
from io import BytesIO

# ===================================================================
# Safe file reader (CSV / Excel)
# ===================================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# ===================================================================
# Category eligibility for PG
# ===================================================================
def category_eligible_pg(seat_cat, cand_cat):
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NULL"):
        cand_cat = "NA"

    if seat_cat == "SM":
        return True

    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


# ===================================================================
# Decode PG OptionEntry Code (8 chars)
# ===================================================================
def decode_opt_pg(opt):
    if not isinstance(opt, str):
        return None

    opt = opt.strip().upper()
    if len(opt) != 8:
        return None

    prog = opt[0]
    typ  = opt[1]
    course = opt[2:4]
    college = opt[4:7]
    flag = opt[7]  # M / Y / other

    is_service  = (flag == "M")
    is_minority = (flag == "Y")

    return {
        "prog": prog,
        "typ": typ,
        "course": course,
        "college": college,
        "flag": flag,
        "is_service": is_service,
        "is_minority": is_minority,
        "raw": opt
    }


# ===================================================================
# Make final PG allot code (11 chars)
# ===================================================================
def make_allot_code(prog, typ, course, college, seat_cat):
    seat_cat4 = seat_cat * 2                 # SC → SCSC
    cat_prefix = seat_cat[0]                # S / E / M / N ...
    return f"{prog}{typ}{course}{college}{cat_prefix}{seat_cat4}"


# ===================================================================
# MAIN PG ALLOTMENT
# ===================================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Admission – Allotment Processor")

    cand_file = st.file_uploader("1️⃣ Candidates File",     type=["csv","xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix File",    type=["csv","xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry File",   type=["csv","xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    cand  = read_any(cand_file)
    seats = read_any(seat_file)
    opts  = read_any(opt_file)

    st.success("📂 Files loaded.")

    # --------------------------------------------------------------
    # Clean: CANDIDATES
    # --------------------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["PRank"]  = pd.to_numeric(cand.get("PRank", 0), errors="coerce").fillna(0).astype(int)

    for col in ["HQ_Rank","MQ_Rank","IQ_Rank","STRank"]:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    if "Category" not in cand.columns:
        cand["Category"] = ""

    if "CheckMinority" not in cand.columns:
        cand["CheckMinority"] = ""

    if "Status" not in cand.columns:
        cand["Status"] = ""

    cand = cand[
        (cand["PRank"] > 0) &
        (cand["Status"].astype(str).str.upper() != "S")
    ].copy()

    cand = cand.sort_values("PRank")

    # --------------------------------------------------------------
    # Clean: OPTIONS
    # --------------------------------------------------------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ].copy()

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo","OPNO"])

    # --------------------------------------------------------------
    # Clean: SEAT MATRIX
    # --------------------------------------------------------------
    for col in ["grp","typ","college","course","category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}
    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["course"], r["college"], r["category"])
        seat_map[key] = seat_map.get(key,0) + int(r["SEAT"])

    # --------------------------------------------------------------
    # RUN PG ALLOTMENT
    # --------------------------------------------------------------
    allotments = []

    for _, c in cand.iterrows():

        roll = c["RollNo"]
        cat  = str(c["Category"]).upper().strip()
        hqr, mqr, iqr, strk = c["HQ_Rank"], c["MQ_Rank"], c["IQ_Rank"], c["STRank"]
        minority_ok = (str(c["CheckMinority"]).upper().strip() == "Y")

        myopts = opts[opts["RollNo"] == roll]
        if myopts.empty:
            continue

        got = False

        for _, op in myopts.iterrows():

            dec = decode_opt_pg(op["Optn"])
            if not dec:
                continue

            prog = dec["prog"]
            typ  = dec["typ"]
            course = dec["course"]
            college = dec["college"]
            is_service  = dec["is_service"]
            is_minority = dec["is_minority"]

            # Service rule
            if is_service and strk <= 0:
                continue

            # Minority rule
            if is_minority and not minority_ok:
                continue

            # Find seats for this course+college
            relevant_rows = seats[
                (seats["grp"] == f"PGM") &
                (seats["typ"] == typ) &
                (seats["course"] == course) &
                (seats["college"] == college)
            ]

            if relevant_rows.empty:
                continue

            # Category priority
            priority = []

            if cat not in ("", "NULL", "NA"):
                priority.append(cat)

            priority.extend(["HQ","MQ","IQ","SM"])

            chosen = None

            for cat_try in priority:

                for _, sr in relevant_rows.iterrows():

                    seat_cat = sr["category"]

                    if seat_cat != cat_try:
                        continue

                    key = (sr["grp"], sr["typ"], sr["course"], sr["college"], seat_cat)

                    if seat_map.get(key,0) <= 0:
                        continue

                    # quota checks
                    if seat_cat == "HQ" and hqr <= 0:
                        continue
                    if seat_cat == "MQ" and mqr <= 0:
                        continue
                    if seat_cat == "IQ" and iqr <= 0:
                        continue

                    if not category_eligible_pg(seat_cat, cat):
                        continue

                    chosen = (seat_cat, key)
                    break

                if chosen:
                    break

            if not chosen:
                continue

            seat_cat, key = chosen
            seat_map[key] -= 1

            allot_code = make_allot_code(
                prog, typ, course, college, seat_cat
            )

            allotments.append({
                "RollNo": roll,
                "AllotCode": allot_code,
                "College": college,
                "Course": course,
                "SeatCategory": seat_cat
            })

            got = True
            break

    # -----------------------------------------------------------------
    # SHOW RESULT
    # -----------------------------------------------------------------
    df = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Result")
    st.write(f"Total Allotted: **{len(df)}**")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download PG Medical Allotment",
        buf,
        "PG_Allotment.csv",
        "text/csv"
    )
