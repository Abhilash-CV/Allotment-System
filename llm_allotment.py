import streamlit as st
import pandas as pd
from io import BytesIO
from collections import defaultdict

# =====================================================
# HELPERS
# =====================================================

def read_any(f):
    if f.name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")

def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) < 7:
        return None
    return {
        "grp": opt[0],
        "typ": opt[1],
        "course": opt[2:4],
        "college": opt[4:7],
    }

def make_allot_code(g, t, c, col, cat):
    c2 = cat[:2]
    return f"{g}{t}{c}{col}{c2}{c2}"

def replace_result(results, roll, new_row):
    for i, r in enumerate(results):
        if r["RollNo"] == roll:
            results[i] = new_row
            return

def higher_rank_demand_exists(base, curr_rank, cand, opts_by_roll, allotted):
    for _, C in cand.iterrows():
        if C["RollNo"] in allotted:
            continue
        if C["LRank"] >= curr_rank:
            continue
        for op in opts_by_roll.get(C["RollNo"], []):
            dec = decode_opt(op["Optn"])
            if dec and (
                dec["grp"], dec["typ"],
                dec["college"], dec["course"]
            ) == base:
                return True
    return False

# =====================================================
# CONVERSION POLICY
# =====================================================

CONVERSION_MAP = {
    "SC": ["ST", "OE", "SM"],
    "ST": ["SC", "OE", "SM"],
    "PD": ["SM"],
    "MU": ["SM"], "EZ": ["SM"], "BH": ["SM"],
    "BX": ["SM"], "KN": ["SM"], "KU": ["SM"],
    "VK": ["SM"], "DV": ["SM"],
    "EW": []
}

# =====================================================
# MAIN APP
# =====================================================

def llm_allotment():

    st.title("⚖️ LLM Counselling – Phase-Chained Allotment Engine")

    phase = st.selectbox("Phase", [1, 2, 3, 4])

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Options", ["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", ["csv", "xlsx"])

    prev_file = None
    if phase >= 2:
        prev_file = st.file_uploader(
            "4️⃣ Previous Allotment (AllotmentDetails)",
            ["csv", "xlsx"]
        )

    if not (cand_file and opt_file and seat_file):
        return
    if phase >= 2 and not prev_file:
        st.warning("Phase-2 and above require Previous Allotment file")
        return

    # =====================================================
    # LOAD FILES
    # =====================================================

    cand  = read_any(cand_file)
    opts  = read_any(opt_file)
    seats = read_any(seat_file)
    prev  = read_any(prev_file) if prev_file else None

    # =====================================================
    # CANDIDATES
    # =====================================================

    cand["RollNo"]   = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["LRank"]    = pd.to_numeric(cand["LRank"], errors="coerce").fillna(999999).astype(int)
    cand["Category"] = cand.get("Category", "").astype(str).str.upper().str.strip()
    cand["Special3"] = cand.get("Special3", "").astype(str).str.upper().str.strip()
    cand["Others"]   = cand.get("Others", "").astype(str).str.upper().str.strip()

    cand = cand.sort_values("LRank")

    # =====================================================
    # OPTIONS
    # =====================================================

    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts["Optn"]   = opts["Optn"].astype(str).str.upper().str.strip()

    opts_by_roll = defaultdict(list)
    for _, r in opts.iterrows():
        if r["OPNO"] > 0:
            opts_by_roll[r["RollNo"]].append(r)

    # =====================================================
    # SEAT MATRIX
    # =====================================================

    seats.columns = seats.columns.str.strip().str.upper().str.replace(" ", "")
    seats = seats.rename(columns={
        "GRP": "grp", "GROUP": "grp",
        "TYP": "typ", "TYPE": "typ",
        "COLLEGE": "college", "COLLEGECODE": "college",
        "COURSE": "course", "COURSECODE": "course",
        "CATEGORY": "category",
        "SEAT": "SEAT", "SEATS": "SEAT",
    })

    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = defaultdict(lambda: defaultdict(int))
    for _, r in seats.iterrows():
        base = (r["grp"], r["typ"], r["college"], r["course"])
        seat_cap[base][r["category"]] += r["SEAT"]

    # =====================================================
    # INITIALISE FROM PREVIOUS ALLOTMENT (PHASE ≥ 2)
    # =====================================================

    results = []
    allotted = set()
    allotted_opno = {}
    allotted_seat = {}

    if phase >= 2:

        for _, r in prev.iterrows():

            roll = int(r["RollNo"])
            allot = str(r["AllotCode"]).upper().strip()

            if len(allot) < 9:
                continue

            g = allot[0]
            t = allot[1]
            course = allot[2:4]
            college = allot[4:7]
            seat_cat = allot[7:9]

            base = (g, t, college, course)

            allotted.add(roll)
            allotted_opno[roll] = int(r["OPNO"])
            allotted_seat[roll] = (base, seat_cat)

            seat_cap[base][seat_cat] -= 1

            results.append({
                "RollNo": roll,
                "LRank": r.get("LRank", ""),
                "College": college,
                "Course": course,
                "SeatCategory": seat_cat,
                "OPNO": r["OPNO"],
                "AllotCode": allot
            })

    # =====================================================
    # PASS-1 (NEW CANDIDATES ONLY)
    # =====================================================

    for _, C in cand.iterrows():

        roll = C["RollNo"]
        if roll in allotted:
            continue

        for op in opts_by_roll.get(roll, []):

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            base = (dec["grp"], dec["typ"], dec["college"], dec["course"])

            def allot(seat_cat):
                seat_cap[base][seat_cat] -= 1
                allotted.add(roll)
                allotted_opno[roll] = op["OPNO"]
                allotted_seat[roll] = (base, seat_cat)
                results.append({
                    "RollNo": roll,
                    "LRank": C["LRank"],
                    "College": base[2],
                    "Course": base[3],
                    "SeatCategory": seat_cat,
                    "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(*base, seat_cat)
                })

            if C["Special3"] == "PD" and seat_cap[base]["PD"] > 0:
                allot("PD"); break
            if seat_cap[base][C["Category"]] > 0:
                allot(C["Category"]); break
            if seat_cap[base]["SM"] > 0:
                allot("SM"); break

    # =====================================================
    # PASS-2 / PASS-3 UPGRADES (PHASE ≥ 3)
    # =====================================================

    if phase >= 3:

        for _, C in cand.iterrows():

            roll = C["RollNo"]
            if roll not in allotted:
                continue

            prev_opno = allotted_opno[roll]

            for op in opts_by_roll.get(roll, []):

                if op["OPNO"] >= prev_opno:
                    continue

                dec = decode_opt(op["Optn"])
                if not dec:
                    continue

                base = (dec["grp"], dec["typ"], dec["college"], dec["course"])

                if higher_rank_demand_exists(
                    base, C["LRank"], cand, opts_by_roll, allotted
                ):
                    continue

                cats = seat_cap[base]
                chosen_cat = None

                if cats.get(C["Category"], 0) > 0:
                    chosen_cat = C["Category"]
                elif cats.get("SM", 0) > 0:
                    chosen_cat = "SM"
                else:
                    for sc, cnt in cats.items():
                        if cnt > 0 and sc != "EW":
                            for tgt in CONVERSION_MAP.get(sc, []):
                                if tgt in ("SM", C["Category"]):
                                    chosen_cat = tgt
                                    break
                        if chosen_cat:
                            break

                if not chosen_cat:
                    continue

                old_base, old_cat = allotted_seat[roll]
                seat_cap[old_base][old_cat] += 1
                seat_cap[base][chosen_cat] -= 1

                new_row = {
                    "RollNo": roll,
                    "LRank": C["LRank"],
                    "College": base[2],
                    "Course": base[3],
                    "SeatCategory": chosen_cat,
                    "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(*base, chosen_cat)
                }

                replace_result(results, roll, new_row)
                allotted_opno[roll] = op["OPNO"]
                allotted_seat[roll] = (base, chosen_cat)

                break

    # =====================================================
    # OUTPUT
    # =====================================================

    df = pd.DataFrame(results)
    st.success(f"✅ Phase {phase} completed — {len(df)} seats allotted")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    st.download_button(
        "⬇ Download Result",
        buf,
        f"LLM_Allotment_Phase{phase}.csv",
        "text/csv"
    )

# =====================================================
# RUN
# =====================================================

llm_allotment()
