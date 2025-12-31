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

# =====================================================
# SEAT CONVERSION (PHASE >= 3)
# =====================================================

def get_conversion_chain(seat_cat):
    if seat_cat == "SC":
        return ["SC", "ST", "OE", "SM"]
    if seat_cat == "ST":
        return ["ST", "SC", "OE", "SM"]
    if seat_cat == "PD":
        return ["PD", "SM"]
    if seat_cat in ("MU", "EZ", "BH", "BX", "KN", "KU", "VK", "DV"):
        return ["SM"]
    if seat_cat == "EW":
        return ["EW"]      # strictly no conversion
    return [seat_cat, "SM"]

def eligible_with_conversion(seat_cat, cand_cat, special3, others):
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

    st.title("⚖️ LLM Counselling – Greedy Allotment (Phase-Aware)")

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

    cand["Status"] = cand.get("Status", "").astype(str).str.upper().str.strip()
    cand = cand[cand["Status"] != "S"]

    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["LRank"]  = pd.to_numeric(cand["LRank"], errors="coerce").fillna(999999).astype(int)

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

    opts["ValidOption"] = opts.get("ValidOption", "Y").astype(str).str.upper()
    opts["Delflg"]      = opts.get("Delflg", "N").astype(str).str.upper()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y", "T"])) &
        (opts["Delflg"] != "Y")
    ]

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo", "OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # =====================================================
    # SEATS (SAFE NORMALIZATION)
    # =====================================================

    seats.columns = (
        seats.columns
             .str.strip()
             .str.upper()
             .str.replace(" ", "")
    )

    COL_MAP = {
        "GRP": "grp", "GROUP": "grp",
        "TYPE": "typ",
        "COLLEGECODE": "college", "COLLEGE": "college",
        "COURSECODE": "course", "COURSE": "course",
        "CATEGORY": "category",
        "SEAT": "SEAT", "SEATS": "SEAT"
    }

    seats = seats.rename(columns={k: v for k, v in COL_MAP.items() if k in seats.columns})

    required = {"grp", "typ", "college", "course", "category", "SEAT"}
    missing = required - set(seats.columns)
    if missing:
        st.error(f"❌ Seat Matrix missing columns: {', '.join(missing)}")
        st.stop()

    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    for _, r in seats.iterrows():
        k = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_cap[k] = seat_cap.get(k, 0) + r["SEAT"]

    # =====================================================
    # PROTECTED ADMISSION (ONLY UPTO PHASE 2)
    # =====================================================

    protected = {}
    if phase <= 2 and prev is not None:
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
                "opno": int(r.get(f"OPNO_{phase-1}", 9999))
            }

    if phase == 2:
        cand = cand[(cand["ConfirmFlag"] == "Y") | (cand["RollNo"].isin(protected))]

    # =====================================================
    # ALLOTMENT
    # =====================================================

    results = []

    for _, C in cand.iterrows():

        roll = C["RollNo"]

        # 🚫 Phase ≥3 → no options → no allotment
        if phase >= 3 and roll not in opts_by_roll:
            continue

        cat = C["Category"]
        sp3 = C["Special3"]
        oth = C["Others"]

        allotted = False

        for op in opts_by_roll.get(roll, []):

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            g, t, col, crs = dec["grp"], dec["typ"], dec["college"], dec["course"]

            # ---- PD PRIORITY ----
            if sp3 == "PD":
                k = (g, t, col, crs, "PD")
                if seat_cap.get(k, 0) > 0:
                    seat_cap[k] -= 1
                    results.append({
                        "RollNo": roll,
                        "LRank": C["LRank"],
                        "College": col,
                        "Course": crs,
                        "SeatCategory": "PD",
                        "OPNO": op["OPNO"],
                        "AllotCode": make_allot_code(g, t, crs, col, "PD")
                    })
                    allotted = True
                    break

            # ---- SM ----
            k = (g, t, col, crs, "SM")
            if seat_cap.get(k, 0) > 0:
                seat_cap[k] -= 1
                results.append({
                    "RollNo": roll,
                    "LRank": C["LRank"],
                    "College": col,
                    "Course": crs,
                    "SeatCategory": "SM",
                    "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(g, t, crs, col, "SM")
                })
                allotted = True
                break

            # ---- CATEGORY + CONVERSION ----
            for (kg, kt, kcol, kcrs, sc), cap in list(seat_cap.items()):
                if cap <= 0:
                    continue
                if (kg, kt, kcol, kcrs) != (g, t, col, crs):
                    continue

                chain = [sc] if phase < 3 else get_conversion_chain(sc)

                for conv in chain:
                    if not eligible_with_conversion(conv, cat, sp3, oth):
                        continue

                    seat_cap[(kg, kt, kcol, kcrs, sc)] -= 1
                    results.append({
                        "RollNo": roll,
                        "LRank": C["LRank"],
                        "College": kcol,
                        "Course": kcrs,
                        "SeatCategory": conv,
                        "OPNO": op["OPNO"],
                        "AllotCode": make_allot_code(
                            kg, kt, kcrs, kcol, conv
                        )
                    })
                    allotted = True
                    break

                if allotted:
                    break

            if allotted:
                break

        # ---- PROTECTED ADMISSION (ONLY PHASE 1–2) ----
        if phase <= 2 and not allotted and roll in protected:
            cur = protected[roll]
            k = (cur["grp"], cur["typ"], cur["college"], cur["course"], cur["cat"])
            if seat_cap.get(k, 0) > 0:
                seat_cap[k] -= 1
                results.append({
                    "RollNo": roll,
                    "LRank": C["LRank"],
                    "College": cur["college"],
                    "Course": cur["course"],
                    "SeatCategory": cur["cat"],
                    "OPNO": cur["opno"],
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
