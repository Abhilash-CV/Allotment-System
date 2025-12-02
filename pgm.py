import streamlit as st
import pandas as pd
from io import BytesIO

# ==========================================================
# Read any file (CSV / Excel)
# ==========================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# ==========================================================
# CATEGORY ELIGIBLE CHECK
# ==========================================================
def eligible_category(seat_cat, cand_cat):
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NULL", "NA"):
        cand_cat = "NA"

    # HQ / MQ / IQ quotas are based on respective ranks, not community
    if seat_cat in ("HQ", "MQ", "IQ"):
        return True

    # SM is open to everyone
    if seat_cat == "SM":
        return True

    # NA candidate only eligible for SM (HQ/MQ/IQ handled above)
    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


# ==========================================================
# Decode Option — PG Format (8 characters)
# ==========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None

    return {
        "prog": opt[0],            # M
        "typ": opt[1],             # G/S
        "course": opt[2:4],        # 2 letters
        "college": opt[4:7],       # 3 letters
        "flag": opt[7]             # M/Y/N
    }


# ==========================================================
# FINAL 11-DIGIT PG ALLOT CODE
# ==========================================================
def make_allot_code(prog, typ, course, college, category):
    """
    FINAL PG ALLOTMENT FORMAT (11 characters):
    MG + CC(2) + COL(3) + CAT(4)
    CAT(4) = category repeated twice (SM → SMSM)
    """
    cat2 = category[:2].upper()
    cat4 = cat2 + cat2
    return f"{prog}{typ}{course}{college}{cat4}"


# ==========================================================
# PG MEDICAL ALLOTMENT MAIN
# ==========================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Allotment (Correct 11-digit Format, Optimized)")

    cand_file = st.file_uploader("1️⃣ Upload Candidates File", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Upload Seat Matrix File", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Upload Option Entry File", type=["csv", "xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    # ---------- LOAD ----------
    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)
    st.success("Files loaded successfully!")

    # ---------- SHOW BASIC COUNTS ----------
    st.write("Processing candidates:", len(cand))
    st.write("Options:", len(opts))
    st.write("Seats:", len(seats))

    # ----------------------------------------------------------
    # CLEAN CANDIDATES
    # ----------------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["PRank"]  = pd.to_numeric(cand["PRank"], errors="coerce").fillna(0).astype(int)

    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank", "STRank"]:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    cand["Category"] = cand["Category"].astype(str).str.upper().fillna("NA")
    cand["CheckMinority"] = cand.get("CheckMinority", "").astype(str).str.upper()
    cand["Status"] = cand.get("Status", "").astype(str).str.upper()

    # Remove S status & PRank=0
    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")].copy()
    cand = cand.sort_values("PRank").reset_index(drop=True)

    # ----------------------------------------------------------
    # CLEAN OPTION ENTRY
    # ----------------------------------------------------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ].copy()

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo", "OPNO"]).reset_index(drop=True)

    # ---- build options index: RollNo -> list of option rows ----
    from collections import defaultdict
    opts_by_roll = defaultdict(list)
    for row in opts.itertuples(index=False):
        opts_by_roll[row.RollNo].append(row)

    # ----------------------------------------------------------
    # CLEAN SEAT MATRIX
    # ----------------------------------------------------------
    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    # ---- build fast seat_map & index by (typ, course, college) ----
    seat_map = {}  # (typ, course, college, category) -> remaining seats
    seat_cats_index = defaultdict(set)  # (typ, course, college) -> set(categories)

    for r in seats.itertuples(index=False):
        key = (r.typ, r.course, r.college, r.category)
        seat_map[key] = seat_map.get(key, 0) + int(r.SEAT)

        tcc = (r.typ, r.course, r.college)
        seat_cats_index[tcc].add(r.category)

    # ----------------------------------------------------------
    # ALLOTMENT PROCESSING (OPTIMIZED)
    # ----------------------------------------------------------
    allotments = []

    for c in cand.itertuples(index=False):

        roll = c.RollNo
        cat = c.Category
        hq = c.HQ_Rank
        mq = c.MQ_Rank
        iq = c.IQ_Rank
        strank = c.STRank
        minority = (c.CheckMinority == "Y")

        myopts = opts_by_roll.get(roll)
        if not myopts:
            continue

        got_seat = False

        for op in myopts:

            dec = decode_opt(op.Optn)
            if not dec:
                continue

            prog    = dec["prog"]
            typ     = dec["typ"]
            course  = dec["course"]
            college = dec["college"]
            flag    = dec["flag"]

            # Service seat rule
            if flag == "M" and strank <= 0:
                continue

            # Minority seat rule
            if flag == "Y" and not minority:
                continue

            tcc_key = (typ, course, college)
            if tcc_key not in seat_cats_index:
                continue

            available_cats = seat_cats_index[tcc_key]

            # Priority order of categories
            priority = []

            if cat not in ("NA", "NULL", "", None) and cat in available_cats:
                priority.append(cat)

            if "HQ" in available_cats and hq > 0:
                priority.append("HQ")
            if "MQ" in available_cats and mq > 0:
                priority.append("MQ")
            if "IQ" in available_cats and iq > 0:
                priority.append("IQ")

            if "SM" in available_cats:
                priority.append("SM")

            chosen_cat = None
            chosen_key = None

            for seat_cat in priority:
                skey = (typ, course, college, seat_cat)

                if seat_map.get(skey, 0) <= 0:
                    continue

                if not eligible_category(seat_cat, cat):
                    continue

                chosen_cat = seat_cat
                chosen_key = skey
                break

            if not chosen_cat:
                continue

            # Deduct seat
            seat_map[chosen_key] -= 1
            got_seat = True

            allot_code = make_allot_code(prog, typ, course, college, chosen_cat)

            allotments.append({
                "RollNo": roll,
                "OPNO": op.OPNO,
                "AllotCode": allot_code,
                "College": college,
                "Course": course,
                "SeatCategory": chosen_cat
            })

            break  # stop after first successful allotment

        # next candidate

    # ----------------------------------------------------------
    # OUTPUT
    # ----------------------------------------------------------
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Completed")
    st.write(f"Total Allotted: **{len(result)}**")
    st.dataframe(result)

    buf = BytesIO()
    result.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download PG Allotment Result",
        buf,
        "PG_Allotment.csv",
        "text/csv"
    )
