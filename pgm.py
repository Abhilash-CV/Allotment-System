import streamlit as st
import pandas as pd
from io import BytesIO

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

def eligible_for_seat(seat_cat, cand_cat, special3, cand_minority, is_minority_opt):
    # PD
    if seat_cat == "PD":
        return special3 == "PD"

    # Minority seats
    if seat_cat in ("MM", "AC"):
        return is_minority_opt and cand_minority == seat_cat

    # SM
    if seat_cat == "SM":
        return True

    # Category
    if cand_cat in ("", "NA", "NULL"):
        return False

    return seat_cat == cand_cat

# =====================================================
# MAIN APP
# =====================================================

def pg_med_allotment():

    st.title("⚖️ PG Medical Counselling – Greedy Allotment")

    phase = st.selectbox("Phase", [1, 2, 3, 4])

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Options", ["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", ["csv", "xlsx"])
    prev_file = st.file_uploader("4️⃣ Previous Allotment", ["csv", "xlsx"]) if phase > 1 else None

    if not (cand_file and opt_file and seat_file):
        return

    # =====================================================
    # LOAD FILES
    # =====================================================

    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)
    prev  = read_any(prev_file) if prev_file else None

    # =====================================================
    # CANDIDATES
    # =====================================================

    cand["Status"] = cand.get("Status", "").astype(str).str.upper().str.strip()
    cand = cand[cand["Status"] != "S"]

    cand["RollNo"] = pd.to_numeric(cand.get("RollNo"), errors="coerce").fillna(0).astype(int)
    cand["LRank"]  = pd.to_numeric(cand.get("LRank"), errors="coerce").fillna(999999).astype(int)

    cand["Category"]  = cand.get("Category", "").astype(str).str.upper().str.strip()
    cand["Special3"]  = cand.get("Special3", "").astype(str).str.upper().str.strip()
    cand["Minority"]  = cand.get("Minority", "").astype(str).str.upper().str.strip()
    cand["Quota"]     = cand.get("Quota", "").astype(str).str.upper().str.strip()

    # ---- PG MEDICAL RANK PRIORITY ----
    for r in ["HQ_Rank", "IQ_Rank", "MQ_Rank"]:
        if r in cand.columns:
            cand[r] = pd.to_numeric(cand[r], errors="coerce")

    def select_prank(row):
        for r in ["MQ_Rank", "HQ_Rank", "IQ_Rank"]:
            if r in row and pd.notna(row[r]):
                return int(row[r])
        return int(row["LRank"])

    cand["PRank"] = cand.apply(select_prank, axis=1)

    if phase == 2:
        cand["ConfirmFlag"] = cand.get("ConfirmFlag", "").astype(str).str.upper().str.strip()

    cand = cand.sort_values("PRank")

    # =====================================================
    # OPTIONS
    # =====================================================

    opts["RollNo"] = pd.to_numeric(opts.get("RollNo"), errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts.get("OPNO"), errors="coerce").fillna(0).astype(int)

    opts["ValidOption"] = opts.get("ValidOption", "Y").astype(str).str.upper()
    opts["Delflg"]      = opts.get("Delflg", "N").astype(str).str.upper()

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()

    # 🔒 OPTION = G ONLY (GLOBAL RULE)
    opts = opts[opts["Optn"].str.endswith("G")]

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y", "T"])) &
        (opts["Delflg"] != "Y")
    ]

    opts["IsMinorityOpt"] = opts["Optn"].str.endswith("Y")

    opts = opts.sort_values(["RollNo", "OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # =====================================================
    # SEATS
    # =====================================================

    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    for _, r in seats.iterrows():
        k = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_cap[k] = seat_cap.get(k, 0) + r["SEAT"]

    # =====================================================
    # PROTECTED ADMISSION
    # =====================================================

    protected = {}
    if prev is not None:
        for _, r in prev.iterrows():
            code = str(r.get("Curr_Admn", "")).upper().strip()
            if len(code) < 9:
                continue
            protected[int(r["RollNo"])] = {
                "grp": code[0],
                "typ": code[1],
                "course": code[2:4],
                "college": code[4:7],
                "cat": code[7:9],
                "opno": int(r.get(f"OPNO_{phase-1}", 9999)) if str(r.get(f"OPNO_{phase-1}", "")).isdigit() else 9999
            }

    if phase == 2:
        cand = cand[(cand["ConfirmFlag"] == "Y") | (cand["RollNo"].isin(protected))]

    # =====================================================
    # ALLOTMENT
    # =====================================================

    results = []

    for _, C in cand.iterrows():

        roll = C["RollNo"]
        cat  = C["Category"]
        sp3  = C["Special3"]
        minr = C["Minority"]
        quota = C["Quota"]

        allotted = False

        for op in opts_by_roll.get(roll, []):

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            g, t, col, crs = dec["grp"], dec["typ"], dec["college"], dec["course"]

            # SQ → only service quota seats
            if quota == "SQ" and t != "S":
                continue

            # 1️⃣ PD
            if sp3 == "PD":
                k = (g, t, col, crs, "PD")
                if seat_cap.get(k, 0) > 0:
                    seat_cap[k] -= 1
                    results.append({
                        "RollNo": roll, "PRank": C["PRank"],
                        "College": col, "Course": crs,
                        "SeatCategory": "PD", "OPNO": op["OPNO"],
                        "AllotCode": make_allot_code(g, t, crs, col, "PD")
                    })
                    allotted = True
                    break

            # 2️⃣ SM
            k = (g, t, col, crs, "SM")
            if seat_cap.get(k, 0) > 0:
                seat_cap[k] -= 1
                results.append({
                    "RollNo": roll, "PRank": C["PRank"],
                    "College": col, "Course": crs,
                    "SeatCategory": "SM", "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(g, t, crs, col, "SM")
                })
                allotted = True
                break

            # 3️⃣ CATEGORY / MINORITY
            for (kg, kt, kcol, kcrs, sc), cap in seat_cap.items():
                if cap <= 0:
                    continue
                if (kg, kt, kcol, kcrs) != (g, t, col, crs):
                    continue
                if sc == "SM":
                    continue
                if not eligible_for_seat(sc, cat, sp3, minr, op["IsMinorityOpt"]):
                    continue

                seat_cap[(kg, kt, kcol, kcrs, sc)] -= 1
                results.append({
                    "RollNo": roll, "PRank": C["PRank"],
                    "College": kcol, "Course": kcrs,
                    "SeatCategory": sc, "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(kg, kt, kcrs, kcol, sc)
                })
                allotted = True
                break

            if allotted:
                break

        # PROTECT CURRENT ADMISSION
        if not allotted and roll in protected:
            cur = protected[roll]
            if cur["cat"] in ("MM", "AC") and minr != cur["cat"]:
                pass
            else:
                k = (cur["grp"], cur["typ"], cur["college"], cur["course"], cur["cat"])
                if seat_cap.get(k, 0) > 0:
                    seat_cap[k] -= 1
                    results.append({
                        "RollNo": roll, "PRank": C["PRank"],
                        "College": cur["college"], "Course": cur["course"],
                        "SeatCategory": cur["cat"], "OPNO": cur["opno"],
                        "AllotCode": make_allot_code(
                            cur["grp"], cur["typ"],
                            cur["course"], cur["college"], cur["cat"]
                        )
                    })

    # =====================================================
    # OUTPUT
    # =====================================================

    df = pd.DataFrame(results)
    st.success(f"✅ Phase {phase} completed — {len(df)} seats allotted")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    st.download_button("⬇ Download Result", buf, f"PG_Medical_Allotment_Phase{phase}.csv", "text/csv")


# =====================================================
# RUN
# =====================================================

pg_med_allotment()
