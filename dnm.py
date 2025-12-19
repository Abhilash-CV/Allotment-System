# dnm.py
import streamlit as st
import pandas as pd
from io import BytesIO

# =====================================================
# HELPERS
# =====================================================

def read_any(file):
    if file.name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    return pd.read_csv(file, encoding="ISO-8859-1", on_bad_lines="skip")

def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) < 7:
        return None
    return opt[0], opt[1], opt[2:4], opt[4:7]

# =====================================================
# MAIN FUNCTION
# =====================================================

def dnm_allotment():

    st.title("🎓 DNM Allotment – HQ / MQ / IQ")

    phase = st.selectbox("Phase", [1, 2, 3, 4])

    cand_file = st.file_uploader("1️⃣ Candidates", ["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix", ["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry", ["csv", "xlsx"])
    prev_file = st.file_uploader("4️⃣ Previous Allotment", ["csv", "xlsx"]) if phase > 1 else None

    if not (cand_file and seat_file and opt_file):
        return

    # =====================================================
    # LOAD FILES
    # =====================================================
    cand  = read_any(cand_file)
    seats = read_any(seat_file)
    opts  = read_any(opt_file)
    prev  = read_any(prev_file) if prev_file else None

    # =====================================================
    # BASIC CANDIDATE CLEAN
    # =====================================================
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)

    if "Status" in cand.columns:
        cand["Status"] = cand["Status"].astype(str).str.upper().str.strip()
        cand = cand[cand["Status"] != "S"]

    # -----------------------------------------------------
    # STRICT RANK NORMALISATION
    # -----------------------------------------------------
    for r in ["HQ_Rank", "MQ_Rank", "IQ_Rank"]:
        if r not in cand.columns:
            cand[r] = -1
        else:
            cand[r] = pd.to_numeric(cand[r], errors="coerce").fillna(-1).astype(int)

    # =====================================================
    # BUILD BLOCKED + PROTECTED FROM PREVIOUS ALLOTMENT
    # (SOURCE OF TRUTH)
    # =====================================================
    blocked = {}
    protected = {}

    join_col = {
        2: "JoinStatus_1",
        3: "JoinStatus_2",
        4: "JoinStatus_3"
    }.get(phase)

    if prev is not None:
        for _, r in prev.iterrows():

            roll = int(r.get("RollNo", 0))
            js = ""

            if join_col and join_col in prev.columns:
                js = str(r.get(join_col, "")).upper().strip()

            code = str(r.get("Curr_Admn", "")).upper().strip()

            # 🚫 BLOCK: Non-joined candidates
            if js == "N":
                blocked[roll] = f"{join_col} = N (Non-joined in previous phase)"
                continue

            # 🛡️ PROTECT: Joined candidates with current admission
            if len(code) >= 9:
                protected[roll] = {
                    "grp": code[0],
                    "typ": code[1],
                    "course": code[2:4],
                    "college": code[4:7],
                    "quota": code[7:9]
                }

    protected_retained = set(protected.keys())

    # =====================================================
    # REMOVE BLOCKED FROM ELIGIBILITY
    # =====================================================
    cand["BlockedReason"] = ""
    cand.loc[cand["RollNo"].isin(blocked), "BlockedReason"] = cand["RollNo"].map(blocked)

    eligible = cand[~cand["RollNo"].isin(blocked)].copy()

    # =====================================================
    # CONFIRM FLAG FILTER (PHASE > 1)
    # =====================================================
    if phase > 1:
        if "ConfirmFlag" not in eligible.columns:
            eligible["ConfirmFlag"] = ""
        else:
            eligible["ConfirmFlag"] = eligible["ConfirmFlag"].astype(str).str.upper().str.strip()

        eligible = eligible[
            (eligible["ConfirmFlag"] == "Y") |
            (eligible["RollNo"].isin(protected))
        ]

    # =====================================================
    # OPTIONS
    # =====================================================
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    if "ValidOption" not in opts.columns:
        opts["ValidOption"] = "Y"
    if "Delflg" not in opts.columns:
        opts["Delflg"] = "N"

    opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper()
    opts["Delflg"]      = opts["Delflg"].astype(str).str.upper()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y", "T"])) &
        (opts["Delflg"] != "Y")
    ].sort_values(["RollNo", "OPNO"])

    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # =====================================================
    # SEAT MATRIX
    # =====================================================
    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    for _, r in seats.iterrows():
        k = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_cap[k] = seat_cap.get(k, 0) + r["SEAT"]

    # =====================================================
    # ALLOTMENT ENGINE (STRICT HQ / MQ / IQ)
    # =====================================================
    rounds = [
        ("HQ", "HQ_Rank"),
        ("MQ", "MQ_Rank"),
        ("IQ", "IQ_Rank"),
    ]

    results = []
    allotted = set()

    for quota, rank_col in rounds:
        for _, C in eligible.sort_values(rank_col).iterrows():

            roll = C["RollNo"]
            rank_val = int(C[rank_col])

            if rank_val <= 0:
                continue
            if roll in allotted:
                continue

            for op in opts_by_roll.get(roll, []):
                dec = decode_opt(op["Optn"])
                if not dec:
                    continue

                g, t, crs, col = dec
                seat_key = (g, t, col, crs, quota)

                if seat_cap.get(seat_key, 0) > 0:
                    seat_cap[seat_key] -= 1
                    allotted.add(roll)
                    protected_retained.discard(roll)

                    results.append({
                        "RollNo": roll,
                        "Quota": quota,
                        "College": col,
                        "Course": crs,
                        "RankUsed": rank_val,
                        "BlockedReason": ""
                    })
                    break

    # =====================================================
    # RETAIN PROTECTED CANDIDATES
    # =====================================================
    for roll in protected_retained:
        p = protected[roll]
        results.append({
            "RollNo": roll,
            "Quota": p["quota"],
            "College": p["college"],
            "Course": p["course"],
            "RankUsed": "RETAINED",
            "BlockedReason": ""
        })

    # =====================================================
    # ADD BLOCKED CANDIDATES (AUDIT)
    # =====================================================
    for roll, reason in blocked.items():
        results.append({
            "RollNo": roll,
            "Quota": "",
            "College": "",
            "Course": "",
            "RankUsed": "",
            "BlockedReason": reason
        })

    # =====================================================
    # OUTPUT
    # =====================================================
    df = pd.DataFrame(results)

    st.success(
        f"✅ Phase {phase} completed — "
        f"{len(df[df['BlockedReason'] == ''])} allotted/retained, "
        f"{len(blocked)} blocked"
    )

    st.dataframe(df, use_container_width=True)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download Result (with BlockedReason)",
        buf,
        f"DNM_Allotment_Phase{phase}_FINAL.csv",
        "text/csv"
    )
