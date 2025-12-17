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

    # Quota seats – allowed for everyone (subject to having rank)
    if seat_cat in ("HQ", "MQ", "IQ"):
        return True

    # Open merit – allowed for everyone
    if seat_cat == "SM":
        return True

    # Special seats – detailed checks in passes_special_rules
    if seat_cat in ("PD", "CD", "AC", "MM", "NR", "NC", "NM"):
        return True

    # Community seats (BH/EZ/MU/SC/ST/OBC/...)
    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


# ==========================================================
# Special rules – NRI / Minority / PD / CD / etc.
# ==========================================================
def passes_special_rules(seat_cat, flag, c):
    seat_cat = str(seat_cat).upper().strip()
    flag = str(flag).upper().strip()

    cand_nri = str(getattr(c, "NRI", "")).upper().strip()
    cand_min = str(getattr(c, "Minority", "")).upper().strip()
    cand_sp3 = str(getattr(c, "Special3", "")).upper().strip()
    cand_cat = str(getattr(c, "Category", "")).upper().strip()

    # ---- NR seat ----
    # Seat = NR, flag = R, NRI in {NR, NRI-NR}
    if seat_cat == "NR":
        if flag != "R" or cand_nri not in {"NR", "NRI-NR"}:
            return False

    # ---- NC seat ----
    # Seat = NC, flag = R, NRI = NRNC
    if seat_cat == "NC":
        if flag != "R" or cand_nri not in {"NRNC"}:
            return False

    # ---- NM seat ----
    # Seat = NM, flag = R, NRI = NRNM
    if seat_cat == "NM":
        if flag != "R" or cand_nri not in {"NRNM"}:
            return False

    # ---- AC minority ----
    if seat_cat == "AC":
        if flag != "Y" or cand_min != "AC":
            return False

    # ---- MM minority ----
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

    # No extra restriction
    return True


# ==========================================================
# Decode 8-char option
# ==========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],        # M
        "typ": opt[1],         # G/S
        "course": opt[2:4],    # 2 letters
        "college": opt[4:7],   # 3 letters
        "flag": opt[7],        # G/M/Y/R/N...
    }


# ==========================================================
# Build Allotment Code: MG + CC + COL + CATCAT
# ==========================================================
def make_allot_code(prog, typ, course, college, category):
    c2 = category[:2].upper()
    return f"{prog}{typ}{course}{college}{c2}{c2}"


# ==========================================================
# MAIN APP
# ==========================================================
def pg_med_allotment():
    st.title("🩺 PG Medical Allotment – PRank Global, HQ/MQ/IQ Inside Option")

    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix File", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"])

    debug_enabled = st.checkbox("🔍 Enable debug for a specific candidate")
    debug_roll = None
    if debug_enabled:
        debug_roll = st.number_input("Enter Roll Number for debug", min_value=0, step=1, value=0)
        if debug_roll == 0:
            debug_enabled = False

    if not (cand_file and seat_file and opt_file):
        return

    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts  = read_any(opt_file)

    # ----------------------------------------------------------
    # CLEAN CANDIDATES
    # ----------------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["PRank"]  = pd.to_numeric(cand["PRank"], errors="coerce").fillna(0).astype(int)

    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank"]:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    for col in ["Category", "NRI", "Minority", "Special3", "Status"]:
        if col not in cand.columns:
            cand[col] = ""
        cand[col] = cand[col].astype(str).str.upper()

    # remove resigned / ineligible
    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")].copy()

    # ---- GLOBAL ORDER = PRank ONLY ----
    cand = cand.sort_values("PRank").reset_index(drop=True)
    cand_rows = list(cand.itertuples(index=False))

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
    opts = opts.sort_values(["RollNo", "OPNO"])

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

    # seat summary for report
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

    # ----------------------------------------------------------
    # ALLOTMENT LOGIC
    # ----------------------------------------------------------
    allotments = []
    debug_logs = []

    def add_priority(priority_list, label):
        if label not in priority_list:
            priority_list.append(label)

    for c in cand_rows:

        is_debug = debug_enabled and (int(c.RollNo) == int(debug_roll))
        if is_debug:
            debug_logs.append(f"=== Candidate {c.RollNo} (PRank={c.PRank}, Cat={c.Category}, HQ={c.HQ_Rank}, MQ={c.MQ_Rank}, IQ={c.IQ_Rank}) ===")

        myopts = opts_by_roll.get(c.RollNo)
        if not myopts:
            if is_debug:
                debug_logs.append("No valid options for this candidate.")
            continue

        allotted_here = False

        for op in myopts:

            dec = decode_opt(op.Optn)
            if not dec:
                if is_debug:
                    debug_logs.append(f"OPNO {op.OPNO}: Invalid option format {op.Optn}")
                continue

            grp     = "PG" + dec["prog"]
            typ     = dec["typ"]
            course  = dec["course"]
            college = dec["college"]
            flag    = dec["flag"].upper()

            base = (grp, typ, course, college)
            if base not in seat_groups:
                if is_debug:
                    debug_logs.append(f"OPNO {op.OPNO}: No seat group for {grp}-{typ}-{course}-{college}")
                continue

            available = seat_groups[base]
            priority = []

            if is_debug:
                debug_logs.append(f"OPNO {op.OPNO}: Optn={op.Optn}, flag={flag}, available_cats={sorted(list(available))}")

            # ---------- PRIORITY INSIDE ONE OPTION ----------

            # If flag = M -> HQ → MQ → IQ first (within this option)
            if flag == "M":
                if "HQ" in available and c.HQ_Rank > 0:
                    add_priority(priority, "HQ")
                if "MQ" in available and c.MQ_Rank > 0:
                    add_priority(priority, "MQ")
                if "IQ" in available and c.IQ_Rank > 0:
                    add_priority(priority, "IQ")

            # Community seat (only same category, and not NA)
            if c.Category not in ("NA", "", "NULL") and c.Category in available:
                add_priority(priority, c.Category)

            # HQ/MQ/IQ AFTER community (for all flags)
            if "HQ" in available and c.HQ_Rank > 0:
                add_priority(priority, "HQ")
            if "MQ" in available and c.MQ_Rank > 0:
                add_priority(priority, "MQ")
            if "IQ" in available and c.IQ_Rank > 0:
                add_priority(priority, "IQ")

            # Special categories
            for sc in ["PD", "CD", "AC", "MM", "NR", "NC", "NM"]:
                if sc not in available:
                    continue
                if not passes_special_rules(sc, flag, c):
                    continue
                add_priority(priority, sc)

            # SM last – open
            if "SM" in available:
                add_priority(priority, "SM")

            if is_debug:
                debug_logs.append(f"OPNO {op.OPNO}: Priority order = {priority}")

            # ---------- TRY TO FIND SEAT ----------
            chosen_cat = None
            chosen_key = None

            for sc in priority:
                skey = (grp, typ, course, college, sc)
                rem = seat_map.get(skey, 0)

                if rem <= 0:
                    if is_debug:
                        debug_logs.append(f"  Try {sc}: NO SEAT LEFT")
                    continue
                if not eligible_category(sc, c.Category):
                    if is_debug:
                        debug_logs.append(f"  Try {sc}: FAILED eligible_category (cand_cat={c.Category})")
                    continue
                if not passes_special_rules(sc, flag, c):
                    if is_debug:
                        debug_logs.append(f"  Try {sc}: FAILED passes_special_rules (flag={flag})")
                    continue

                chosen_cat = sc
                chosen_key = skey
                if is_debug:
                    debug_logs.append(f"  Try {sc}: SUCCESS -> seat allotted")
                break

            if not chosen_cat:
                if is_debug:
                    debug_logs.append(f"OPNO {op.OPNO}: No category could be allotted from priority list.")
                continue

            # Deduct seat
            seat_map[chosen_key] -= 1

            # Save allotment
            allotments.append({
                "RollNo": c.RollNo,
                "OPNO": op.OPNO,
                "College": college,
                "Course": course,
                "SeatCategory": chosen_cat,
                "AllotCode": make_allot_code(dec["prog"], typ, course, college, chosen_cat),
            })

            allotted_here = True
            if is_debug:
                debug_logs.append(f"✅ Candidate {c.RollNo} allotted: {college}-{course}-{chosen_cat} via OPNO {op.OPNO}")
            break  # stop at first successful option

        if not allotted_here and is_debug:
            debug_logs.append(f"❌ Candidate {c.RollNo} NOT allotted in any option.")

    # ----------------------------------------------------------
    # OUTPUT
    # ----------------------------------------------------------
    result = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Result")
    st.write("Total Allotted:", len(result))
    st.dataframe(result)

    # Detailed report
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
        admitted = pd.DataFrame(
            columns=["CollegeCode", "CourseCode", "CategoryCode", "AdmittedTotal"]
        )

    detail = seat_grouped.merge(
        admitted,
        on=["CollegeCode", "CourseCode", "CategoryCode"],
        how="left",
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

    rem_df = pd.DataFrame(rem_rows)
    st.subheader("🪑 Remaining Seats After Allotment")
    st.dataframe(rem_df)

    # Downloads
    buf1 = BytesIO()
    result.to_csv(buf1, index=False)
    buf1.seek(0)
    st.download_button("⬇ Download Allotment CSV", buf1, "Allotment.csv")

    buf2 = BytesIO()
    detail.to_csv(buf2, index=False)
    buf2.seek(0)
    st.download_button("⬇ Download Detailed Seat Report CSV", buf2, "Seat_Detail.csv")

    # Debug log output
    if debug_enabled and int(debug_roll or 0) > 0:
        st.subheader(f"🔍 Debug log for RollNo {int(debug_roll)}")
        if debug_logs:
            st.text("\n".join(str(line) for line in debug_logs))
        else:
            st.write("No debug information (candidate may not exist or no options).")


if __name__ == "__main__":
    pg_med_allotment()
