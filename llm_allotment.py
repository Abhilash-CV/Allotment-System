import streamlit as st
import pandas as pd
from io import BytesIO

# =========================================================
# FILE READER
# =========================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# =========================================================
# OPTION DECODER (LLM)
# Format assumed:
# 0: grp, 1: typ, 2-3: course, 4-6: college
# =========================================================
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


# =========================================================
# CATEGORY ELIGIBILITY
# =========================================================
def eligible_for_seat(seat_cat, cand_cat, cand_sp3):
    seat_cat = seat_cat.upper().strip()
    cand_cat = cand_cat.upper().strip()
    cand_sp3 = cand_sp3.upper().strip()

    # PD seats
    if seat_cat == "PD":
        return cand_sp3 == "PD"

    # SM open to all
    if seat_cat == "SM":
        return True

    # NA candidates → only SM
    if cand_cat in ("", "NA", "NULL"):
        return False

    return seat_cat == cand_cat


# =========================================================
# ALLOT CODE (11 chars)
# =========================================================
def make_allot_code(grp, typ, course, college, cat):
    c = cat[:2].upper()
    return f"{grp}{typ}{course}{college}{c}{c}"


# =========================================================
# MAIN LLM ALLOTMENT
# =========================================================
def llm_allotment():

    st.title("⚖️ LLM Allotment – Gale–Shapley (Phase-aware)")

    phase = st.selectbox("Select Allotment Phase", [1, 2], index=1)

    cand_file = st.file_uploader("1️⃣ Candidates", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Option Entry", type=["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Category", type=["csv", "xlsx"])
    allot_file = None

    if phase > 1:
        allot_file = st.file_uploader("4️⃣ Allotment Details (Previous Phase)", type=["csv", "xlsx"])

    if not (cand_file and opt_file and seat_file):
        return
    if phase > 1 and not allot_file:
        return

    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)
    allot_prev = read_any(allot_file) if phase > 1 else None

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    for c in ["RollNo", "LRank"]:
        cand[c] = pd.to_numeric(cand.get(c, 0), errors="coerce").fillna(0).astype(int)

    cand["Category"] = cand.get("Category", "").astype(str).str.upper()
    cand["Special3"] = cand.get("Special3", "").astype(str).str.upper()
    cand["Status"] = cand.get("Status", "").astype(str).str.upper()
    cand["ConfirmFlag"] = cand.get("ConfirmFlag", "").astype(str).str.upper()

    if phase > 1:
        js_col = f"JoinStatus_{phase-1}"
        cand[js_col] = cand.get(js_col, "").astype(str).str.upper()

        # 🔴 PHASE-2 FILTER (CRITICAL)
        cand = cand[
            (cand["ConfirmFlag"] == "Y") &
            (cand["Status"] != "S") &
            (~cand[js_col].isin(["N", "TC"]))
        ].copy()
    else:
        cand = cand[(cand["Status"] != "S") & (cand["LRank"] > 0)].copy()

    cand = cand.sort_values("LRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    opts["RollNo"] = pd.to_numeric(opts.get("RollNo", 0), errors="coerce").fillna(0).astype(int)
    opts["OPNO"] = pd.to_numeric(opts.get("OPNO", 0), errors="coerce").fillna(0).astype(int)

    opts["ValidOption"] = opts.get("ValidOption", "Y").astype(str).str.upper()
    opts["Delflg"] = opts.get("Delflg", "").astype(str).str.upper()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y", "T"])) &
        (opts["Delflg"] != "Y")
    ].copy()

    opts = opts.sort_values(["RollNo", "OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # =====================================================
    # CLEAN SEATS
    # =====================================================
    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()
    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    seat_idx = {}

    for _, r in seats.iterrows():
        kf = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        kb = (r["grp"], r["typ"], r["college"], r["course"])
        seat_cap[kf] = seat_cap.get(kf, 0) + r["SEAT"]
        seat_idx.setdefault(kb, []).append(r["category"])

    # =====================================================
    # EXISTING ADMISSIONS (PROTECTION)
    # =====================================================
    protected = {}
    if phase > 1:
        for _, r in allot_prev.iterrows():
            roll = int(r["RollNo"])
            protected[roll] = {
                "grp": r["grp"],
                "typ": r["typ"],
                "college": r["College"],
                "course": r["Course"],
                "category": r["SeatCategory"],
                "AllotCode": r["AllotCode"],
                "OPNO": r["OPNO"],
            }

    # =====================================================
    # GALE–SHAPLEY (CANDIDATE-PROPOSING)
    # =====================================================
    results = []

    for _, c in cand.iterrows():
        roll = c["RollNo"]
        cat = c["Category"]
        sp3 = c["Special3"]

        best = None

        if roll in opts_by_roll:
            for op in opts_by_roll[roll]:
                dec = decode_opt(op["Optn"])
                if not dec:
                    continue

                kb = (dec["grp"], dec["typ"], dec["college"], dec["course"])
                if kb not in seat_idx:
                    continue

                # category priority: own → PD → SM
                priority = []
                if cat not in ("NA", "", "NULL"):
                    priority.append(cat)
                if sp3 == "PD":
                    priority.append("PD")
                priority.append("SM")

                for sc in priority:
                    kf = (dec["grp"], dec["typ"], dec["college"], dec["course"], sc)
                    if seat_cap.get(kf, 0) <= 0:
                        continue
                    if not eligible_for_seat(sc, cat, sp3):
                        continue

                    best = {
                        "RollNo": roll,
                        "LRank": c["LRank"],
                        "grp": dec["grp"],
                        "typ": dec["typ"],
                        "College": dec["college"],
                        "Course": dec["course"],
                        "SeatCategory": sc,
                        "AllotCode": make_allot_code(dec["grp"], dec["typ"], dec["course"], dec["college"], sc),
                        "OPNO": op["OPNO"],
                    }
                    seat_cap[kf] -= 1
                    break

                if best:
                    break

        # 🔐 PROTECTION RULE
        if best:
            results.append(best)
        elif roll in protected:
            results.append({
                "RollNo": roll,
                "LRank": c["LRank"],
                **protected[roll],
            })

    # =====================================================
    # OUTPUT
    # =====================================================
    df = pd.DataFrame(results)

    st.success(f"✅ Allotted: {len(df)}")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download LLM Allotment",
        buf,
        f"LLM_Phase{phase}_Allotment.csv",
        "text/csv"
    )
