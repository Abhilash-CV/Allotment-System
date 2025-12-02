import streamlit as st
import pandas as pd
from io import BytesIO
from collections import defaultdict


# ==========================================================
# Read any file (CSV / Excel)
# ==========================================================
def read_any(f):
    fname = f.name.lower()
    if fname.endswith(".xlsx") or fname.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# ==========================================================
# CATEGORY ELIGIBLE CHECK
# ==========================================================
def eligible_category(seat_cat, cand_cat):

    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NA", "NULL"):
        cand_cat = "NA"

    # HQ/MQ/IQ eligibility is determined by ranks, not communities
    if seat_cat in ("HQ", "MQ", "IQ"):
        return True

    # SM is open to all
    if seat_cat == "SM":
        return True

    # NA candidates only eligible for SM
    if cand_cat == "NA":
        return False

    # For community seats (SC, ST, EZ, MU, LA, VK, BX...)
    return seat_cat == cand_cat


# ==========================================================
# Decode PG Option Format
# Optn = M G CC COL F
#        0 1 2  4  7
# ==========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None

    return {
        "prog": opt[0],        # M
        "typ": opt[1],         # G or S
        "course": opt[2:4],    # e.g., VL, AN
        "college": opt[4:7],   # 3 letters
        "flag": opt[7]         # M(service) / Y(minority) / N
    }


# ==========================================================
# FINAL PG ALLOT CODE (11 CHARACTERS)
# MG + CC(2) + COL(3) + CATCAT (4)
# ==========================================================
def make_allot_code(prog, typ, course, college, category):
    cat = category[:2].upper()
    cat4 = cat + cat
    return f"{prog}{typ}{course}{college}{cat4}"


# ==========================================================
# MAIN FUNCTION
# ==========================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Allotment (Correct 11-digit Format, Optimized)")

    cand_file = st.file_uploader("1️⃣ Upload Candidates File", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Upload Seat Matrix File", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Upload Option Entry File", type=["csv", "xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    # ---------------- LOAD FILES ----------------
    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("Files loaded!")

    st.write("Candidates:", len(cand))
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

    # Mandatory fields
    if "Category" not in cand.columns:
        cand["Category"] = "NA"

    cand["Category"] = cand["Category"].astype(str).str.upper().fillna("NA")

    # Safe handling of missing columns
    if "CheckMinority" not in cand.columns:
        cand["CheckMinority"] = ""
    if "Status" not in cand.columns:
        cand["Status"] = ""

    cand["CheckMinority"] = cand["CheckMinority"].astype(str).str.upper()
    cand["Status"] = cand["Status"].astype(str).str.upper()

    # Remove Status=S and PRank=0
    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")].copy()
    cand = cand.sort_values("PRank").reset_index(drop=True)

    # ----------------------------------------------------------
    # CLEAN OPTIONS
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

    # Build index for fast lookup
    opts_by_roll = defaultdict(list)
    for row in opts.itertuples(index=False):
        opts_by_roll[row.RollNo].append(row)

    # ----------------------------------------------------------
    # CLEAN & INDEX SEAT MATRIX
    # ----------------------------------------------------------
    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}   # (typ, course, college, category) -> seats
    seat_groups = defaultdict(set)  # (typ, course, college) -> categories

    for r in seats.itertuples(index=False):
        key = (r.typ, r.course, r.college, r.category)
        seat_map[key] = seat_map.get(key, 0) + int(r.SEAT)

        tcc = (r.typ, r.course, r.college)
        seat_groups[tcc].add(r.category)

    # ----------------------------------------------------------
    # RUN ALLOTMENT (FAST)
    # ----------------------------------------------------------
    allotments = []

    for c in cand.itertuples(index=False):

        roll = c.RollNo
        cand_cat = c.Category
        hq = c.HQ_Rank
        mq = c.MQ_Rank
        iq = c.IQ_Rank
        strank = c.STRank
        minority = (c.CheckMinority == "Y")

        myopts = opts_by_roll.get(roll)
        if not myopts:
            continue

        for op in myopts:

            dec = decode_opt(op.Optn)
            if not dec:
                continue

            prog = dec["prog"]
            typ = dec["typ"]
            course = dec["course"]
            college = dec["college"]
            flag = dec["flag"]

            # Service quota
            if flag == "M" and strank <= 0:
                continue

            # Minority quota
            if flag == "Y" and not minority:
                continue

            tcc_key = (typ, course, college)
            if tcc_key not in seat_groups:
                continue

            available_cats = seat_groups[tcc_key]

            # Priority order
            priority = []

            if cand_cat not in ("NA", "NULL", "") and cand_cat in available_cats:
                priority.append(cand_cat)

            if "HQ" in available_cats and hq > 0:
                priority.append("HQ")
            if "MQ" in available_cats and mq > 0:
                priority.append("MQ")
            if "IQ" in available_cats and iq > 0:
                priority.append("IQ")

            if "SM" in available_cats:
                priority.append("SM")

            chosen = None

            for sc in priority:

                key = (typ, course, college, sc)

                if seat_map.get(key, 0) <= 0:
                    continue

                if not eligible_category(sc, cand_cat):
                    continue

                chosen = (sc, key)
                break

            if not chosen:
                continue

            seat_cat, key = chosen
            seat_map[key] -= 1

            allot_code = make_allot_code(prog, typ, course, college, seat_cat)

            allotments.append({
                "RollNo": roll,
                "OPNO": op.OPNO,
                "AllotCode": allot_code,
                "College": college,
                "Course": course,
                "SeatCategory": seat_cat
            })

            break  # move to next candidate

    # ----------------------------------------------------------
    # OUTPUT
    # ----------------------------------------------------------
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Completed")
    st.write("Total Allotted:", len(result))
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
