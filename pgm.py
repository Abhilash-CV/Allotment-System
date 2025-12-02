import streamlit as st
import pandas as pd
from io import BytesIO

# ---------------------------------------------------------
# FAST File Reader
# ---------------------------------------------------------
def read_any(f):
    n = f.name.lower()
    if n.endswith(".xlsx") or n.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# ---------------------------------------------------------
# Community Eligibility  (special seats bypass)
# ---------------------------------------------------------
def eligible_category(seat_cat, cand_cat):
    seat_cat = seat_cat.upper()
    cand_cat = cand_cat.upper()

    if cand_cat in ("", "NULL", "NA"):
        cand_cat = "NA"

    # Special categories handled in passes_special_rules()
    if seat_cat in ("NR", "NC", "NM", "AC", "MM", "PD", "CD"):
        return True

    if seat_cat == "SM":
        return True

    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


# ---------------------------------------------------------
# Special Rules
# ---------------------------------------------------------
def passes_special_rules(seat_cat, flag, C):
    seat_cat = seat_cat.upper()
    flag = flag.upper()

    nri  = C["NRI"]
    mino = C["Minority"]
    sp3  = C["Special3"]
    cat  = C["Category"]

    if seat_cat == "NR":  return (flag == "R" and nri == "NR")
    if seat_cat == "NC":  return (flag == "R" and nri == "NRNC")
    if seat_cat == "NM":  return (flag == "R" and nri == "NM")

    if seat_cat == "AC":  return (flag == "Y" and mino == "AC")
    if seat_cat == "MM":  return (flag == "Y" and mino == "MM")

    if seat_cat == "PD":  return (sp3 == "PD")

    if seat_cat == "CD":  return (cat == "SC" and sp3 == "PD")

    return True


# ---------------------------------------------------------
# Decode Option Code
# ---------------------------------------------------------
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],
        "typ": opt[1],
        "course": opt[2:4],
        "college": opt[4:7],
        "flag": opt[7],
    }


# ---------------------------------------------------------
# Make Allot Code (11-digit)
# ---------------------------------------------------------
def make_allot_code(prog, typ, course, college, cat):
    cat2 = cat[:2]
    return f"{prog}{typ}{course}{college}{cat2}{cat2}"


# ---------------------------------------------------------
# MAIN ENGINE (SUPER FAST)
# ---------------------------------------------------------
def pg_med_allotment():

    st.title("⚡ Ultra-Fast PG Medical Allotment Engine")

    cand_f = st.file_uploader("1️⃣ Candidates File", type=["csv","xlsx"])
    seat_f = st.file_uploader("2️⃣ Seat Matrix File", type=["csv","xlsx"])
    opt_f  = st.file_uploader("3️⃣ Option Entry File", type=["csv","xlsx"])

    if not (cand_f and seat_f and opt_f):
        return

    # LOAD
    cand = read_any(cand_f)
    seats = read_any(seat_f)
    opts = read_any(opt_f)

    st.success("Files Loaded")

    # -----------------------------------------------------
    # CLEAN CANDIDATES
    # -----------------------------------------------------
    numeric = ["RollNo","PRank","HQ_Rank","MQ_Rank","IQ_Rank","STRank"]
    for col in numeric:
        if col not in cand:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    cand["Category"] = cand["Category"].astype(str).str.upper()
    cand["NRI"] = cand.get("NRI", "").astype(str).str.upper()
    cand["Minority"] = cand.get("Minority", "").astype(str).str.upper()
    cand["Special3"] = cand.get("Special3", "").astype(str).str.upper()
    cand["Status"] = cand.get("Status", "").astype(str).str.upper()

    cand = cand[(cand["PRank"] > 0) & (cand["Status"] != "S")]
    cand = cand.sort_values("PRank")

    # -----------------------------------------------------
    # CLEAN OPTIONS
    # -----------------------------------------------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ]
    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo","OPNO"])

    # FAST INDEX: options per candidate
    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # -----------------------------------------------------
    # CLEAN & INDEX SEATS (SUPER FAST LOOKUP)
    # -----------------------------------------------------
    for col in ["grp","typ","course","college","category"]:
        seats[col] = seats[col].astype(str).str.upper()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_index = {}

    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["course"], r["college"])
        seat_index.setdefault(key, {})
        seat_index[key][r["category"]] = seat_index[key].get(r["category"], 0) + r["SEAT"]

    # -----------------------------------------------------
    # ALLOTMENT ENGINE (Optimized)
    # -----------------------------------------------------
    allot = []

    for _, C in cand.iterrows():

        roll = C["RollNo"]
        cat  = C["Category"]

        if roll not in opts_by_roll:
            continue

        for op in opts_by_roll[roll]:

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            prog, typ, course, college, flag = (
                dec["prog"], dec["typ"], dec["course"], dec["college"], dec["flag"]
            )

            seat_key = (prog + "M", typ, course, college)

            if seat_key not in seat_index:
                continue

            category_map = seat_index[seat_key]

            # Priority list
            priority = []
            if cat not in ("NA","NULL",""): priority.append(cat)
            if C["HQ_Rank"] > 0: priority.append("HQ")
            if C["MQ_Rank"] > 0: priority.append("MQ")
            if C["IQ_Rank"] > 0: priority.append("IQ")
            priority.append("SM")

            chosen = None

            for sc in priority:

                if sc not in category_map: continue
                if category_map[sc] <= 0: continue
                if not passes_special_rules(sc, flag, C): continue
                if not eligible_category(sc, cat): continue

                chosen = sc
                break

            if chosen is None:
                continue

            # Reduce seat
            category_map[chosen] -= 1

            allot_code = make_allot_code(prog, typ, course, college, chosen)

            allot.append({
                "RollNo": roll,
                "OPNO": op["OPNO"],
                "AllotCode": allot_code,
                "College": college,
                "Course": course,
                "SeatCategory": chosen,
            })

            break  # Stop after first allotment

    # -----------------------------------------------------
    # OUTPUT
    # -----------------------------------------------------
    result = pd.DataFrame(allot)
    st.success(f"Allotted: {len(result)}")
    st.dataframe(result)

    buf = BytesIO()
    result.to_csv(buf, index=False)
    buf.seek(0)
    st.download_button("⬇ Download Result", buf, "PG_Allotment.csv", "text/csv")
