import streamlit as st
import pandas as pd
from io import BytesIO

# =========================================================
# Utility helpers
# =========================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


def ensure_col(df, col, default=""):
    if col not in df.columns:
        df[col] = default
    return df


# =========================================================
# Decode option code (LLM – same structure)
# =========================================================
def decode_opt(opt):
    """
    Expected format (min 7 chars):
    0 : Program (L)
    1 : Type (G/S)
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
        "college": opt[4:7]
    }


# =========================================================
# Eligibility rules
# =========================================================
def eligible_category(seat_cat, cand_cat, special3):
    seat_cat = seat_cat.upper().strip()
    cand_cat = cand_cat.upper().strip()
    special3 = special3.upper().strip()

    # PD seats
    if seat_cat == "PD":
        return special3 == "PD"

    # SM seats open to all
    if seat_cat == "SM":
        return True

    # NA / NULL → only SM
    if cand_cat in ("", "NA", "NULL"):
        return False

    return seat_cat == cand_cat


# =========================================================
# Allotment code (11 char)
# =========================================================
def make_allot_code(grp, typ, course, college, category):
    cat2 = category[:2].upper()
    return f"{grp}{typ}{course}{college}{cat2}{cat2}"


# =========================================================
# MAIN LLM ALLOTMENT ENGINE
# =========================================================
def llm_allotment():

    st.title("⚖️ LLM Allotment – Phase-wise (Gale–Shapley, Protected)")

    phase = st.selectbox("Select Phase", [1, 2, 3, 4], index=0)

    cand_file = st.file_uploader("1️⃣ Candidates", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Option Entry", type=["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", type=["csv", "xlsx"])
    prev_file = None

    if phase > 1:
        prev_file = st.file_uploader("4️⃣ Allotment Details (Previous Phase)", type=["csv", "xlsx"])

    if not (cand_file and opt_file and seat_file):
        return
    if phase > 1 and not prev_file:
        return

    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)
    prev  = read_any(prev_file) if phase > 1 else None

    # =====================================================
    # CLEAN SEATS
    # =====================================================
    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()
    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    seat_index = {}

    for _, r in seats.iterrows():
        full = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        base = (r["grp"], r["typ"], r["college"], r["course"])
        seat_cap[full] = seat_cap.get(full, 0) + r["SEAT"]
        seat_index.setdefault(base, set()).add(r["category"])

    total_seats = sum(seat_cap.values())

    # =====================================================
    # PHASE ≥ 2 : PROTECT EXISTING ADMISSIONS
    # =====================================================
    if phase > 1:
        prev = ensure_col(prev, "Curr_Admn", "")
        protected = prev[prev["Curr_Admn"].astype(str).str.strip() != ""]

        st.info(f"🔒 Protecting existing admissions: {len(protected)}")

        for _, r in protected.iterrows():
            ca = str(r["Curr_Admn"]).strip()
            if len(ca) < 9:
                continue

            grp = ca[0]
            typ = ca[1]
            course = ca[2:4]
            college = ca[4:7]
            cat = ca[7:9]

            key = (grp, typ, college, course, cat)
            if key in seat_cap and seat_cap[key] > 0:
                seat_cap[key] -= 1

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    for c in ["RollNo", "LRank"]:
        cand[c] = pd.to_numeric(cand[c], errors="coerce").fillna(0).astype(int)

    for c in ["Category", "Special3", "Status"]:
        cand = ensure_col(cand, c, "")
        cand[c] = cand[c].astype(str).str.upper().str.strip()

    # Phase blocking
    if phase > 1:
        js = f"JoinStatus_{phase-1}"
        cand = ensure_col(cand, js, "")
        cand = cand[~cand[js].isin(["Y", "N", "TC"])]

    cand = cand[cand["LRank"] > 0]
    cand = cand.sort_values("LRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts["Optn"]   = opts["Optn"].astype(str).str.upper().str.strip()
    opts = ensure_col(opts, "ValidOption", "Y")
    opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper().str.strip()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y", "T"]))
    ].sort_values(["RollNo", "OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # =====================================================
    # ALLOTMENT
    # =====================================================
    allotments = []

    for _, c in cand.iterrows():
        roll = c["RollNo"]
        cat = c["Category"]
        sp3 = c["Special3"]

        if roll not in opts_by_roll:
            continue

        for op in opts_by_roll[roll]:
            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            base = (dec["grp"], dec["typ"], dec["college"], dec["course"])
            if base not in seat_index:
                continue

            priority = []
            if cat not in ("NA", "", "NULL"):
                priority.append(cat)
            if "PD" in seat_index[base]:
                priority.append("PD")
            priority.append("SM")

            chosen = None
            for sc in priority:
                if sc not in seat_index[base]:
                    continue
                key = (*base, sc)
                if seat_cap.get(key, 0) <= 0:
                    continue
                if not eligible_category(sc, cat, sp3):
                    continue
                chosen = sc
                seat_cap[key] -= 1
                break

            if chosen:
                allotments.append({
                    "RollNo": roll,
                    "LRank": c["LRank"],
                    "OPNO": op["OPNO"],
                    "AllotCode": make_allot_code(dec["grp"], dec["typ"], dec["course"], dec["college"], chosen),
                    "SeatCategory": chosen
                })
                break

    # =====================================================
    # OUTPUT
    # =====================================================
    result = pd.DataFrame(allotments)

    st.success(f"✅ Phase {phase} completed")
    st.write(f"Total seats        : {total_seats}")
    st.write(f"Remaining seats    : {sum(seat_cap.values())}")
    st.write(f"New allotments     : {len(result)}")

    st.dataframe(result)

    buf = BytesIO()
    result.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download LLM Allotment",
        buf,
        f"LLM_Phase_{phase}_Allotment.csv",
        "text/csv"
    )
