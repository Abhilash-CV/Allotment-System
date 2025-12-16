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
    LLM option format:
    [0]=grp, [1]=typ, [2:4]=course, [4:7]=college
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
    seat_cat = seat_cat.upper()
    cand_cat = cand_cat.upper()
    special3 = special3.upper()

    # PD seat
    if seat_cat == "PD":
        return special3 == "PD"

    # SM seat
    if seat_cat == "SM":
        return True

    # NA / NULL candidates
    if cand_cat in ("NA", "NULL", ""):
        return False

    # Normal category seat
    return seat_cat == cand_cat


def make_allot_code(grp, typ, course, college, category):
    cat2 = category[:2]
    return f"{grp}{typ}{course}{college}{cat2}{cat2}"


# =========================================================
# MAIN APP
# =========================================================

def llm_allotment():

    st.title("⚖️ LLM Allotment – Gale–Shapley (Rank Based)")

    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv","xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Category File", type=["csv","xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv","xlsx"])

    phase = st.selectbox("Allotment Phase", [1,2,3,4], index=0)

    if not (cand_file and seat_file and opt_file):
        return

    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["LRank"]  = pd.to_numeric(cand["LRank"], errors="coerce").fillna(999999).astype(int)

    for col in ["Category","Special3"]:
        if col not in cand.columns:
            cand[col] = ""
        cand[col] = cand[col].astype(str).str.upper().str.strip()

    # Phase protection
    if phase > 1:
        js_col = f"JOINSTATUS_{phase-1}"
        if js_col in cand.columns:
            cand = cand[~cand[js_col].isin(["N","TC"])]

    cand = cand[cand["LRank"] > 0]
    cand = cand.sort_values("LRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper().str.strip()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y","T"]))
    ].sort_values(["RollNo","OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # =====================================================
    # CLEAN SEATS
    # =====================================================
    for col in ["grp","typ","college","course","category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    seat_index = {}

    for _, r in seats.iterrows():
        k_full = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        k_base = (r["grp"], r["typ"], r["college"], r["course"])

        seat_cap[k_full] = seat_cap.get(k_full, 0) + r["SEAT"]
        seat_index.setdefault(k_base, set()).add(r["category"])

    # =====================================================
    # GALE–SHAPLEY ALLOTMENT
    # =====================================================
    allotments = []

    for _, c in cand.iterrows():
        roll = c["RollNo"]
        if roll not in opts_by_roll:
            continue

        for op in opts_by_roll[roll]:

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            grp, typ, course, college = dec.values()
            base_key = (grp, typ, college, course)

            if base_key not in seat_index:
                continue

            # Category preference
            prefs = []
            if c["Category"] not in ("NA","NULL",""):
                prefs.append(c["Category"])
            if c["Special3"] == "PD":
                prefs.append("PD")
            prefs.append("SM")

            chosen = None

            for sc in prefs:
                full_key = (grp, typ, college, course, sc)
                if seat_cap.get(full_key,0) <= 0:
                    continue
                if not eligible_category(sc, c["Category"], c["Special3"]):
                    continue
                chosen = sc
                break

            if not chosen:
                continue

            seat_cap[(grp,typ,college,course,chosen)] -= 1

            allotments.append({
                "RollNo": roll,
                "LRank": c["LRank"],
                "College": college,
                "Course": course,
                "SeatCategory": chosen,
                "AllotCode": make_allot_code(grp,typ,course,college,chosen),
                "OPNO": op["OPNO"]
            })
            break

    # =====================================================
    # OUTPUT
    # =====================================================
    result = pd.DataFrame(allotments)

    st.success(f"Allotment Completed – {len(result)} candidates allotted")
    st.dataframe(result)

    buf = BytesIO()
    result.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download LLM Allotment",
        buf,
        "LLM_Allotment.csv",
        "text/csv"
    )


# =========================================================
# RUN
# =========================================================
llm_allotment()
