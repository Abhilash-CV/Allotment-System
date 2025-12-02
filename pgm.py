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

    # Quota categories based on rank only
    if seat_cat in ("HQ", "MQ", "IQ"):
        return True

    # SM open to all
    if seat_cat == "SM":
        return True

    # NA candidates only eligible for SM
    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


# ==========================================================
# Decode PG Option Format
# Optn = M G CC CCC F
#        0 1 2  4  7
# ==========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None

    return {
        "prog": opt[0],        # M
        "typ": opt[1],         # G or S
        "course": opt[2:4],    # CC (2 chars)
        "college": opt[4:7],   # COL (3 chars)
        "flag": opt[7]         # M/Y/N
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

    st.title("🩺 PG Medical Allotment (11-digit Format, Optimized + Diagnostics)")

    cand_file = st.file_uploader("1️⃣ Upload Candidates File", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Upload Seat Matrix File", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Upload Option Entry File", type=["csv", "xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    # ---------------- LOAD FILES ----------------
    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("Files loaded successfully!")

    # ---------- DIAGNOSTICS ----------
    st.write("🔢 Candidates:", len(cand))
    st.write("🗂 Options:", len(opts))
    st.write("📦 Seat Rows:", len(seats))
    st.write("🪑 Total SEAT Capacity:", int(seats["SEAT"].fillna(0).sum()))

    # ----------------------------------------------------------
    # CLEAN CANDIDATES
    # ----------------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["PRank"]  = pd.to_numeric(cand["PRank"], errors="coerce").fillna(0).astype(int)

    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank", "STRank"]:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

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

    seat_map = {}   # (grp, typ, course, college, category) -> seats
    seat_groups = defaultdict(set)  # (grp, typ, course, college) -> categories

    for r in seats.itertuples(index=False):
        key = (r.grp, r.typ, r.course, r.college, r.category)
        seat_map[key] = seat_map.get(key, 0) + int(r.SEAT)

        gkey = (r.grp, r.typ, r.course, r.college)
        seat_groups[gkey].add(r.category)

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

            prog = dec["prog"]       # M
            typ = dec["typ"]         # G/S
            course = dec["course"]   # CC
            college = dec["college"] # COL3
            flag = dec["flag"]       # M/Y/N

            # Map prog to seat grp (PGM and PGS only)
            grp = "PG" + prog    # M -> PGM, S -> PGS

            # Service quota
            if flag == "M" and strank <= 0:
                continue

            # Minority quota
            if flag == "Y" and not minority:
                continue

            seat_key_base = (grp, typ, course, college)
            if seat_key_base not in seat_groups:
                continue

            available_cats = seat_groups[seat_key_base]

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

            chosen_cat = None
            chosen_key = None

            for sc in priority:
                skey = (grp, typ, course, college, sc)

                if seat_map.get(skey, 0) <= 0:
                    continue

                if not eligible_category(sc, cand_cat):
                    continue

                chosen_cat = sc
                chosen_key = skey
                break

            if not chosen_cat:
                continue

            # Deduct seat
            seat_map[chosen_key] -= 1

            allot_code = make_allot_code(prog, typ, course, college, chosen_cat)

            allotments.append({
                "RollNo": roll,
                "OPNO": op.OPNO,
                "AllotCode": allot_code,
                "College": college,
                "Course": course,
                "SeatCategory": chosen_cat
            })

            break  # move to next candidate

    # ----------------------------------------------------------
    # OUTPUT RESULT
    # ----------------------------------------------------------
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Completed")
    st.write("🧍 Total Allotted Candidates:", len(result))
    st.dataframe(result)

    # ----------------------------------------------------------
    # REMAINING SEAT DIAGNOSTICS
    # ----------------------------------------------------------
    rem = []
    for (grp, typ, course, college, cat), rem_count in seat_map.items():
        if rem_count > 0:
            rem.append({
                "grp": grp,
                "typ": typ,
                "course": course,
                "college": college,
                "category": cat,
                "RemainingSeat": rem_count
            })

    rem_df = pd.DataFrame(rem)

    st.subheader("🪑 Remaining Seat Summary (After Allotment)")
    if rem_df.empty:
        st.success("All seats fully utilized.")
    else:
        st.write("Total Remaining Seats:", int(rem_df["RemainingSeat"].sum()))
        st.dataframe(rem_df)

    # ----------------------------------------------------------
    # DOWNLOAD RESULT
    # ----------------------------------------------------------
    buf = BytesIO()
    result.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download PG Allotment Result",
        buf,
        "PG_Allotment.csv",
        "text/csv"
    )
