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
# Basic category eligibility (generic rules)
# ==========================================================
def eligible_category(seat_cat, cand_cat):
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NULL", "NA"):
        cand_cat = "NA"

    # Quota categories – controlled by ranks, not community
    if seat_cat in ("HQ", "MQ", "IQ"):
        return True

    # SM is open to all
    if seat_cat == "SM":
        return True

    # Special categories – further filtered by passes_special_rules
    if seat_cat in ("PD", "CD", "AC", "MM", "NR", "NC"):
        return True

    # NA candidate cannot take community seats
    if cand_cat == "NA":
        return False

    # Normal community seat
    return seat_cat == cand_cat


# ==========================================================
# Special rules – NRI / Minority / PD / CD etc.
# ==========================================================
def passes_special_rules(seat_cat, flag, c_row):
    """
    c_row is a row from candidates (itertuples), with fields:
    NRI, Minority, Special3, Category, etc.

    Explicit cases (from your conditions):

    Case 1:
        Option last digit = R
        Seat = NR
        Candidate.NRI = NR

    Case 2:
        Candidate.Minority = AC
        Seat = AC
        Option last digit = Y

    Case 3:
        Candidate.Minority = MM
        Seat = MM
        Option last digit = Y

    Case 4:
        Option last digit = R
        Seat = NC
        Candidate.NRI = NRNC

    Case 5:
        Seat = PD
        Candidate.Special3 = PD

    Case 6:
        Seat = CD
        Candidate.Category = SC AND Candidate.Special3 = PD
    """

    seat_cat = str(seat_cat).upper().strip()
    flag = str(flag).upper().strip()

    # Extract candidate fields safely
    cand_nri = str(getattr(c_row, "NRI", "")).upper().strip()
    cand_min = str(getattr(c_row, "Minority", "")).upper().strip()
    cand_sp3 = str(getattr(c_row, "Special3", "")).upper().strip()
    cand_cat = str(getattr(c_row, "Category", "")).upper().strip()

    # ---- Case 1: NRI seat NR ----
    # Option last digit R, Seat = NR, Candidate NRI = NR
    if seat_cat == "NR":
        if flag != "R" or cand_nri != "NR":
            return False

    # ---- Case 4: NRI seat NC ----
    # Option last digit R, Seat = NC, Candidate NRI = NRNC
    if seat_cat == "NC":
        if flag != "R" or cand_nri != "NRNC":
            return False

    # ---- Case 2: Minority AC ----
    # Candidate.Minority = AC, Seat = AC, Option last digit Y
    if seat_cat == "AC":
        if flag != "Y":
            return False
        if cand_min != "AC":
            return False

    # ---- Case 3: Minority MM ----
    # Candidate.Minority = MM, Seat = MM, Option last digit Y
    if seat_cat == "MM":
        if flag != "Y" or cand_min != "MM":
            return False

    # ---- Case 5: PD ----
    # Seat = PD, Candidate.Special3 = PD
    if seat_cat == "PD":
        if cand_sp3 != "PD":
            return False

    # ---- Case 6: CD ----
    # Seat = CD, Candidate.Category = SC and Special3 = PD
    if seat_cat == "CD":
        if not (cand_cat == "SC" and cand_sp3 == "PD"):
            return False

    # For all other categories – no special restriction
    return True


# ==========================================================
# Decode 8-char PG option
# ==========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],        # M (PGM) / S (PGS) etc.
        "typ": opt[1],         # G/S
        "course": opt[2:4],    # 2 letters
        "college": opt[4:7],   # 3 letters
        "flag": opt[7],        # M / Y / R / N, etc.
    }


# ==========================================================
# 11-char Allotment Code: MG + CC + COL + CATCAT
# ==========================================================
def make_allot_code(prog, typ, course, college, category):
    cat2 = category[:2].upper()
    cat4 = cat2 + cat2
    return f"{prog}{typ}{course}{college}{cat4}"


# ==========================================================
# MAIN STREAMLIT APP FUNCTION
# ==========================================================
def pg_med_allotment():
    st.title("🩺 PG Medical Allotment – Special Rules + Detail Report")

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

    # ---------- INPUT SUMMARY ----------
    st.write("🔢 Candidates:", len(cand))
    st.write("🗂 Options:", len(opts))
    st.write("📦 Seat Rows:", len(seats))
    if "SEAT" in seats.columns:
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

    # Ensure special columns exist
    if "NRI" not in cand.columns:
        cand["NRI"] = ""
    if "Minority" not in cand.columns:
        cand["Minority"] = ""
    if "Special3" not in cand.columns:
        cand["Special3"] = ""
    if "Status" not in cand.columns:
        cand["Status"] = ""

    cand["NRI"] = cand["NRI"].astype(str).str.upper()
    cand["Minority"] = cand["Minority"].astype(str).str.upper()
    cand["Special3"] = cand["Special3"].astype(str).str.upper()
    cand["Status"] = cand["Status"].astype(str).str.upper()

    # Remove ineligible candidates
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

    # Index: RollNo -> list of options
    opts_by_roll = defaultdict(list)
    for row in opts.itertuples(index=False):
        opts_by_roll[row.RollNo].append(row)

    # ----------------------------------------------------------
    # CLEAN SEAT MATRIX
    # ----------------------------------------------------------
    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    # seat_map: (grp, typ, course, college, category) -> remaining seats
    seat_map = {}
    # seat_groups: (grp, typ, course, college) -> set(categories)
    seat_groups = defaultdict(set)

    for r in seats.itertuples(index=False):
        key = (r.grp, r.typ, r.course, r.college, r.category)
        seat_map[key] = seat_map.get(key, 0) + int(r.SEAT)

        gkey = (r.grp, r.typ, r.course, r.college)
        seat_groups[gkey].add(r.category)

    # Also keep original seat summary for detail report
    seat_summary = (
        seats.groupby(["college", "course", "typ", "category"], as_index=False)["SEAT"]
        .sum()
        .rename(
            columns={
                "college": "CollegeCode",
                "course": "CourseCode",
                "typ": "CollegeType",
                "category": "CategoryCode",
                "SEAT": "SeatTotal",
            }
        )
    )

    # ----------------------------------------------------------
    # RUN ALLOTMENT
    # ----------------------------------------------------------
    allotments = []

    for c in cand.itertuples(index=False):
        roll = c.RollNo
        cand_cat = c.Category
        hq = c.HQ_Rank
        mq = c.MQ_Rank
        iq = c.IQ_Rank

        myopts = opts_by_roll.get(roll)
        if not myopts:
            continue

        for op in myopts:
            dec = decode_opt(op.Optn)
            if not dec:
                continue

            prog = dec["prog"]      # M
            typ = dec["typ"]        # G/S
            course = dec["course"]
            college = dec["college"]
            flag = dec["flag"].upper()

            # Map prog to seat grp: M -> PGM, S -> PGS
            grp = "PG" + prog

            base_key = (grp, typ, course, college)
            if base_key not in seat_groups:
                continue

            available_cats = seat_groups[base_key]

            # Build priority order
            priority = []

            # 1. exact community if present
            if cand_cat not in ("NA", "NULL", "") and cand_cat in available_cats:
                priority.append(cand_cat)

            # 2. HQ / MQ / IQ (quota ranks)
            if "HQ" in available_cats and hq > 0:
                priority.append("HQ")
            if "MQ" in available_cats and mq > 0:
                priority.append("MQ")
            if "IQ" in available_cats and iq > 0:
                priority.append("IQ")

            # 3. special categories (with candidate-based filtering)
            special_order = ["PD", "CD", "AC", "MM", "NR", "NC"]
            for sc in special_order:
                if sc not in available_cats:
                    continue
                if sc in priority:
                    continue
                # ensure candidate is eligible + passes special rule
                if not eligible_category(sc, cand_cat):
                    continue
                if not passes_special_rules(sc, flag, c):
                    continue
                priority.append(sc)

            # 4. SM last (open seat)
            if "SM" in available_cats and "SM" not in priority:
                if eligible_category("SM", cand_cat) and passes_special_rules("SM", flag, c):
                    priority.append("SM")

            chosen_cat = None
            chosen_key = None

            for sc in priority:
                skey = (grp, typ, course, college, sc)

                # no seats left
                if seat_map.get(skey, 0) <= 0:
                    continue

                # basic + special eligibility (redundant but safe)
                if not eligible_category(sc, cand_cat):
                    continue
                if not passes_special_rules(sc, flag, c):
                    continue

                chosen_cat = sc
                chosen_key = skey
                break

            if not chosen_cat:
                continue  # try next option

            # Deduct seat
            seat_map[chosen_key] -= 1

            # Allot code
            allot_code = make_allot_code(prog, typ, course, college, chosen_cat)

            allotments.append(
                {
                    "RollNo": roll,
                    "OPNO": op.OPNO,
                    "AllotCode": allot_code,
                    "College": college,
                    "Course": course,
                    "SeatCategory": chosen_cat,
                }
            )

            break  # stop at first successful allotment

    # ----------------------------------------------------------
    # ALLOTMENT RESULT
    # ----------------------------------------------------------
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Result")
    st.write("Total Allotted Candidates:", len(result))
    st.dataframe(result)

    # ----------------------------------------------------------
    # DETAILED SEAT REPORT (like manual)
    # ----------------------------------------------------------
    # admitted summary: count of allotments for each (college, course, category)
    if not result.empty:
        admitted = (
            result.groupby(["College", "Course", "SeatCategory"], as_index=False)
            .size()
            .rename(
                columns={
                    "College": "CollegeCode",
                    "Course": "CourseCode",
                    "SeatCategory": "CategoryCode",
                    "size": "AdmittedTotal",
                }
            )
        )
    else:
        admitted = pd.DataFrame(
            columns=["CollegeCode", "CourseCode", "CategoryCode", "AdmittedTotal"]
        )

    detail = seat_summary.merge(
        admitted,
        on=["CollegeCode", "CourseCode", "CategoryCode"],
        how="left",
    )
    detail["AdmittedTotal"] = detail["AdmittedTotal"].fillna(0).astype(int)
    detail["Unallotted"] = detail["SeatTotal"] - detail["AdmittedTotal"]

    st.subheader("📊 Detailed Seat Report (Manual Style)")
    st.dataframe(detail)

    # ----------------------------------------------------------
    # REMAINING SEAT DIAGNOSTICS
    # ----------------------------------------------------------
    rem_rows = []
    for (grp, typ, course, college, cat), rem in seat_map.items():
        if rem > 0:
            rem_rows.append(
                {
                    "grp": grp,
                    "typ": typ,
                    "CollegeCode": college,
                    "CourseCode": course,
                    "CategoryCode": cat,
                    "RemainingSeat": rem,
                }
            )

    rem_df = pd.DataFrame(rem_rows)
    st.subheader("🪑 Remaining Seat Summary (After Allotment)")
    if rem_df.empty:
        st.success("All seats fully utilized.")
    else:
        st.write("Total Remaining Seats:", int(rem_df["RemainingSeat"].sum()))
        st.dataframe(rem_df)

    # ----------------------------------------------------------
    # DOWNLOADS
    # ----------------------------------------------------------
    # Allotment result
    buf1 = BytesIO()
    result.to_csv(buf1, index=False)
    buf1.seek(0)
    st.download_button(
        "⬇ Download Allotment Result CSV",
        buf1,
        "PG_Allotment_Result.csv",
        "text/csv",
    )

    # Detailed seat report
    buf2 = BytesIO()
    detail.to_csv(buf2, index=False)
    buf2.seek(0)
    st.download_button(
        "⬇ Download Detailed Seat Report CSV",
        buf2,
        "PG_Detailed_Seat_Report.csv",
        "text/csv",
    )
