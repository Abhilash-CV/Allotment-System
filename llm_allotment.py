import streamlit as st
import pandas as pd
from io import BytesIO

# =====================================================
# Helpers
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

def eligible_for_seat(seat_cat, cand_cat, special3):
    if seat_cat == "SM":
        return True
    if seat_cat == "PD":
        return special3 == "PD"
    if cand_cat in ("", "NA", "NULL"):
        return False
    return seat_cat == cand_cat

def make_allot_code(g, t, c, col, cat):
    cat2 = cat[:2]
    return f"{g}{t}{c}{col}{cat2}{cat2}"

# =====================================================
# MAIN
# =====================================================

def llm_allotment():

    st.title("⚖️ LLM Allotment – Counselling Logic")

    phase = st.selectbox("Select Phase", [1,2,3,4])

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv","xlsx"])
    opt_file  = st.file_uploader("2️⃣ Option Entry", ["csv","xlsx"])
    seat_file = st.file_uploader("3️⃣ Seat Matrix", ["csv","xlsx"])
    prev_file = st.file_uploader("4️⃣ Previous Allotment", ["csv","xlsx"]) if phase > 1 else None

    if not (cand_file and opt_file and seat_file):
        return

    # ---------------- LOAD ----------------
    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)
    prev  = read_any(prev_file) if prev_file else None

    # ---------------- CANDIDATES ----------------
    cand["Status"] = cand["Status"].astype(str).str.upper().str.strip() if "Status" in cand.columns else ""
    cand = cand[cand["Status"] != "S"]

    if "RollNo" in cand.columns:
        cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    else:
        cand["RollNo"] = 0

    if "LRank" in cand.columns:
        cand["LRank"] = pd.to_numeric(cand["LRank"], errors="coerce").fillna(999999).astype(int)
    else:
        cand["LRank"] = 999999

    cand["Category"] = cand["Category"].astype(str).str.upper().str.strip() if "Category" in cand.columns else ""
    cand["Special3"] = cand["Special3"].astype(str).str.upper().str.strip() if "Special3" in cand.columns else ""

    cand = cand.sort_values("LRank")

    # ---------------- OPTIONS ----------------
    if "RollNo" in opts.columns:
        opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    else:
        opts["RollNo"] = 0

    if "OPNO" in opts.columns:
        opts["OPNO"] = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    else:
        opts["OPNO"] = 0

    opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper() if "ValidOption" in opts.columns else "Y"
    opts["Delflg"] = opts["Delflg"].astype(str).str.upper() if "Delflg" in opts.columns else "N"

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y","T"])) &
        (opts["Delflg"] != "Y")
    ]

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo","OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # ---------------- SEATS ----------------
    for c in ["grp","typ","college","course","category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    for _, r in seats.iterrows():
        k = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_cap[k] = seat_cap.get(k, 0) + r["SEAT"]

    # ---------------- PROTECTED ----------------
    protected = {}
    if prev is not None:
        join_col = f"JoinStatus_{phase-1}"
        op_col   = f"OPNO_{phase-1}"

        for _, r in prev.iterrows():
            code = str(r.get("Curr_Admn","")).upper().strip()
            if len(code) < 9:
                continue
            protected[int(r["RollNo"])] = {
                "grp": code[0],
                "typ": code[1],
                "course": code[2:4],
                "college": code[4:7],
                "cat": code[7:9],
                "opno": int(r.get(op_col,9999)) if str(r.get(op_col,"")).isdigit() else 9999
            }

    # ---------------- PHASE-2 CONFIRM ----------------
    if phase == 2:
        cand["ConfirmFlag"] = cand["ConfirmFlag"].astype(str).str.upper() if "ConfirmFlag" in cand.columns else ""
        cand = cand[
            (cand["ConfirmFlag"] == "Y") |
            (cand["RollNo"].isin(protected))
        ]

    # ---------------- ALLOTMENT ----------------
    results = []

    for _, C in cand.iterrows():
        roll = C["RollNo"]
        allotted = False

        for op in opts_by_roll.get(roll, []):
            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            for (g,t,col,crs,sc), cap in seat_cap.items():
                if cap > 0 and sc == "SM" and (g,t,col,crs) == (dec["grp"],dec["typ"],dec["college"],dec["course"]):
                    seat_cap[(g,t,col,crs,sc)] -= 1
                    results.append({
                        "RollNo": roll,
                        "LRank": C["LRank"],
                        "College": col,
                        "Course": crs,
                        "SeatCategory": sc,
                        "OPNO": op["OPNO"],
                        "AllotCode": make_allot_code(g,t,crs,col,sc)
                    })
                    allotted = True
                    break
            if allotted:
                break

    df = pd.DataFrame(results)
    st.success(f"✅ Phase {phase} Completed")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    st.download_button("⬇ Download Result", buf, f"LLM_Allotment_Phase{phase}.csv", "text/csv")
