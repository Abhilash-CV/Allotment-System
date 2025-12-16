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
    """
    LLM option code:
    0-1 : Program+Type (eg LG)
    2-3 : Course
    4-6 : College
    """
    opt = str(opt).upper().strip()
    if len(opt) < 7:
        return None
    return {
        "grp": opt[0],
        "typ": opt[1],
        "course": opt[2:4],
        "college": opt[4:7],
    }


def eligible_category(seat_cat, cand_cat, special3):
    seat_cat = seat_cat.upper().strip()
    cand_cat = cand_cat.upper().strip()
    special3 = special3.upper().strip()

    # PD rule
    if seat_cat == "PD":
        return special3 == "PD"

    # SM open
    if seat_cat == "SM":
        return True

    # NA/NULL only SM
    if cand_cat in ("", "NA", "NULL"):
        return False

    return seat_cat == cand_cat


def make_allot_code(grp, typ, course, college, seat_cat):
    sc = seat_cat[:2].upper()
    return f"{grp}{typ}{course}{college}{sc}{sc}"


# =========================================================
# MAIN LLM ALLOTMENT
# =========================================================

def llm_allotment():

    st.title("⚖️ LLM Allotment – Gale Shapley (Correct & Protected)")

    cand_file = st.file_uploader("1️⃣ Candidates", type=["csv","xlsx"])
    opt_file  = st.file_uploader("2️⃣ Option Entry", type=["csv","xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", type=["csv","xlsx"])
    prev_file = st.file_uploader("4️⃣ Allotment Details (Phase-1 / Prev)", type=["csv","xlsx"])

    if not (cand_file and opt_file and seat_file):
        return

    # -----------------------------------------------------
    # LOAD
    # -----------------------------------------------------
    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)
    prev  = read_any(prev_file) if prev_file else pd.DataFrame()

    # -----------------------------------------------------
    # CLEAN SEATS
    # -----------------------------------------------------
    for c in ["grp","typ","college","course","category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_cap[key] = seat_cap.get(key, 0) + r["SEAT"]

    TOTAL_SEATS = sum(seat_cap.values())

    # -----------------------------------------------------
    # PROTECT PREVIOUS ADMISSIONS (CRITICAL)
    # -----------------------------------------------------
    protected = {}

    if not prev.empty:
        for _, r in prev.iterrows():
            if str(r.get("Curr_Admn","")).strip() == "":
                continue
            if str(r.get("JoinStatus_1","")).upper() != "Y":
                continue

            code = r["Curr_Admn"]
            grp, typ = code[0], code[1]
            course, college = code[2:4], code[4:7]
            seat_cat = code[7:9]

            key = (grp, typ, college, course, seat_cat)

            # deduct physical seat
            if seat_cap.get(key, 0) <= 0:
                continue

            seat_cap[key] -= 1

            protected[int(r["RollNo"])] = {
                "RollNo": int(r["RollNo"]),
                "AllotCode": code,
                "grp": grp,
                "typ": typ,
                "college": college,
                "course": course,
                "SeatCategory": seat_cat,
                "OPNO": r.get("OPNO_1", 0),
            }

    # -----------------------------------------------------
    # CLEAN CANDIDATES
    # -----------------------------------------------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype("Int64")
    cand["Lrank"]  = pd.to_numeric(cand["Lrank"], errors="coerce").fillna(9999999)

    for c in ["Category","Special3","Status","ConfirmFlag"]:
        cand[c] = cand.get(c,"").astype(str).str.upper().str.strip()

    # Phase-2 rule
    cand = cand[
        (cand["Status"] != "S") &
        (cand["ConfirmFlag"] == "Y")
    ].copy()

    cand = cand.sort_values("Lrank")

    # -----------------------------------------------------
    # CLEAN OPTIONS
    # -----------------------------------------------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype("Int64")
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0)

    opts["ValidOption"] = opts.get("ValidOption","Y").astype(str).str.upper()
    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y","T"]))
    ].sort_values(["RollNo","OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(int(r["RollNo"]), []).append(r)

    # -----------------------------------------------------
    # ALLOTMENT ENGINE
    # -----------------------------------------------------
    results = []
    occupied = set()

    for _, c in cand.iterrows():

        roll = int(c["RollNo"])
        cat  = c["Category"]
        sp3  = c["Special3"]

        current = protected.get(roll)
        best = None

        for op in opts_by_roll.get(roll, []):
            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            for seat_cat in seats["category"].unique():

                key = (
                    dec["grp"],
                    dec["typ"],
                    dec["college"],
                    dec["course"],
                    seat_cat
                )

                if seat_cap.get(key, 0) <= 0:
                    continue

                if not eligible_category(seat_cat, cat, sp3):
                    continue

                # upgrade check
                if current and op["OPNO"] >= current["OPNO"]:
                    continue

                best = {
                    "RollNo": roll,
                    "OPNO": op["OPNO"],
                    "grp": dec["grp"],
                    "typ": dec["typ"],
                    "college": dec["college"],
                    "course": dec["course"],
                    "SeatCategory": seat_cat,
                    "AllotCode": make_allot_code(
                        dec["grp"], dec["typ"],
                        dec["course"], dec["college"],
                        seat_cat
                    )
                }
                break

            if best:
                break

        if best:
            seat_cap[(best["grp"],best["typ"],best["college"],best["course"],best["SeatCategory"])] -= 1
            results.append(best)
            occupied.add(roll)
        elif current:
            results.append(current)
            occupied.add(roll)

    # -----------------------------------------------------
    # OUTPUT
    # -----------------------------------------------------
    result_df = pd.DataFrame(results)

    st.subheader("✅ LLM Allotment Result")
    st.write(f"Total Seats        : {TOTAL_SEATS}")
    st.write(f"Final Allotted     : {len(result_df)}")

    st.dataframe(result_df)

    buf = BytesIO()
    result_df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download LLM Allotment",
        buf,
        "LLM_Allotment.csv",
        "text/csv"
    )
