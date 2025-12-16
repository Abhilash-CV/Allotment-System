import streamlit as st
import pandas as pd
from io import BytesIO

# =========================================================
# Helpers
# =========================================================

def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
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


def eligible_for_seat(seat_cat, cand_cat, special3):
    seat_cat = seat_cat.upper()
    cand_cat = cand_cat.upper()

    if seat_cat == "PD":
        return special3 == "PD"

    if seat_cat == "SM":
        return True

    if cand_cat in ("NA", "", "NULL"):
        return False

    return seat_cat == cand_cat


def make_allot_code(grp, typ, course, college, cat):
    cat2 = cat[:2]
    return f"{grp}{typ}{course}{college}{cat2}{cat2}"


# =========================================================
# MAIN ENGINE
# =========================================================

def llm_allotment():

    st.title("⚖️ LLM Allotment – Gale–Shapley (Multi-Phase)")

    phase = st.selectbox("Select Phase", [1, 2, 3, 4], index=0)

    cand_file = st.file_uploader("1️⃣ Candidates", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Option Entry", type=["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Category", type=["csv", "xlsx"])

    allot_file = None
    if phase > 1:
        allot_file = st.file_uploader(
            "4️⃣ Allotment Details (Previous Phase)",
            type=["csv", "xlsx"]
        )

    if not cand_file or not opt_file or not seat_file:
        return

    # ---------------- LOAD ----------------
    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)

    allot_prev = None
    if phase > 1 and allot_file:
        allot_prev = read_any(allot_file)

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    cand["Status"] = cand.get("Status", "").astype(str).str.upper().str.strip()
    cand = cand[cand["Status"] != "S"].copy()   # HARD EXCLUSION

    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["LRank"]  = pd.to_numeric(cand["LRank"], errors="coerce").fillna(999999).astype(int)

    for col in ["Category", "Special3"]:
        cand[col] = cand.get(col, "").astype(str).str.upper().str.strip()

    cand = cand.sort_values("LRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts["ValidOption"] = opts.get("ValidOption", "Y").astype(str).str.upper()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y", "T"])) &
        (opts.get("Delflg", "N").astype(str).str.upper() != "Y")
    ].copy()

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
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
    for _, r in seats.iterrows():
        k = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_cap[k] = seat_cap.get(k, 0) + r["SEAT"]

    # =====================================================
    # PROTECTION (Phase ≥ 2)
    # =====================================================
    protected = {}

    if phase > 1 and allot_prev is not None:

        join_col = f"JoinStatus_{phase-1}"
        op_col   = f"OPNO_{phase-1}"

        for _, r in allot_prev.iterrows():

            if str(r.get("Status", "")).upper() == "S":
                continue

            js = str(r.get(join_col, "")).upper()
            if js not in ("Y", ""):
                continue

            code = str(r.get("Curr_Admn", "")).upper().strip()
            if len(code) < 9:
                continue

            protected[int(r["RollNo"])] = {
                "grp": code[0],
                "typ": code[1],
                "course": code[2:4],
                "college": code[4:7],
                "cat": code[7:9],
                "opno": int(r.get(op_col, 9999))
                if str(r.get(op_col, "")).isdigit() else 9999
            }

    # =====================================================
    # PHASE-2 CONFIRM FLAG + PROTECTION RULE
    # =====================================================
    if phase == 2:
        cand["ConfirmFlag"] = cand.get("ConfirmFlag", "").astype(str).str.upper().str.strip()
        # Keep candidates who either confirmed OR are protected
        cand = cand[
            (cand["ConfirmFlag"] == "Y") |
            (cand["RollNo"].isin(protected.keys()))
        ].copy()

    # =====================================================
    # ALLOTMENT LOOP (GALE–SHAPLEY)
    # =====================================================
    results = []

    for _, C in cand.iterrows():

        roll = C["RollNo"]
        cat  = C["Category"]
        sp3  = C["Special3"]

        current = protected.get(roll)
        best = None

        # ======== Try options first ========
        for op in opts_by_roll.get(roll, []):

            if current and op["OPNO"] >= current["opno"]:
                continue

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            for (g, t, col, crs, sc), cap in seat_cap.items():

                if cap <= 0:
                    continue

                if (g, t, col, crs) != (dec["grp"], dec["typ"], dec["college"], dec["course"]):
                    continue

                if not eligible_for_seat(sc, cat, sp3):
                    continue

                best = (g, t, crs, col, sc, op["OPNO"])
                break

            if best:
                break

        # ======== Allocate seat ========
        if best:
            g, t, crs, col, sc, opno = best
            seat_cap[(g, t, col, crs, sc)] -= 1  # Deduct seat

            results.append({
                "RollNo": roll,
                "LRank": C["LRank"],
                "College": col,
                "Course": crs,
                "SeatCategory": sc,
                "OPNO": opno,
                "AllotCode": make_allot_code(g, t, crs, col, sc)
            })

        # ======== Protected candidate ========
        elif current:
            key = (current["grp"], current["typ"], current["college"], current["course"], current["cat"])
            # Deduct seat if available
            if seat_cap.get(key, 0) > 0:
                seat_cap[key] -= 1

            results.append({
                "RollNo": roll,
                "LRank": C["LRank"],
                "College": current["college"],
                "Course": current["course"],
                "SeatCategory": current["cat"],
                "OPNO": current["opno"],
                "AllotCode": make_allot_code(
                    current["grp"], current["typ"],
                    current["course"], current["college"], current["cat"]
                )
            })

    # =====================================================
    # OUTPUT
    # =====================================================
    df = pd.DataFrame(results)

    st.success(f"✅ Phase {phase} completed")
    st.write(f"Total Allotted: **{len(df)}**")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download Allotment Result",
        buf,
        f"LLM_Allotment_Phase{phase}.csv",
        "text/csv"
    )
