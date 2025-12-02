import streamlit as st
import pandas as pd
from io import BytesIO

# ----------------------------------------------------------
# Read any data file
# ----------------------------------------------------------
def read_any(file):
    name = file.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(file)
    return pd.read_csv(file, encoding="ISO-8859-1", on_bad_lines="skip")


# ----------------------------------------------------------
# Decode 8-digit PG option
# ----------------------------------------------------------
def decode_opt(opt):
    opt = str(opt).strip().upper()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],          # M
        "typ": opt[1],           # G/S
        "course": opt[2:4],      # 2 chars
        "college": opt[4:7],     # 3 chars
        "flag": opt[7]           # M/Y/R/Q
    }


# ----------------------------------------------------------
# Make final 11-digit allotment code
# ----------------------------------------------------------
def make_allot_code(p, t, c, clg, cat):
    c2 = cat[:2].upper()
    return f"{p}{t}{c}{clg}{c2}{c2}"


# ----------------------------------------------------------
# Special category rules
# ----------------------------------------------------------
def special_ok(seat_cat, flag, cand):
    seat_cat = seat_cat.upper()
    flag = flag.upper()

    nri = cand["NRI"]
    mino = cand["Minority"]
    sp3 = cand["Special3"]
    ccat = cand["Category"]

    # NR, NC, NM
    if seat_cat == "NR":   return (flag == "R" and nri == "NR")
    if seat_cat == "NC":   return (flag == "R" and nri == "NRNC")
    if seat_cat == "NM":   return (flag == "R" and nri == "NM")

    # AC, MM
    if seat_cat == "AC":   return (flag == "Y" and mino == "AC")
    if seat_cat == "MM":   return (flag == "Y" and mino == "MM")

    # PD
    if seat_cat == "PD":   return (sp3 == "PD")

    # CD (only SC + PD)
    if seat_cat == "CD":   return (ccat == "SC" and sp3 == "PD")

    return True


# ----------------------------------------------------------
# Category eligibility check
# ----------------------------------------------------------
def eligible(seat_cat, cand_cat):
    if seat_cat == "SM":
        return True
    if cand_cat in ("", "NULL", "NA"):
        return False
    return seat_cat == cand_cat


# ----------------------------------------------------------
# Main PG Allotment (Optimized)
# ----------------------------------------------------------
def pg_med_allotment():

    st.title("⚡ PG Medical Allotment — FAST ENGINE")

    cand_file = st.file_uploader("Upload Candidates", ["csv","xlsx"])
    seat_file = st.file_uploader("Upload Seat Matrix", ["csv","xlsx"])
    opt_file  = st.file_uploader("Upload Option Entry", ["csv","xlsx"])

    if not(cand_file and seat_file and opt_file):
        return

    # Load data
    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("Files Loaded.")

    # ------------------------------------------------------
    # Prepare Candidates
    # ------------------------------------------------------
    for col in ["RollNo","PRank","STRank","HQ_Rank","MQ_Rank","IQ_Rank"]:
        if col not in cand:
            cand[col] = 0
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)

    cand["Category"]  = cand["Category"].astype(str).str.upper()
    cand["NRI"]       = cand.get("NRI","").astype(str).str.upper()
    cand["Minority"]  = cand.get("Minority","").astype(str).str.upper()
    cand["Special3"]  = cand.get("Special3","").astype(str).str.upper()
    cand["Status"]    = cand.get("Status","").astype(str).str.upper()

    # Remove invalid candidates
    cand = cand[(cand["PRank"]>0) & (cand["Status"]!="S")]
    cand = cand.sort_values("PRank")

    # ------------------------------------------------------
    # Prepare Option Entries (group by RollNo for speed)
    # ------------------------------------------------------
    opts = opts[
        (opts["ValidOption"].astype(str).str.upper()=="Y") &
        (opts["Delflg"].astype(str).str.upper()!="Y")
    ]

    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts["Optn"]   = opts["Optn"].astype(str).str.upper().str.strip()

    # Group options by RollNo → instant lookup
    opt_map = {}
    for _, r in opts.iterrows():
        roll = r["RollNo"]
        if roll not in opt_map:
            opt_map[roll] = []
        opt_map[roll].append((r["OPNO"], decode_opt(r["Optn"])))

    # ------------------------------------------------------
    # Build Seat Map (dictionary only)
    # ------------------------------------------------------
    seats["grp"] = seats["grp"].astype(str).str.upper()
    seats["typ"] = seats["typ"].astype(str).str.upper()
    seats["course"] = seats["course"].astype(str).str.upper()
    seats["college"] = seats["college"].astype(str).str.upper()
    seats["category"] = seats["category"].astype(str).str.upper()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}     # key → seats left
    seat_grp = {}     # (GM, G, CC, CO) → list of categories

    for _, s in seats.iterrows():
        key = (s["grp"], s["typ"], s["college"], s["course"], s["category"])
        seat_map[key] = s["SEAT"]

        gkey = (s["grp"], s["typ"], s["college"], s["course"])
        seat_grp.setdefault(gkey, []).append(s["category"])


    # ------------------------------------------------------
    # FASTEST POSSIBLE LOOP — pure Python, no pandas
    # ------------------------------------------------------
    result = []

    for _, c in cand.iterrows():

        roll = c["RollNo"]
        cand_cat = c["Category"]

        if roll not in opt_map:
            continue

        candidate_opts = opt_map[roll]

        for opno, d in candidate_opts:
            if not d:
                continue

            prog = d["prog"]
            typ = d["typ"]
            course = d["course"]
            college = d["college"]
            flag = d["flag"]

            gkey = (prog+"M", typ, college, course)
            if gkey not in seat_grp:
                continue

            # Priority list
            pr = []
            if cand_cat not in ("", "NA"): pr.append(cand_cat)
            if c["HQ_Rank"] > 0: pr.append("HQ")
            if c["MQ_Rank"] > 0: pr.append("MQ")
            if c["IQ_Rank"] > 0: pr.append("IQ")
            pr.append("SM")

            assigned = False

            # Loop only available category rows for this course/college
            for pcat in pr:
                if pcat not in seat_grp[gkey]:
                    continue

                key = (prog+"M", typ, college, course, pcat)

                if seat_map.get(key,0) <= 0:
                    continue

                # special rules
                if not special_ok(pcat, flag, c):
                    continue

                # category match
                if not eligible(pcat, cand_cat):
                    continue

                # allot seat
                seat_map[key] -= 1

                allot_code = make_allot_code(prog, typ, course, college, pcat)

                result.append({
                    "RollNo": roll,
                    "OPNO": opno,
                    "AllotCode": allot_code,
                    "College": college,
                    "Course": course,
                    "SeatCategory": pcat
                })

                assigned = True
                break

            if assigned:
                break

    # ------------------------------------------------------
    # Output
    # ------------------------------------------------------
    df = pd.DataFrame(result)

    st.success(f"Allotment Completed — {len(df)} allotted")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button("Download PG Allotment", buf, "PG_Allotment.csv")
