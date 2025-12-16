import streamlit as st
import pandas as pd
from io import BytesIO

# =========================================================
# Utility: Safe column getter
# =========================================================
def ensure_col(df, col, default=""):
    if col not in df.columns:
        df[col] = default
    return df


# =========================================================
# Read CSV / Excel safely
# =========================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# =========================================================
# Category Eligibility Rules (LLM)
# =========================================================
def eligible_for_seat(seat_cat, cand_cat, cand_sp3):
    seat_cat = seat_cat.upper().strip()
    cand_cat = cand_cat.upper().strip()
    cand_sp3 = cand_sp3.upper().strip()

    # PD seat
    if seat_cat == "PD":
        return cand_sp3 == "PD"

    # SM seat → open to all
    if seat_cat == "SM":
        return True

    # NA / NULL candidates → ONLY SM
    if cand_cat in ("", "NA", "NULL"):
        return False

    # Category seats
    return seat_cat == cand_cat


# =========================================================
# Decode Option Code (generic)
# grp + typ + course + college
# =========================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) < 6:
        return None
    return {
        "grp": opt[0],
        "typ": opt[1],
        "course": opt[2:4],
        "college": opt[4:7],
    }


# =========================================================
# Allot Code Builder (11-char standard)
# =========================================================
def make_allot_code(grp, typ, course, college, cat):
    c2 = cat[:2]
    return f"{grp}{typ}{course}{college}{c2}{c2}"


# =========================================================
# MAIN LLM ALLOTMENT ENGINE
# =========================================================
def llm_allotment():

    st.title("⚖️ LLM Allotment – Rank-based (Gale–Shapley Style)")

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Option Entry", ["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", ["csv", "xlsx"])
    allo_file = st.file_uploader("4️⃣ Allotment Details (Phase-2+ only)", ["csv", "xlsx"])

    phase = st.selectbox("Allotment Phase", [1, 2, 3, 4], index=0)

    if not (cand_file and opt_file and seat_file):
        return

    # =====================================================
    # LOAD FILES
    # =====================================================
    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)
    allot_prev = read_any(allo_file) if (phase > 1 and allo_file) else None

    st.success("Files loaded")

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    cand = ensure_col(cand, "RollNo", 0)
    cand = ensure_col(cand, "LRank", 999999)
    cand = ensure_col(cand, "Category", "NA")
    cand = ensure_col(cand, "Special3", "")
    cand = ensure_col(cand, "Status", "")

    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["LRank"]  = pd.to_numeric(cand["LRank"], errors="coerce").fillna(999999).astype(int)

    for c in ["Category", "Special3", "Status"]:
        cand[c] = cand[c].astype(str).str.upper().str.strip()

    # Phase protection
    if phase > 1 and allot_prev is not None:
        js_col = f"JoinStatus_{phase-1}"
        allot_prev = ensure_col(allot_prev, js_col, "")
        allot_prev[js_col] = allot_prev[js_col].astype(str).str.upper()

        blocked = allot_prev[
            allot_prev[js_col].isin(["Y", "N", "TC"])
        ]["RollNo"].astype(int)

        cand = cand[~cand["RollNo"].isin(blocked)]

    # Rank order (candidate-proposing)
    cand = cand.sort_values("LRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    opts = ensure_col(opts, "RollNo", 0)
    opts = ensure_col(opts, "OPNO", 0)
    opts = ensure_col(opts, "Optn", "")
    opts = ensure_col(opts, "ValidOption", "Y")
    opts = ensure_col(opts, "Delflg", "")

    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    for c in ["Optn", "ValidOption", "Delflg"]:
        opts[c] = opts[c].astype(str).str.upper().str.strip()

    # ValidOption = Y or T
    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y", "T"])) &
        (opts["Delflg"] != "Y")
    ]

    opts = opts.sort_values(["RollNo", "OPNO"])
    opts_by_roll = opts.groupby("RollNo")

    # =====================================================
    # CLEAN SEATS
    # =====================================================
    for c in ["grp", "typ", "college", "course", "category"]:
        seats = ensure_col(seats, c, "")
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats = ensure_col(seats, "SEAT", 0)
    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    seat_idx = {}

    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        base = (r["grp"], r["typ"], r["college"], r["course"])
        seat_cap[key] = seat_cap.get(key, 0) + r["SEAT"]
        seat_idx.setdefault(base, set()).add(r["category"])

    # =====================================================
    # ALLOTMENT (Gale–Shapley style)
    # =====================================================
    allotments = []

    for _, c in cand.iterrows():
        roll = c["RollNo"]
        cat  = c["Category"]
        sp3  = c["Special3"]

        if roll not in opts_by_roll.groups:
            continue

        for _, op in opts_by_roll.get_group(roll).iterrows():
            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            base = (dec["grp"], dec["typ"], dec["college"], dec["course"])
            if base not in seat_idx:
                continue

            # Seat category priority:
            # 1. PD (if eligible)
            # 2. Candidate category
            # 3. SM
            pref = []
            if sp3 == "PD" and "PD" in seat_idx[base]:
                pref.append("PD")
            if cat not in ("NA", "NULL", "") and cat in seat_idx[base]:
                pref.append(cat)
            if "SM" in seat_idx[base]:
                pref.append("SM")

            chosen = None
            for sc in pref:
                full = (*base, sc)
                if seat_cap.get(full, 0) <= 0:
                    continue
                if not eligible_for_seat(sc, cat, sp3):
                    continue
                chosen = sc
                seat_cap[full] -= 1
                break

            if not chosen:
                continue

            allotments.append({
                "RollNo": roll,
                "LRank": c["LRank"],
                "College": dec["college"],
                "Course": dec["course"],
                "SeatCategory": chosen,
                "AllotCode": make_allot_code(
                    dec["grp"], dec["typ"], dec["course"], dec["college"], chosen
                ),
                "OPNO": op["OPNO"],
                "Phase": phase
            })
            break

    # =====================================================
    # OUTPUT
    # =====================================================
    res = pd.DataFrame(allotments)
    st.subheader("✅ Allotment Result")
    st.write(f"Allotted: **{len(res)}**")

    if res.empty:
        st.warning("No allotments – please verify seat categories and option codes.")
        return

    st.dataframe(res, use_container_width=True)

    buf = BytesIO()
    res.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download LLM Allotment",
        buf,
        f"LLM_Allotment_Phase{phase}.csv",
        "text/csv"
    )
