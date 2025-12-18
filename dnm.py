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

def make_allot_code(g, t, crs, col, cat):
    c2 = cat[:2]
    return f"{g}{t}{crs}{col}{c2}{c2}"

# =====================================================
# MAIN APP
# =====================================================
def dnm_allotment():

    st.title("🧮 DNM Admission Allotment (Phase-wise)")

    phase = st.selectbox("Select Phase", [1, 2, 3, 4])

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv", "xlsx"])
    opt_file  = st.file_uploader("2️⃣ Options", ["csv", "xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", ["csv", "xlsx"])
    allot_file = st.file_uploader("4️⃣ Allotment Details", ["csv", "xlsx"]) if phase > 1 else None

    if not (cand_file and opt_file and seat_file):
        return

    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)
    allot = read_any(allot_file) if allot_file else None

    # =====================================================
    # PHASE-1 → USE ORIGINAL LOGIC (UNCHANGED)
    # =====================================================
    if phase == 1:
        st.info("Running Phase-1 logic")

        cand["ARank"] = pd.to_numeric(cand["ARank"], errors="coerce").fillna(9999999)
        cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype("Int64")
        cand = cand.sort_values("ARank")

        opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype("Int64")
        opts = opts[
            (opts["OPNO"] != 0) &
            (opts["ValidOption"].astype(str).str.upper() == "Y") &
            (opts["Delflg"].astype(str).str.upper() != "Y")
        ].sort_values(["RollNo", "OPNO"])

        for c in ["grp", "typ", "college", "course", "category"]:
            seats[c] = seats[c].astype(str).str.upper().str.strip()
        seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0)

        seat_cap = {}
        for _, r in seats.iterrows():
            k = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
            seat_cap[k] = seat_cap.get(k, 0) + r["SEAT"]

        results = []

        for _, C in cand.iterrows():
            for _, op in opts[opts["RollNo"] == C["RollNo"]].iterrows():
                dec = decode_opt(op["Optn"])
                if not dec:
                    continue

                g, t, crs, col = dec["grp"], dec["typ"], dec["course"], dec["college"]

                seat_rows = seats[
                    (seats["grp"] == g) &
                    (seats["typ"] == t) &
                    (seats["college"] == col) &
                    (seats["course"] == crs)
                ]

                for _, sr in seat_rows.iterrows():
                    k = (g, t, col, crs, sr["category"])
                    if seat_cap.get(k, 0) > 0 and category_eligible(sr["category"], C["Category"]):
                        seat_cap[k] -= 1
                        results.append({
                            "RollNo": C["RollNo"],
                            "ARank": C["ARank"],
                            "College": col,
                            "Course": crs,
                            "SeatCategory": sr["category"]
                        })
                        break
                else:
                    continue
                break

        df = pd.DataFrame(results)
        st.success(f"Phase-1 completed — {len(df)} seats allotted")
        st.dataframe(df)
        return

    # =====================================================
    # PHASE-2+ → LLM-STYLE PROTECTED ENGINE (ADAPTED)
    # =====================================================
    st.info("Running Phase-2+ protected allotment logic")

    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype(int)
    cand["ARank"] = pd.to_numeric(cand["ARank"], errors="coerce").fillna(9999999)
    cand["Category"] = cand["Category"].astype(str).str.upper().str.strip()

    allot["RollNo"] = pd.to_numeric(allot["RollNo"], errors="coerce").astype(int)
    cand = cand.merge(allot, on="RollNo", how="left")

    # JoinStatus logic
    js_col = f"JoinStatus_{phase-1}"
    if js_col in cand.columns:
        cand = cand[
            (cand[js_col].astype(str).str.upper() != "N") |
            (cand["Curr_Admn"].astype(str).str.strip() != "")
        ]

    # Protected candidates
    protected = {}
    for _, r in cand.iterrows():
        code = str(r.get("Curr_Admn", "")).strip().upper()
        if len(code) >= 9:
            protected[r["RollNo"]] = {
                "grp": code[0],
                "typ": code[1],
                "course": code[2:4],
                "college": code[4:7],
                "cat": code[7:9]
            }

    # Seats
    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()
    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0)

    seat_cap = {}
    for _, r in seats.iterrows():
        k = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_cap[k] = seat_cap.get(k, 0) + r["SEAT"]

    # Reduce seats using Allot_(phase-1)
    allot_col = f"Allot_{phase-1}"
    if allot_col in cand.columns:
        for _, r in cand[cand[allot_col].astype(str).str.strip() != ""].iterrows():
            code = r[allot_col]
            if len(code) >= 9:
                k = (code[0], code[1], code[4:7], code[2:4], code[7:9])
                if k in seat_cap:
                    seat_cap[k] -= 1

    # Options
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype(int)
    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper().isin(["Y", "T"])) &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ].sort_values(["RollNo", "OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    results = []

    for _, C in cand.sort_values("ARank").iterrows():
        roll = C["RollNo"]
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
                if not category_eligible(sc, C["Category"]):
                    continue

                seat_cap[(kg, kt, kcol, kcrs, sc)] -= 1
                results.append({
                    "RollNo": roll,
                    "ARank": C["ARank"],
                    "College": col,
                    "Course": crs,
                    "SeatCategory": sc
                })
                break
            else:
                continue
            break

    df = pd.DataFrame(results)
    st.success(f"Phase {phase} completed — {len(df)} seats allotted")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    st.download_button("⬇ Download Result", buf, f"DNM_Phase{phase}_Result.csv", "text/csv")

# =====================================================
# RUN
# =====================================================
dnm_allotment()
