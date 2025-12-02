import streamlit as st
import pandas as pd
from io import BytesIO

# ---------------------------------------------------------
# Read CSV/Excel
# ---------------------------------------------------------
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# ---------------------------------------------------------
# Community eligibility (special quotas bypass)
# ---------------------------------------------------------
def eligible_category(seat_cat: str, cand_cat: str) -> bool:
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NULL", "NA"):
        cand_cat = "NA"

    # Special quota seats are controlled by passes_special_rules()
    if seat_cat in ("NR", "NC", "NM", "AC", "MM", "PD", "CD"):
        return True

    # SM is open to all
    if seat_cat == "SM":
        return True

    # NA candidate only eligible for SM and specials above
    if cand_cat == "NA":
        return False

    # Normal community seat: SC/ST/EZ/MU/... must match
    return seat_cat == cand_cat


# ---------------------------------------------------------
# Special rules for NR / NC / NM / AC / MM / PD / CD
# ---------------------------------------------------------
def passes_special_rules(seat_cat, flag, C):
    seat_cat = str(seat_cat).upper().strip()
    flag     = str(flag).upper().strip()

    cand_nri = str(C.get("NRI", "")).upper().strip()
    cand_min = str(C.get("Minority", "")).upper().strip()
    cand_sp3 = str(C.get("Special3", "")).upper().strip()
    cand_cat = str(C.get("Category", "")).upper().strip()

    # ---------------------------------------------------------
    # Case 1: NRI seat NR
    # Option must end with 'R'
    # Candidate NRI = NR
    # ---------------------------------------------------------
    if seat_cat == "NR":
        return (flag == "R" and cand_nri == "NR")

    # ---------------------------------------------------------
    # Case 4: NRI category NC
    # Option must end with 'R'
    # Candidate NRI = NRNC
    # ---------------------------------------------------------
    if seat_cat == "NC":
        return (flag == "R" and cand_nri == "NRNC")

    # ---------------------------------------------------------
    # Case 1 extension: NM seat
    # Option ends with 'R'
    # Candidate NRI = NM
    # (You confirmed NM = R rule)
    # ---------------------------------------------------------
    if seat_cat == "NM":
        return (flag == "R" and cand_nri == "NM")

    # ---------------------------------------------------------
    # Case 2: Minority AC seat
    # Option must end with 'Y'
    # Candidate Minority = AC
    # ---------------------------------------------------------
    if seat_cat == "AC":
        return (flag == "Y" and cand_min == "AC")

    # ---------------------------------------------------------
    # Case 3: Minority MM seat
    # Option must end with 'Y'
    # Candidate Minority = MM
    # ---------------------------------------------------------
    if seat_cat == "MM":
        return (flag == "Y" and cand_min == "MM")

    # ---------------------------------------------------------
    # Case 5: PD seats
    # Candidate Special3 = PD
    # ---------------------------------------------------------
    if seat_cat == "PD":
        return (cand_sp3 == "PD")

    # ---------------------------------------------------------
    # Case 6: CD seats
    # Candidate Category = SC AND Special3 = PD
    # ---------------------------------------------------------
    if seat_cat == "CD":
        return (cand_cat == "SC" and cand_sp3 == "PD")

    # ---------------------------------------------------------
    # All other seats (SM, EZ, MU, etc.)
    # No special rule required
    # ---------------------------------------------------------
    return True



# ---------------------------------------------------------
# Decode Option — PG format (8 characters)
# ---------------------------------------------------------
def decode_opt(opt: str):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],        # M
        "typ": opt[1],         # G / S
        "course": opt[2:4],    # 2-char course
        "college": opt[4:7],   # 3-char college
        "flag": opt[7],        # M / Y / R / N
    }


# ---------------------------------------------------------
# Final 11-digit allot code: MG + CC(2) + COL(3) + CAT(4)
# ---------------------------------------------------------
def make_allot_code(prog, typ, course, college, category):
    cat2 = category[:2].upper()
    return f"{prog}{typ}{course}{college}{cat2}{cat2}"


# ---------------------------------------------------------
# MAIN: PG Medical Allotment (fast engine)
# ---------------------------------------------------------
def pg_med_allotment():

    st.title("⚡ PG Medical Allotment – Final Engine")

    cand_f = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"])
    seat_f = st.file_uploader("2️⃣ Seat Matrix File", type=["csv", "xlsx"])
    opt_f  = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"])

    if not (cand_f and seat_f and opt_f):
        return

    # ---------- Load ----------
    cand = read_any(cand_f)
    seats = read_any(seat_f)
    opts = read_any(opt_f)

    st.success("✔ Files loaded")

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    num_cols = ["RollNo", "PRank", "HQ_Rank", "MQ_Rank", "IQ_Rank", "STRank"]
    for col in num_cols:
        if col not in cand.columns:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    # Safe defaults
    for col in ["Category", "NRI", "Minority", "Special3", "Status"]:
        if col not in cand.columns:
            cand[col] = ""
        cand[col] = cand[col].astype(str).str.upper().str.strip()

    # Remove PRank = 0 and Status = 'S'
    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")]
    cand = cand.sort_values("PRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ]

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo", "OPNO"])

    # Index options per candidate for speed
    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # =====================================================
    # CLEAN & INDEX SEATS
    # =====================================================
    for col in ["grp", "typ", "course", "college", "category"]:
        if col not in seats.columns:
            seats[col] = ""
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    # index: key = (typ, course, college) → dict(category → remaining seats)
    seat_index = {}
    for _, r in seats.iterrows():
        key = (r["typ"], r["course"], r["college"])
        cat = r["category"]
        seat_index.setdefault(key, {})
        seat_index[key][cat] = seat_index[key].get(cat, 0) + r["SEAT"]

    # =====================================================
    # ALLOTMENT ENGINE
    # =====================================================
    allotments = []

    for _, C in cand.iterrows():

        roll = C["RollNo"]
        cand_cat = C["Category"]

        if roll not in opts_by_roll:
            continue

        cand_opts = opts_by_roll[roll]

        for op in cand_opts:

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            prog    = dec["prog"]
            typ     = dec["typ"]
            course  = dec["course"]
            college = dec["college"]
            flag    = dec["flag"]

            seat_key = (typ, course, college)
            if seat_key not in seat_index:
                continue

            cat_map = seat_index[seat_key]

            # Priority list for this candidate
            priority = []
            if cand_cat not in ("NA", "NULL", ""):
                priority.append(cand_cat)
            if C["HQ_Rank"] > 0:
                priority.append("HQ")
            if C["MQ_Rank"] > 0:
                priority.append("MQ")
            if C["IQ_Rank"] > 0:
                priority.append("IQ")
            # SM always last
            priority.append("SM")

            chosen_cat = None

            for sc in priority:
                if sc not in cat_map:
                    continue
                if cat_map[sc] <= 0:
                    continue
                if not passes_special_rules(sc, flag, C):
                    continue
                if not eligible_category(sc, cand_cat):
                    continue

                chosen_cat = sc
                break

            if not chosen_cat:
                continue

            # Deduct seat
            cat_map[chosen_cat] -= 1

            allot_code = make_allot_code(prog, typ, course, college, chosen_cat)

            allotments.append({
                "RollNo": roll,
                "OPNO": op["OPNO"],
                "AllotCode": allot_code,
                "College": college,
                "Course": course,
                "SeatCategory": chosen_cat,
            })

            # Stop at first successful allotment for this candidate
            break

    # =====================================================
    # OUTPUT
    # =====================================================
    result = pd.DataFrame(allotments)

    st.subheader("✅ Allotment Completed")
    st.write(f"Total Allotted: **{len(result)}**")
    st.dataframe(result)

    buf = BytesIO()
    result.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download PG Allotment Result",
        buf,
        "PG_Allotment.csv",
        "text/csv",
    )
