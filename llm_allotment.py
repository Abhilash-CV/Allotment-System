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
# CONVERSION POLICY (PHASE >= 3)
# =====================================================

CONVERSION_MAP = {
    "SC": ["ST", "OE", "SM"],
    "ST": ["SC", "OE", "SM"],
    "PD": ["SM"],
    "MU": ["SM"], "EZ": ["SM"], "BH": ["SM"],
    "BX": ["SM"], "KN": ["SM"], "KU": ["SM"],
    "VK": ["SM"], "DV": ["SM"],
    "EW": []   # strictly no conversion
}

def eligible(seat_cat, cand_cat, special3, others):
    if seat_cat == "SM":
        return True
    if seat_cat == "PD":
        return special3 == "PD"
    if seat_cat == "OE":
        return others == "OE"
    return seat_cat == cand_cat

# =====================================================
# MAIN APP
# =====================================================

def llm_allotment():

    st.title("⚖️ LLM Counselling – Phase-Aware Allotment with Audit")

    phase = st.selectbox("Phase", [1, 2, 3, 4])

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Options", ["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", ["csv", "xlsx"])
    prev_file = st.file_uploader("4️⃣ Previous Allotment", ["csv", "xlsx"]) if phase > 1 else None

    if not (cand_file and opt_file and seat_file):
        return

    # =====================================================
    # LOAD
    # =====================================================

    cand  = read_any(cand_file)
    opts  = read_any(opt_file)
    seats = read_any(seat_file)
    prev  = read_any(prev_file) if prev_file else None

    # =====================================================
    # CANDIDATES
    # =====================================================

    cand["Status"]   = cand.get("Status", "").astype(str).str.upper().str.strip()
    cand             = cand[cand["Status"] != "S"]
    cand["RollNo"]   = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["LRank"]    = pd.to_numeric(cand["LRank"], errors="coerce").fillna(999999).astype(int)
    cand["Category"] = cand.get("Category", "").astype(str).str.upper().str.strip()
    cand["Special3"] = cand.get("Special3", "").astype(str).str.upper().str.strip()
    cand["Others"]   = cand.get("Others", "").astype(str).str.upper().str.strip()

    if phase == 2:
        cand["ConfirmFlag"] = cand.get("ConfirmFlag", "").astype(str).str.upper().str.strip()

    cand = cand.sort_values("LRank")

    # =====================================================
    # OPTIONS
    # =====================================================

    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts["Optn"]   = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo", "OPNO"])

    opts_by_roll = defaultdict(list)
    for _, r in opts.iterrows():
        opts_by_roll[r["RollNo"]].append(r)

    # =====================================================
    # SEATS – NORMALIZE & INDEX (PERFORMANCE)
    # =====================================================

    seats.columns = seats.columns.str.strip().str.upper().str.replace(" ", "")
    seats = seats.rename(columns={
        "GROUP": "grp", "GRP": "grp",
        "TYPE": "typ",
        "COLLEGECODE": "college",
        "COURSECODE": "course",
        "CATEGORY": "category",
        "SEAT": "SEAT"
    })

    required = {"grp", "typ", "college", "course", "category", "SEAT"}
    missing = required - set(seats.columns)
    if missing:
        st.error(f"❌ Seat Matrix missing columns: {', '.join(missing)}")
        st.stop()

    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    # ---- seat_cap indexed by (grp,typ,col,course)[category] ----
    seat_cap = defaultdict(lambda: defaultdict(int))
    for _, r in seats.iterrows():
        base = (r["grp"], r["typ"], r["college"], r["course"])
        seat_cap[base][r["category"]] += r["SEAT"]

    # =====================================================
    # AUDIT SNAPSHOT – BEFORE CONVERSION
    # =====================================================

    vacancy_before = []
    for base, cats in seat_cap.items():
        for cat, cnt in cats.items():
            if cnt > 0:
                vacancy_before.append({
                    "grp": base[0], "typ": base[1],
                    "college": base[2], "course": base[3],
                    "SeatCategory": cat,
                    "Vacant": cnt
                })

    # =====================================================
    # PASS 1 – NORMAL ALLOTMENT (NO CONVERSION)
    # =====================================================

    results = []
    allotted = set()

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
                results.append({
                    "RollNo": roll, "LRank": C["LRank"],
                    "College": base[2], "Course": base[3],
                    "SeatCategory": "PD", "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(*base, "PD")
                })
                break

            # Exact category
            cat = C["Category"]
            if seat_cap[base][cat] > 0:
                seat_cap[base][cat] -= 1
                allotted.add(roll)
                results.append({
                    "RollNo": roll, "LRank": C["LRank"],
                    "College": base[2], "Course": base[3],
                    "SeatCategory": cat, "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(*base, cat)
                })
                break

            # SM
            if seat_cap[base]["SM"] > 0:
                seat_cap[base]["SM"] -= 1
                allotted.add(roll)
                results.append({
                    "RollNo": roll, "LRank": C["LRank"],
                    "College": base[2], "Course": base[3],
                    "SeatCategory": "SM", "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(*base, "SM")
                })
                break

    # =====================================================
    # PASS 2 – VACANCY-BASED CONVERSION (PHASE >= 3)
    # =====================================================

    conversion_log = []

    if phase >= 3:

        for _, C in cand.iterrows():

            roll = C["RollNo"]
            if roll in allotted or roll not in opts_by_roll:
                continue

            for op in opts_by_roll[roll]:
                dec = decode_opt(op["Optn"])
                if not dec:
                    continue

                base = (dec["grp"], dec["typ"], dec["college"], dec["course"])

                for seat_cat, cnt in list(seat_cap[base].items()):
                    if cnt <= 0:
                        continue

                    for conv in CONVERSION_MAP.get(seat_cat, []):
                        if eligible(conv, C["Category"], C["Special3"], C["Others"]):

                            # ---- ASSERTIONS ----
                            assert seat_cat != "EW", "❌ EW seat illegally converted"
                            assert seat_cap[base][seat_cat] > 0, "❌ Negative seat usage"

                            seat_cap[base][seat_cat] -= 1
                            allotted.add(roll)

                            results.append({
                                "RollNo": roll, "LRank": C["LRank"],
                                "College": base[2], "Course": base[3],
                                "SeatCategory": conv, "OPNO": op["OPNO"],
                                "AllotCode": make_allot_code(*base, conv)
                            })

                            conversion_log.append({
                                "College": base[2], "Course": base[3],
                                "FromSeat": seat_cat,
                                "ToSeat": conv,
                                "RollNo": roll
                            })
                            break
                    else:
                        continue
                    break
                else:
                    continue
                break

    # =====================================================
    # AUDIT SNAPSHOT – AFTER CONVERSION
    # =====================================================

    vacancy_after = []
    for base, cats in seat_cap.items():
        for cat, cnt in cats.items():
            if cnt > 0:
                vacancy_after.append({
                    "grp": base[0], "typ": base[1],
                    "college": base[2], "course": base[3],
                    "SeatCategory": cat,
                    "Vacant": cnt
                })

    # =====================================================
    # OUTPUTS
    # =====================================================

    df_res = pd.DataFrame(results)
    st.success(f"✅ Phase {phase} completed — {len(df_res)} seats allotted")
    st.dataframe(df_res)

    st.subheader("🧾 Vacancy Audit – Before Conversion")
    st.dataframe(pd.DataFrame(vacancy_before))

    st.subheader("🧾 Vacancy Audit – After Conversion")
    st.dataframe(pd.DataFrame(vacancy_after))

    st.subheader("🔄 Seat-wise Conversion Report")
    st.dataframe(pd.DataFrame(conversion_log))

    # Downloads
    def dl(df, name):
        b = BytesIO()
        df.to_csv(b, index=False)
        b.seek(0)
        st.download_button(f"⬇ {name}", b, f"{name}.csv", "text/csv")

    dl(df_res, "Allotment_Result")
    dl(pd.DataFrame(vacancy_before), "Vacancy_Before")
    dl(pd.DataFrame(vacancy_after), "Vacancy_After")
    dl(pd.DataFrame(conversion_log), "Seat_Conversion")

# =====================================================
# RUN
# =====================================================

llm_allotment()
