import streamlit as st
import pandas as pd
from io import BytesIO

# =====================================================
# UNIVERSAL FILE READER
# =====================================================
def read_any(file):
    name = file.name.lower()
    file.seek(0)

    if name.endswith(".csv"):
        return pd.read_csv(file, encoding="ISO-8859-1")

    if name.endswith(".xlsx") or name.endswith(".xls"):
        try:
            return pd.read_excel(file)
        except:
            return pd.read_csv(file, encoding="ISO-8859-1")

    return pd.read_csv(file, encoding="ISO-8859-1")


# =====================================================
# CATEGORY ELIGIBILITY
# =====================================================
def category_eligible(seat_cat, cand_cat):
    seat_cat = str(seat_cat).strip().upper()
    cand_cat = str(cand_cat or "").strip().upper()

    if seat_cat in ["AM", "SM"]:
        return True

    if cand_cat in ["", "NA", "NULL", "N/A"]:
        return False

    return seat_cat == cand_cat


# =====================================================
# JOINSTATUS COLUMN BY PHASE
# =====================================================
def joinstatus_col(phase):
    return {
        "PHASE2": "JOINSTATUS_1",
        "PHASE3": "JOINSTATUS_2",
        "PHASE4": "JOINSTATUS_3",
    }.get(phase)


# =====================================================
# PHASE ELIGIBILITY (FINAL)
# =====================================================
def is_candidate_eligible(row, phase):

    curr_admn = str(row.get("Curr_Admn", "")).strip()

    # CURRENT ADMISSION → ALWAYS PROTECTED
    if curr_admn != "":
        return True

    # Phase-1 → everyone eligible
    if phase == "PHASE1":
        return True

    # Phase-wise JoinStatus exclusion
    js = joinstatus_col(phase)
    if js:
        if str(row.get(js, "")).strip().upper() == "N":
            return False

    return True


# =====================================================
# OPTION DECODER
# =====================================================
def decode_opt(opt):
    opt = str(opt).strip().upper()
    if len(opt) < 7:
        return None
    return opt[0], opt[1], opt[2:4], opt[4:7]


# =====================================================
# MAIN APP
# =====================================================
def dnm_allotment():

    st.title("🧮 DNM Admission Allotment – Multi Phase")

    phase = st.selectbox(
        "Select Allotment Phase",
        ["PHASE1", "PHASE2", "PHASE3", "PHASE4"]
    )

    cand_file = st.file_uploader("1️⃣ Candidates File", ["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix File", ["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry File", ["csv", "xlsx"])

    prev_allot_file = None
    allotdet_file  = None

    if phase != "PHASE1":
        prev_allot_file = st.file_uploader(
            "4️⃣ Previous Phase Allotment Result", ["csv", "xlsx"]
        )
        allotdet_file = st.file_uploader(
            "5️⃣ Allotment Details File", ["csv", "xlsx"]
        )

    if not (cand_file and seat_file and opt_file):
        return

    if phase != "PHASE1" and not (prev_allot_file and allotdet_file):
        st.warning("Previous allotment & allotmentdetails required")
        return

    # ---------------- LOAD FILES ----------------
    cand  = read_any(cand_file)
    seats = read_any(seat_file)
    opts  = read_any(opt_file)

    prev_allot = None
    allotdet   = None

    if prev_allot_file:
        prev_allot = read_any(prev_allot_file)

    if allotdet_file:
        allotdet = read_any(allotdet_file)

    # ---------------- NORMALIZE CANDIDATES ----------------
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype("Int64")
    cand["ARank"]  = pd.to_numeric(cand["ARank"], errors="coerce").fillna(9999999)
    cand["Category"] = cand.get("Category", "")

    # Merge allotmentdetails
    if allotdet is not None:
        allotdet["RollNo"] = pd.to_numeric(
            allotdet["RollNo"], errors="coerce"
        ).astype("Int64")

        cand = cand.merge(allotdet, on="RollNo", how="left")

    # ---------------- ELIGIBILITY FILTER ----------------
    cand = cand[cand.apply(
        lambda r: is_candidate_eligible(r, phase),
        axis=1
    )]

    # ---------------- PROTECTED FIRST ----------------
    protected = cand[
        cand["Curr_Admn"].astype(str).str.strip().ne("")
    ].sort_values("ARank")

    fresh = cand[
        cand["Curr_Admn"].astype(str).str.strip().eq("")
    ].sort_values("ARank")

    cand_sorted = pd.concat([protected, fresh], ignore_index=True)

    # ---------------- CLEAN OPTIONS ----------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype("Int64")
    opts["OPNO"] = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0)

    opts = opts[
        (opts["OPNO"] != 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ].sort_values(["RollNo", "OPNO"])

    # ---------------- CLEAN SEATS ----------------
    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}
    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_map[key] = seat_map.get(key, 0) + r["SEAT"]

    # ---------------- REDUCE SEATS (PREVIOUS PHASE) ----------------
    if prev_allot is not None and not prev_allot.empty:
        for _, r in prev_allot.iterrows():
            key = (
                r["grp"], r["typ"],
                r["College"], r["Course"],
                r["SeatCategoryAllotted"]
            )
            if key in seat_map:
                seat_map[key] = max(0, seat_map[key] - 1)

    # ---------------- RUN ALLOTMENT ----------------
    allotments = []

    for _, c in cand_sorted.iterrows():

        roll  = int(c["RollNo"])
        arank = int(c["ARank"])
        ccat  = str(c["Category"]).upper().strip()

        # Current admission seat (if any)
        current_seat_key = None
        if str(c.get("Curr_Admn","")).strip():
            parts = str(c["Curr_Admn"]).split("|")
            if len(parts) == 5:
                current_seat_key = tuple(p.upper().strip() for p in parts)

        c_opts = opts[opts["RollNo"] == roll]
        if c_opts.empty:
            continue

        for _, op in c_opts.iterrows():

            decoded = decode_opt(op["Optn"])
            if not decoded:
                continue

            og, otyp, ocourse, oclg = decoded

            seat_rows = seats[
                (seats["grp"] == og) &
                (seats["typ"] == otyp) &
                (seats["college"] == oclg) &
                (seats["course"] == ocourse)
            ]

            if seat_rows.empty:
                continue

            priority = ["AM", "SM"] + sorted(
                set(seat_rows["category"]) - {"AM", "SM"}
            )

            chosen_key = None
            chosen_cat = None

            for cat in priority:
                for _, sr in seat_rows[seat_rows["category"] == cat].iterrows():

                    key = (
                        sr["grp"], sr["typ"],
                        sr["college"], sr["course"], sr["category"]
                    )

                    if seat_map.get(key, 0) <= 0:
                        continue

                    if category_eligible(sr["category"], ccat):
                        chosen_key = key
                        chosen_cat = sr["category"]
                        break

                if chosen_key:
                    break

            if chosen_key:

                # UPGRADE → RELEASE OLD SEAT
                if current_seat_key:
                    seat_map[current_seat_key] = seat_map.get(
                        current_seat_key, 0
                    ) + 1

                seat_map[chosen_key] -= 1

                allotments.append({
                    "Phase": phase,
                    "RollNo": roll,
                    "ARank": arank,
                    "CandidateCategory": ccat,
                    "grp": og,
                    "typ": otyp,
                    "College": oclg,
                    "Course": ocourse,
                    "SeatCategoryAllotted": chosen_cat
                })
                break

    # ---------------- RESULT ----------------
    result_df = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Result")
    st.write(f"Total Allotted in {phase}: **{len(result_df)}**")
    st.dataframe(result_df)

    buffer = BytesIO()
    result_df.to_csv(buffer, index=False)
    buffer.seek(0)

    st.download_button(
        f"⬇️ Download {phase} Result",
        buffer,
        f"DNM_{phase}_allotment_result.csv",
        "text/csv"
    )


# =====================================================
# RUN
# =====================================================
dnm_allotment()
