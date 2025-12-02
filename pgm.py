import streamlit as st
import pandas as pd
from io import BytesIO
from collections import defaultdict


# ==========================================================
# Generic reader for CSV / Excel
# ==========================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# ==========================================================
# Basic category eligibility
# ==========================================================
def eligible_category(seat_cat, cand_cat):
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NULL", "NA"):
        cand_cat = "NA"

    # Quota seats always allowed
    if seat_cat in ("HQ", "MQ", "IQ"):
        return True

    # SM open to all
    if seat_cat == "SM":
        return True

    # Special categories - eligibility checked separately
    if seat_cat in ("PD", "CD", "AC", "MM", "NR", "NC", "NM"):
        return True

    # Normal community seats
    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


# ==========================================================
# Special category rule validation
# ==========================================================
def passes_special_rules(seat_cat, flag, c):

    seat_cat = str(seat_cat).upper().strip()
    flag = str(flag).upper().strip()

    cand_nri = str(getattr(c, "NRI", "")).upper().strip()
    cand_min = str(getattr(c, "Minority", "")).upper().strip()
    cand_sp3 = str(getattr(c, "Special3", "")).upper().strip()
    cand_cat = str(getattr(c, "Category", "")).upper().strip()

    # ---- NR seat ----
    if seat_cat == "NR":
        valid = {"NR", "NRI-NR"}
        if flag != "R" or cand_nri not in valid:
            return False

    # ---- NC seat ----
    if seat_cat == "NC":
        valid = {"NRNC"}
        if flag != "R" or cand_nri not in valid:
            return False

    # ---- NM seat ----
    if seat_cat == "NM":
        valid = {"NRNM"}
        if flag != "R" or cand_nri not in valid:
            return False

    # ---- AC ----
    if seat_cat == "AC":
        if flag != "Y" or cand_min != "AC":
            return False

    # ---- MM ----
    if seat_cat == "MM":
        if flag != "Y" or cand_min != "MM":
            return False

    # ---- PD ----
    if seat_cat == "PD":
        if cand_sp3 != "PD":
            return False

    # ---- CD ----
    if seat_cat == "CD":
        if not (cand_cat == "SC" and cand_sp3 == "PD"):
            return False

    return True


# ==========================================================
# Decode option
# ==========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],        # M
        "typ": opt[1],         # G/S
        "course": opt[2:4],    # 2 chars
        "college": opt[4:7],   # 3 chars
        "flag": opt[7],        # M/Y/R/N
    }


# ==========================================================
# Build Allotment Code
# ==========================================================
def make_allot_code(prog, typ, course, college, category):
    c2 = category[:2].upper()
    return f"{prog}{typ}{course}{college}{c2}{c2}"


# ==========================================================
# MAIN APP
# ==========================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Allotment – FINAL FIXED VERSION")

    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix File", type=["csv", "xlsx"])
    opt_file = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("Files loaded successfully!")

    # ----------------------------------------------------------
    # CLEAN CANDIDATES
    # ----------------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["PRank"] = pd.to_numeric(cand["PRank"], errors="coerce").fillna(0).astype(int)

    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank"]:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    for col in ["Category", "NRI", "Minority", "Special3", "Status"]:
        if col not in cand.columns:
            cand[col] = ""
        cand[col] = cand[col].astype(str).str.upper()

    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")]
    cand = cand.sort_values("PRank").reset_index(drop=True)

    # ----------------------------------------------------------
    # CLEAN OPTIONS
    # ----------------------------------------------------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"] = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ]

    opts["Optn"] = opts["Optn"].astype(str).str.upper()
    opts = opts.sort_values(["RollNo", "OPNO"])

    opts_by_roll = defaultdict(list)
    for row in opts.itertuples(index=False):
        opts_by_roll[row.RollNo].append(row)

    # ----------------------------------------------------------
    # CLEAN SEAT MATRIX
    # ----------------------------------------------------------
    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}
    seat_groups = defaultdict(set)

    for r in seats.itertuples(index=False):
        key = (r.grp, r.typ, r.course, r.college, r.category)
        seat_map[key] = seat_map.get(key, 0) + int(r.SEAT)

        gkey = (r.grp, r.typ, r.course, r.college)
        seat_groups[gkey].add(r.category)

    # ----------------------------------------------------------
    # RUN ALLOTMENT
    # ----------------------------------------------------------
    allotments = []

    for c in cand.itertuples(index=False):

        myopts = opts_by_roll.get(c.RollNo)
        if not myopts:
            continue

        for op in myopts:

            dec = decode_opt(op.Optn)
            if not dec:
                continue

            grp = "PG" + dec["prog"]
            typ = dec["typ"]
            course = dec["course"]
            college = dec["college"]
            flag = dec["flag"]

            base = (grp, typ, course, college)
            if base not in seat_groups:
                continue

            available = seat_groups[base]

            # --------------------------------------------------
            # PRIORITY ORDER (FINAL CORRECTED VERSION)
            # --------------------------------------------------
            priority = []

            # 1. Community
            if c.Category not in ("NA", "") and c.Category in available:
                priority.append(c.Category)

            # 2. HQ / MQ / IQ (IQ MUST BE BEFORE SPECIAL CATEGORIES)
            if "HQ" in available and c.HQ_Rank > 0:
                priority.append("HQ")
            if "MQ" in available and c.MQ_Rank > 0:
                priority.append("MQ")
            if "IQ" in available and c.IQ_Rank > 0:
                priority.append("IQ")

            # 3. Special categories
            for sc in ["PD", "CD", "AC", "MM", "NR", "NC", "NM"]:
                if sc not in available:
                    continue
                if not passes_special_rules(sc, flag, c):
                    continue
                priority.append(sc)

            # 4. SM last
            if "SM" in available:
                priority.append("SM")

            # --------------------------------------------------
            # TRY ALLOT
            # --------------------------------------------------
            chosen = None
            chosen_key = None

            for sc in priority:
                skey = (grp, typ, course, college, sc)
                if seat_map.get(skey, 0) <= 0:
                    continue
                if not eligible_category(sc, c.Category):
                    continue
                if not passes_special_rules(sc, flag, c):
                    continue

                chosen = sc
                chosen_key = skey
                break

            if not chosen:
                continue

            # Deduct seat
            seat_map[chosen_key] -= 1

            # Save allotment
            allotments.append({
                "RollNo": c.RollNo,
                "OPNO": op.OPNO,
                "College": college,
                "Course": course,
                "SeatCategory": chosen,
                "AllotCode": make_allot_code(dec["prog"], typ, course, college, chosen),
            })

            break

    # ----------------------------------------------------------
    # OUTPUT
    # ----------------------------------------------------------
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Result")
    st.write("Total Allotted:", len(result))
    st.dataframe(result)

    # Detailed report
    admitted = (
        result.groupby(["College", "Course", "SeatCategory"], as_index=False)
        .size()
        .rename(columns={
            "College": "CollegeCode",
            "Course": "CourseCode",
            "SeatCategory": "CategoryCode",
            "size": "AdmittedTotal",
        })
    ) if not result.empty else pd.DataFrame(columns=[
        "CollegeCode", "CourseCode", "CategoryCode", "AdmittedTotal"
    ])

    seat_grouped = (
        seats.groupby(["college", "course", "typ", "category"], as_index=False)["SEAT"]
        .sum()
        .rename(columns={
            "college": "CollegeCode",
            "course": "CourseCode",
            "typ": "CollegeType",
            "category": "CategoryCode",
            "SEAT": "SeatTotal",
        })
    )

    detail = seat_grouped.merge(
        admitted,
        on=["CollegeCode", "CourseCode", "CategoryCode"],
        how="left"
    )
    detail["AdmittedTotal"] = detail["AdmittedTotal"].fillna(0).astype(int)
    detail["Unallotted"] = detail["SeatTotal"] - detail["AdmittedTotal"]

    st.subheader("📊 Detailed Seat Report")
    st.dataframe(detail)

    # Remaining seats
    rem_rows = []
    for (grp, typ, course, college, cat), rem in seat_map.items():
        if rem > 0:
            rem_rows.append({
                "grp": grp,
                "typ": typ,
                "CollegeCode": college,
                "CourseCode": course,
                "CategoryCode": cat,
                "RemainingSeat": rem,
            })

    st.subheader("🪑 Remaining Seats")
    st.dataframe(pd.DataFrame(rem_rows))

    # Downloads
    buf1 = BytesIO()
    result.to_csv(buf1, index=False)
    buf1.seek(0)
    st.download_button("⬇ Download Allotment CSV", buf1, "Allotment.csv")

    buf2 = BytesIO()
    detail.to_csv(buf2, index=False)
    buf2.seek(0)
    st.download_button("⬇ Download Detailed Seat Report", buf2, "DetailReport.csv")
