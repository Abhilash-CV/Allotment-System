import streamlit as st
import pandas as pd
from io import BytesIO

# ======================================================
# SAFE FILE READER
# ======================================================
def read_any(f):
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")

# ======================================================
# COLUMN RESOLVER (CRITICAL FIX)
# ======================================================
def resolve_column(df, possible_names, label):
    for c in possible_names:
        if c in df.columns:
            return c
    st.error(f"❌ Required column not found for: {label}\nTried: {possible_names}")
    st.stop()

# ======================================================
# OPTION DECODER
# ======================================================
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

# ======================================================
# ELIGIBILITY
# ======================================================
def eligible(seat_cat, cand_cat, special3):
    seat_cat = str(seat_cat).upper()
    cand_cat = str(cand_cat).upper()

    if cand_cat in ("", "NA", "NULL"):
        cand_cat = "NA"

    if seat_cat == "SM":
        return True
    if seat_cat == "PD":
        return special3 == "PD"
    if cand_cat == "NA":
        return False
    return seat_cat == cand_cat

# ======================================================
# ALLOT CODE (11 CHAR)
# ======================================================
def make_allot_code(grp, typ, course, college, cat):
    c = cat[:2]
    return f"{grp}{typ}{course}{college}{c}{c}"

# ======================================================
# MAIN ENGINE
# ======================================================
def llm_allotment():

    st.title("⚖️ LLM Allotment – Phase-aware (Corrected)")

    phase = st.selectbox("Select Phase", [1, 2, 3, 4])

    cand_file = st.file_uploader("Candidates", ["csv", "xlsx"])
    opt_file  = st.file_uploader("Option Entry", ["csv", "xlsx"])
    seat_file = st.file_uploader("Seat Category", ["csv", "xlsx"])
    allot_file = None

    if phase > 1:
        allot_file = st.file_uploader("Allotment Details (Previous Phase)", ["csv", "xlsx"])

    if not (cand_file and opt_file and seat_file):
        return

    cand = read_any(cand_file)
    opts = read_any(opt_file)
    seats = read_any(seat_file)
    allot_prev = read_any(allot_file) if allot_file else None

    # ==================================================
    # RESOLVE SEAT COLUMNS (FIX FOR YOUR ERROR)
    # ==================================================
    col_grp      = resolve_column(seats, ["grp", "Grp", "GROUP"], "Seat Group")
    col_typ      = resolve_column(seats, ["typ", "Type", "CollegeType"], "Seat Type")
    col_college  = resolve_column(seats, ["college", "CollegeCode"], "College Code")
    col_course   = resolve_column(seats, ["course", "CourseCode"], "Course Code")
    col_cat      = resolve_column(seats, ["category", "Category", "SeatCategory"], "Seat Category")
    col_seat     = resolve_column(seats, ["SEAT", "Seat", "SeatCount"], "Seat Count")

    seats = seats.rename(columns={
        col_grp: "grp",
        col_typ: "typ",
        col_college: "college",
        col_course: "course",
        col_cat: "category",
        col_seat: "SEAT"
    })

    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0)

    seat_map = {}
    for _, r in seats.iterrows():
        key = (r.grp, r.typ, r.college, r.course, r.category)
        seat_map[key] = seat_map.get(key, 0) + r.SEAT

    # ==================================================
    # CANDIDATES
    # ==================================================
    col_roll = resolve_column(cand, ["RollNo", "ROLLNO"], "RollNo")
    col_rank = resolve_column(cand, ["LRank", "LRANK"], "LRank")

    cand["RollNo"] = pd.to_numeric(cand[col_roll], errors="coerce")
    cand["LRank"]  = pd.to_numeric(cand[col_rank], errors="coerce").fillna(9999999)

    cand["Category"] = cand.get("Category", "NA").astype(str).str.upper()
    cand["Special3"] = cand.get("Special3", "").astype(str).str.upper()

    cand = cand[cand["LRank"] > 0].sort_values("LRank")

    # ==================================================
    # OPTION ENTRY
    # ==================================================
    opts["RollNo"] = pd.to_numeric(resolve_column(opts, ["RollNo","ROLLNO"], "Opt RollNo"), errors="coerce")
    opts["OPNO"] = pd.to_numeric(resolve_column(opts, ["OPNO"], "OPNO"), errors="coerce")

    opts["ValidOption"] = opts.get("ValidOption","Y").astype(str).str.upper()
    opts["Delflg"] = opts.get("Delflg","").astype(str).str.upper()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y","T"])) &
        (opts["Delflg"] != "Y")
    ].sort_values(["RollNo","OPNO"])

    opts_by_roll = opts.groupby("RollNo")

    # ==================================================
    # PROTECTION (PHASE >1)
    # ==================================================
    protected = {}
    if phase > 1:
        js = f"JoinStatus_{phase-1}"
        allot_prev[js] = allot_prev[js].astype(str).str.upper()

        joined = allot_prev[allot_prev[js] == "Y"]
        for _, r in joined.iterrows():
            protected[r.RollNo] = r.Curr_Admn

        blocked = allot_prev[allot_prev[js].isin(["N","TC"])]["RollNo"]
        cand = cand[~cand.RollNo.isin(blocked)]

    # ==================================================
    # ALLOTMENT
    # ==================================================
    results = []

    for _, c in cand.iterrows():
        roll = c.RollNo
        cat  = c.Category
        sp3  = c.Special3

        if roll not in opts_by_roll.groups:
            continue

        for _, op in opts_by_roll.get_group(roll).iterrows():

            dec = decode_opt(op.Optn)
            if not dec:
                continue

            for seat_cat in ["PD", cat, "SM"]:

                key = (dec["grp"], dec["typ"], dec["college"], dec["course"], seat_cat)
                if seat_map.get(key, 0) <= 0:
                    continue

                if not eligible(seat_cat, cat, sp3):
                    continue

                seat_map[key] -= 1
                results.append({
                    "RollNo": roll,
                    "LRank": c.LRank,
                    "AllotCode": make_allot_code(dec["grp"],dec["typ"],dec["course"],dec["college"],seat_cat),
                    "SeatCategory": seat_cat,
                    "OPNO": op.OPNO,
                    "Phase": phase
                })
                break
            else:
                continue
            break

    # ==================================================
    # OUTPUT
    # ==================================================
    df = pd.DataFrame(results)
    st.success(f"✅ Allotted: {len(df)}")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇ Download LLM Allotment",
        buf,
        f"LLM_Allotment_Phase_{phase}.csv",
        "text/csv"
    )
