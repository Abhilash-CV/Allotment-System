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

    # Quota categories – controlled by ranks, not community
    if seat_cat in ("HQ", "MQ", "IQ"):
        return True

    # SM open to all
    if seat_cat == "SM":
        return True

    # Special categories
    if seat_cat in ("PD", "CD", "AC", "MM", "NR", "NC", "NM"):
        return True

    # Community seats
    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


# ==========================================================
# Special rules – NRI / Minority / PD / CD / AC / MM / NM
# ==========================================================
def passes_special_rules(seat_cat, flag, c_row):

    seat_cat = str(seat_cat).upper().strip()
    flag = str(flag).upper().strip()

    cand_nri = str(getattr(c_row, "NRI", "")).upper().strip()
    cand_min = str(getattr(c_row, "Minority", "")).upper().strip()
    cand_sp3 = str(getattr(c_row, "Special3", "")).upper().strip()
    cand_cat = str(getattr(c_row, "Category", "")).upper().strip()

    # ---- NR seat ----
    # Seat = NR, Flag = R, Candidate = NRI-NR or NR
    if seat_cat == "NR":
        valid_nri_nr = {"NR", "NRI-NR"}
        if flag != "R" or cand_nri not in valid_nri_nr:
            return False

    # ---- NC seat ----
    # Seat = NC, Flag = R, Candidate = NRNC
    if seat_cat == "NC":
        valid_nri_nc = {"NRNC"}
        if flag != "R" or cand_nri not in valid_nri_nc:
            return False

    # ---- NM seat ----
    # Seat = NM, Flag = R, Candidate = NRNM
    if seat_cat == "NM":
        valid_nri_nm = {"NRNM"}
        if flag != "R" or cand_nri not in valid_nri_nm:
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
# Decode 8-char PG option
# ==========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],
        "typ": opt[1],
        "course": opt[2:4],
        "college": opt[4:7],
        "flag": opt[7],
    }


# ==========================================================
# Allotment Code
# ==========================================================
def make_allot_code(prog, typ, course, college, category):
    c2 = category[:2].upper()
    return f"{prog}{typ}{course}{college}{c2}{c2}"


# ==========================================================
# MAIN STREAMLIT APP
# ==========================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Allotment – Full Corrected Version")

    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix File", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    # ---------- LOAD ----------
    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("Files loaded successfully!")

    # ----------------------------------------------------------
    # CLEAN CANDIDATE DATA
    # ----------------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["PRank"]  = pd.to_numeric(cand["PRank"], errors="coerce").fillna(0).astype(int)

    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank", "STRank"]:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    for col in ["Category", "NRI", "Minority", "Special3", "Status"]:
        if col not in cand.columns:
            cand[col] = ""
        cand[col] = cand[col].astype(str).str.upper().fillna("")

    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")]
    cand = cand.sort_values("PRank").reset_index(drop=True)

    # ----------------------------------------------------------
    # CLEAN OPTION DATA
    # ----------------------------------------------------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ]

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo", "OPNO"])

    # Group options
    opts_by_roll = defaultdict(list)
    for row in opts.itertuples(index=False):
        opts_by_roll[row.RollNo].append(row)

    # ----------------------------------------------------------
    # CLEAN SEAT MATRIX
    # ----------------------------------------------------------
    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}
    seat_groups = defaultdict(set)

    for r in seats.itertuples(index=False):
        key = (r.grp, r.typ, r.course, r.college, r.category)
        seat_map[key] = seat_map.get(key, 0) + int(r.SEAT)

        gkey = (r.grp, r.typ, r.course, r.college)
        seat_groups[gkey].add(r.category)

    # Seat summary
    seat_summary = (
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

            base_key = (grp, typ, course, college)
            if base_key not in seat_groups:
                continue

            available = seat_groups[base_key]

            priority = []

            # 1. Exact community
            if c.Category not in ("NA", "") and c.Category in available:
                priority.append(c.Category)

            # 2. Quotas
            if "HQ" in available and c.HQ_Rank > 0:
                priority.append("HQ")
            if "MQ" in available and c.MQ_Rank > 0:
                priority.append("MQ")
            if "IQ" in available and c.IQ_Rank > 0:
                priority.append("IQ")

            # 3. Special categories
            special_order = ["PD", "CD", "AC", "MM", "NR", "NC", "NM"]
            for sc in special_order:
                if sc not in available:
                    continue
                if not eligible_category(sc, c.Category):
                    continue
                if not passes_special_rules(sc, flag, c):
                    continue
                priority.append(sc)

            # 4. SM last
            if "SM" in available:
                priority.append("SM")

            # Choose seat
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
    # OUTPUT RESULTS
    # ----------------------------------------------------------
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Result")
    st.write("Total Allotted:", len(result))
    st.dataframe(result)

    # Admitted summary
    if not result.empty:
        admitted = (
            result.groupby(["College", "Course", "SeatCategory"], as_index=False)
            .size()
            .rename(columns={
                "College": "CollegeCode",
                "Course": "CourseCode",
                "SeatCategory": "CategoryCode",
                "size": "AdmittedTotal",
            })
        )
    else:
        admitted = pd.DataFrame(columns=["CollegeCode", "CourseCode", "CategoryCode", "AdmittedTotal"])

    detail = seat_summary.merge(
        admitted,
        on=["CollegeCode", "CourseCode", "CategoryCode"],
        how="left",
    )
    detail["AdmittedTotal"] = detail["AdmittedTotal"].fillna(0).astype(int)
    detail["Unallotted"] = detail["SeatTotal"] - detail["AdmittedTotal"]

    st.subheader("📊 Detailed Seat Report")
    st.dataframe(detail)

    # Remaining seats
    rem = []
    for (grp, typ, course, college, cat), rems in seat_map.items():
        if rems > 0:
            rem.append({
                "grp": grp,
                "typ": typ,
                "CollegeCode": college,
                "CourseCode": course,
                "CategoryCode": cat,
                "RemainingSeat": rems,
            })

    rem_df = pd.DataFrame(rem)
    st.subheader("🪑 Remaining Seat Summary")
    st.dataframe(rem_df)

    # Downloads
    b1 = BytesIO()
    result.to_csv(b1, index=False)
    b1.seek(0)
    st.download_button("⬇ Download Allotment Result CSV", b1, "PG_Allotment_Result.csv")

    b2 = BytesIO()
    detail.to_csv(b2, index=False)
    b2.seek(0)
    st.download_button("⬇ Download Detailed Seat Report CSV", b2, "PG_Detail_Report.csv")
