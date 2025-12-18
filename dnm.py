import streamlit as st
import pandas as pd
from io import BytesIO

# =====================================================
# COMMON HELPERS
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

def category_eligible(seat_cat, cand_cat):
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if seat_cat in ("AM", "SM"):
        return True
    if cand_cat in ("", "NA", "NULL"):
        return False
    return seat_cat == cand_cat

# =====================================================
# MAIN APP
# =====================================================
def dnm_allotment():

    st.title("🧮 DNM Admission Allotment (Final – Phase-wise)")

    phase = st.selectbox("Select Phase", [1, 2, 3, 4])

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Options", ["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", ["csv", "xlsx"])
    allot_file = st.file_uploader(
        "4️⃣ Allotment Details", ["csv", "xlsx"]
    ) if phase > 1 else None

    if not (cand_file and opt_file and seat_file):
        return
    if phase > 1 and not allot_file:
        return

    # =====================================================
    # LOAD FILES
    # =====================================================
    cand  = read_any(cand_file)
    opts  = read_any(opt_file)
    seats = read_any(seat_file)
    allot = read_any(allot_file) if allot_file else None

    # =====================================================
    # NORMALIZE CANDIDATES
    # =====================================================
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["ARank"]  = pd.to_numeric(cand["ARank"], errors="coerce").fillna(9999999)
    cand["Category"] = cand.get("Category", "").astype(str).str.upper().str.strip()

    cand = cand.sort_values("ARank")

    # =====================================================
    # NORMALIZE OPTIONS
    # =====================================================
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts["ValidOption"] = opts.get("ValidOption", "Y").astype(str).str.upper()
    opts["Delflg"] = opts.get("Delflg", "N").astype(str).str.upper()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y", "T"])) &
        (opts["Delflg"] != "Y")
    ].sort_values(["RollNo", "OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # =====================================================
    # NORMALIZE SEATS
    # =====================================================
    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    for _, r in seats.iterrows():
        k = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_cap[k] = seat_cap.get(k, 0) + r["SEAT"]

    # =====================================================
    # PHASE-2+ : MERGE ALLOTMENT DETAILS
    # =====================================================
    if phase > 1:
        allot["RollNo"] = pd.to_numeric(allot["RollNo"], errors="coerce").fillna(0).astype(int)
        cand = cand.merge(allot, on="RollNo", how="left")

        # ---------- JoinStatus filter (GUARDED) ----------
        js_col = f"JoinStatus_{phase-1}"
        if js_col in cand.columns:
            cand = cand[
                (cand[js_col].astype(str).str.upper() != "N") |
                (cand["Curr_Admn"].astype(str).str.strip() != "")
            ]

    # =====================================================
    # PHASE-2+ : REDUCE SEATS USING Allot_(phase-1)
    # (SAFE – no string slicing)
    # =====================================================
    if phase > 1:
        allot_col = f"Allot_{phase-1}"
        if allot_col in cand.columns:
            for _, r in cand[cand[allot_col].astype(str).str.strip() != ""].iterrows():
                dec = decode_opt(r[allot_col])
                if not dec:
                    continue
                g, t, crs, col = dec["grp"], dec["typ"], dec["course"], dec["college"]

                for (kg, kt, kcol, kcrs, sc), cap in seat_cap.items():
                    if cap <= 0:
                        continue
                    if (kg, kt, kcol, kcrs) == (g, t, col, crs):
                        seat_cap[(kg, kt, kcol, kcrs, sc)] -= 1
                        break

    # =====================================================
    # ALLOTMENT
    # =====================================================
    results = []

    for _, C in cand.iterrows():
        roll = C["RollNo"]
        cat  = C["Category"]

        for op in opts_by_roll.get(roll, []):
            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            g, t, crs, col = dec["grp"], dec["typ"], dec["course"], dec["college"]

            for (kg, kt, kcol, kcrs, sc), cap in seat_cap.items():
                if cap <= 0:
                    continue
                if (kg, kt, kcol, kcrs) != (g, t, col, crs):
                    continue
                if not category_eligible(sc, cat):
                    continue

                seat_cap[(kg, kt, kcol, kcrs, sc)] -= 1
                results.append({
                    "Phase": phase,
                    "RollNo": roll,
                    "ARank": C["ARank"],
                    "College": col,
                    "Course": crs,
                    "SeatCategory": sc,
                    "OPNO": op["OPNO"]
                })
                break
            else:
                continue
            break

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
        f"DNM_Phase{phase}_Result.csv",
        "text/csv"
    )

# =====================================================
# RUN
# =====================================================
dnm_allotment()
