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
    "EW": []   # never convert
}

# =====================================================
# MAIN APP
# =====================================================

def llm_allotment():

    st.title("⚖️ LLM Counselling – Manual-Aligned Final Logic")

    phase = st.selectbox("Phase", [1, 2, 3, 4])

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Options", ["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", ["csv", "xlsx"])

    if not (cand_file and opt_file and seat_file):
        return

    # =====================================================
    # LOAD
    # =====================================================

    cand  = read_any(cand_file)
    opts  = read_any(opt_file)
    seats = read_any(seat_file)

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
    # SEATS – NORMALIZATION
    # =====================================================

    seats.columns = seats.columns.str.strip().str.upper().str.replace(" ", "")

    COL_MAP = {
        "GRP": "grp", "GROUP": "grp",
        "TYP": "typ", "TYPE": "typ",
        "COLLEGE": "college", "COLLEGECODE": "college",
        "COURSE": "course", "COURSECODE": "course",
        "CATEGORY": "category",
        "SEAT": "SEAT", "SEATS": "SEAT",
    }

    seats = seats.rename(columns={c: COL_MAP[c] for c in seats.columns if c in COL_MAP})

    required = {"grp", "typ", "college", "course", "category", "SEAT"}
    missing = required - set(seats.columns)
    if missing:
        st.error(f"❌ Seat Matrix missing columns: {', '.join(sorted(missing))}")
        st.stop()

    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = defaultdict(lambda: defaultdict(int))
    for _, r in seats.iterrows():
        base = (r["grp"], r["typ"], r["college"], r["course"])
        seat_cap[base][r["category"]] += r["SEAT"]

    # =====================================================
    # PASS 1 – NORMAL ALLOTMENT
    # =====================================================

    results = []
    allotted = set()
    allotted_opno = {}

    for _, C in cand.iterrows():

        roll = C["RollNo"]
        if phase >= 3 and roll not in opts_by_roll:
            continue

        for op in opts_by_roll.get(roll, []):

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            base = (dec["grp"], dec["typ"], dec["college"], dec["course"])

            # PD
            if C["Special3"] == "PD" and seat_cap[base]["PD"] > 0:
                seat_cap[base]["PD"] -= 1
                allotted.add(roll)
                allotted_opno[roll] = op["OPNO"]
                results.append({
                    "RollNo": roll, "LRank": C["LRank"],
                    "College": base[2], "Course": base[3],
                    "SeatCategory": "PD", "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(*base, "PD")
                })
                break

            # Exact category
            if seat_cap[base][C["Category"]] > 0:
                seat_cap[base][C["Category"]] -= 1
                allotted.add(roll)
                allotted_opno[roll] = op["OPNO"]
                results.append({
                    "RollNo": roll, "LRank": C["LRank"],
                    "College": base[2], "Course": base[3],
                    "SeatCategory": C["Category"], "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(*base, C["Category"])
                })
                break

            # SM
            if seat_cap[base]["SM"] > 0:
                seat_cap[base]["SM"] -= 1
                allotted.add(roll)
                allotted_opno[roll] = op["OPNO"]
                results.append({
                    "RollNo": roll, "LRank": C["LRank"],
                    "College": base[2], "Course": base[3],
                    "SeatCategory": "SM", "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(*base, "SM")
                })
                break

    # =====================================================
    # PASS 2 – VACANT SEAT UPGRADE (FINAL)
    # =====================================================

    if phase >= 3:

        # Bases that still have demand from UNALLOTTED candidates
        base_has_demand = set()
        for roll, oplist in opts_by_roll.items():
            if roll in allotted:
                continue
            for op in oplist:
                dec = decode_opt(op["Optn"])
                if dec:
                    base_has_demand.add(
                        (dec["grp"], dec["typ"], dec["college"], dec["course"])
                    )

        # Upgrade only
        for _, C in cand.iterrows():

            roll = C["RollNo"]
            if roll not in allotted:
                continue

            prev_opno = allotted_opno.get(roll, 9999)

            for op in opts_by_roll.get(roll, []):

                # must be higher preference
                if op["OPNO"] >= prev_opno:
                    continue

                dec = decode_opt(op["Optn"])
                if not dec:
                    continue

                base = (dec["grp"], dec["typ"], dec["college"], dec["course"])

                # block if any unallotted demand exists
                if base in base_has_demand:
                    continue

                cats = seat_cap.get(base, {})
                chosen_cat = None

                # priority: exact → SM → converted
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

                # APPLY UPGRADE
                cats[chosen_cat] -= 1
                allotted_opno[roll] = op["OPNO"]

                results.append({
                    "RollNo": roll, "LRank": C["LRank"],
                    "College": base[2], "Course": base[3],
                    "SeatCategory": chosen_cat, "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(
                        base[0], base[1],
                        base[3], base[2],
                        chosen_cat
                    )
                })

                break  # only one upgrade per candidate

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
