import streamlit as st
import pandas as pd
from io import BytesIO

# ===============================================================
# LOAD CSV / EXCEL
# ===============================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# ===============================================================
# CATEGORY ELIGIBILITY
# ===============================================================
def eligible_category(seat_cat, cand_cat):
    seat_cat = seat_cat.upper().strip()
    cand_cat = cand_cat.upper().strip()

    if cand_cat in ("", "NULL"):
        cand_cat = "NA"

    # SM is open to everyone
    if seat_cat == "SM":
        return True

    # NA candidate → only SM is allowed
    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


# ===============================================================
# DECODE PG OPTION ENTRY (8 LETTERS)
# ===============================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None

    return {
        "prog": opt[0],            # M
        "typ": opt[1],             # G/S
        "course": opt[2:4],        # ET
        "college": opt[4:7],       # EMC
        "flag": opt[7]             # M/Y/N
    }


# ===============================================================
# FINAL 11-CHAR ALLOT CODE
# ===============================================================
def make_allot_code(prog, typ, course, college, category):
    """
    Format:
    1-2 : M + G/S
    3-4 : Course (2 letters)
    5-7 : College (3 letters)
    8-9 : Category Prefix (1st letter ×2)
    10-11: Category Code (first 2 letters)
    Example: MSETEMCSMSM
    """

    cat_prefix = category[0] * 2     # SM → SS
    cat_code = category[:2]          # SM → SM

    return f"{prog}{typ}{course}{college}{cat_prefix}{cat_code}"


# ===============================================================
# MAIN PG MEDICAL PROCESS
# ===============================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Allotment Processor (Correct 11-Digit Format)")

    cand_file = st.file_uploader("1️⃣ Upload Candidates file", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Upload Seat Matrix", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Upload Option Entry", type=["csv", "xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)
    st.success("Files loaded correctly!")

    # --------------------------------------------------------
    # CLEAN CANDIDATES
    # --------------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["PRank"]  = pd.to_numeric(cand["PRank"], errors="coerce").fillna(0).astype(int)

    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank", "STRank"]:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    cand["Category"] = cand["Category"].astype(str).str.upper().fillna("NA")
    cand["CheckMinority"] = cand.get("CheckMinority", "").astype(str).str.upper()
    cand["Status"] = cand.get("Status", "").astype(str).str.upper()

    # remove stopped/ineligible
    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")]
    cand = cand.sort_values("PRank")

    # --------------------------------------------------------
    # CLEAN OPTIONS
    # --------------------------------------------------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype(int)
    opts["OPNO"] = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ]

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo", "OPNO"])

    # --------------------------------------------------------
    # CLEAN SEAT MATRIX
    # --------------------------------------------------------
    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}
    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_map[key] = seat_map.get(key, 0) + r["SEAT"]

    # --------------------------------------------------------
    # ALLOTMENT
    # --------------------------------------------------------
    allotments = []

    for _, c in cand.iterrows():

        roll = c["RollNo"]
        cat = c["Category"]
        hq = c["HQ_Rank"]
        mq = c["MQ_Rank"]
        iq = c["IQ_Rank"]
        strank = c["STRank"]
        is_minority = (c["CheckMinority"] == "Y")

        c_opts = opts[opts["RollNo"] == roll]
        if c_opts.empty:
            continue

        for _, op in c_opts.iterrows():

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            prog = dec["prog"]
            typ = dec["typ"]
            course = dec["course"]
            college = dec["college"]
            flag = dec["flag"]

            # service seat rule
            if flag == "M" and strank <= 0:
                continue

            # minority rule
            if flag == "Y" and not is_minority:
                continue

            # matching seat rows
            sr = seats[
                (seats["grp"] == prog + "M") &
                (seats["typ"] == typ) &
                (seats["course"] == course) &
                (seats["college"] == college)
            ]

            if sr.empty:
                continue

            # category order
            priority = []

            if cat not in ("NA", "NULL", ""):
                priority.append(cat)  # reserved first

            # quota seats
            if hq > 0: priority.append("HQ")
            if mq > 0: priority.append("MQ")
            if iq > 0: priority.append("IQ")

            priority.append("SM")  # always last

            chosen = None

            for pcat in priority:
                row = sr[sr["category"] == pcat]
                if row.empty:
                    continue

                key = (prog + "M", typ, college, course, pcat)

                if seat_map.get(key, 0) <= 0:
                    continue

                if not eligible_category(pcat, cat):
                    continue

                chosen = (pcat, key)
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
                "OPNO": op["OPNO"],
                "AllotCode": allot_code,
                "College": college,
                "Course": course,
                "SeatCategory": seat_cat
            })

            break  # stop options for this candidate

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Complete")
    st.write(f"Total Allotted: **{len(result)}**")
    st.dataframe(result)

    buf = BytesIO()
    result.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download PG Allotment Result",
        buf,
        "PG_allotment.csv",
        "text/csv"
    )
