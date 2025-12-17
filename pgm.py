import streamlit as st
import pandas as pd
from io import BytesIO
from collections import defaultdict

# =====================================================
# FILE READER
# =====================================================
def read_any(f):
    if f.name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")

# =====================================================
# OPTION DECODER (8 CHAR)
# =====================================================
def decode_opt(opt):
    opt = str(opt).upper().strip()
    if len(opt) != 8:
        return None
    return {
        "prog": opt[0],      # M
        "typ": opt[1],       # G / S
        "course": opt[2:4],
        "college": opt[4:7],
        "flag": opt[7],      # M / Y / R / N
    }

# =====================================================
# ALLOTMENT CODE
# =====================================================
def make_allot_code(prog, typ, course, college, cat):
    c2 = cat[:2]
    return f"{prog}{typ}{course}{college}{c2}{c2}"

# =====================================================
# BASIC CATEGORY CHECK
# =====================================================
def eligible_category(seat_cat, cand_cat):
    seat_cat = seat_cat.upper()
    cand_cat = cand_cat.upper()

    if seat_cat in ("SM", "HQ", "MQ", "IQ"):
        return True
    if cand_cat in ("", "NA", "NULL"):
        return False
    return seat_cat == cand_cat

# =====================================================
# SPECIAL RULES
# =====================================================
def passes_special(seat_cat, flag, c):
    seat_cat = seat_cat.upper()
    flag = flag.upper()

    if seat_cat == "PD":
        return c.Special3 == "PD"

    if seat_cat == "CD":
        return c.Category == "SC" and c.Special3 == "PD"

    if seat_cat in ("AC", "MM"):
        return flag == "Y" and c.Minority == seat_cat

    if seat_cat == "NR":
        return flag == "R" and c.NRI in ("NR", "NRI-NR")

    if seat_cat == "NC":
        return flag == "R" and c.NRI == "NRNC"

    if seat_cat == "NM":
        return flag == "R" and c.NRI == "NRNM"

    return True

# =====================================================
# MAIN APP
# =====================================================
def pg_med_allotment():

    st.title("🩺 PG Medical Allotment – Manual-Equivalent Engine")

    cand_file = st.file_uploader("Candidates", ["csv", "xlsx"])
    seat_file = st.file_uploader("Seat Matrix", ["csv", "xlsx"])
    opt_file  = st.file_uploader("Options", ["csv", "xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts  = read_any(opt_file)

    # -------------------------------------------------
    # NORMALISE CANDIDATES
    # -------------------------------------------------
    for col in ["RollNo", "PRank"]:
        cand[col] = pd.to_numeric(cand.get(col, 0), errors="coerce").fillna(0).astype(int)

    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank"]:
        cand[col] = pd.to_numeric(cand.get(col, 0), errors="coerce").fillna(0).astype(int)

    for col in ["Category", "Minority", "NRI", "Special3", "Status"]:
        cand[col] = cand.get(col, "").astype(str).str.upper().str.strip()

    cand = cand[(cand.PRank > 0) & (cand.Status != "S")]
    cand = cand.sort_values("PRank")
    cand_rows = list(cand.itertuples(index=False))

    # -------------------------------------------------
    # NORMALISE OPTIONS
    # -------------------------------------------------
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    opts = opts[
        (opts.OPNO > 0) &
        (opts.ValidOption.astype(str).str.upper() == "Y") &
        (opts.Delflg.astype(str).str.upper() != "Y")
    ]

    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()
    opts = opts.sort_values(["RollNo", "OPNO"])

    opts_by_roll = defaultdict(list)
    for r in opts.itertuples(index=False):
        opts_by_roll[r.RollNo].append(r)

    # -------------------------------------------------
    # NORMALISE SEATS
    # -------------------------------------------------
    for c in ["grp", "typ", "course", "college", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = defaultdict(int)
    seat_groups = defaultdict(set)

    for r in seats.itertuples(index=False):
        key = (r.grp, r.typ, r.course, r.college, r.category)
        seat_map[key] += r.SEAT
        seat_groups[(r.grp, r.typ, r.course, r.college)].add(r.category)

    # -------------------------------------------------
    # ALLOTMENT
    # -------------------------------------------------
    results = []

    for c in cand_rows:

        for op in opts_by_roll.get(c.RollNo, []):

            dec = decode_opt(op.Optn)
            if not dec:
                continue

            grp = "PG" + dec["prog"]
            typ = dec["typ"]
            course = dec["course"]
            college = dec["college"]
            flag = dec["flag"]

            base = (grp, typ, course, college)
            if base not in seat_groups:
                continue

            priority = []

            # --- HQ/MQ/IQ preference if flag=M
            if flag == "M":
                if c.HQ_Rank > 0: priority.append("HQ")
                if c.MQ_Rank > 0: priority.append("MQ")
                if c.IQ_Rank > 0: priority.append("IQ")

            # --- Community
            if c.Category in seat_groups[base]:
                priority.append(c.Category)

            # --- HQ/MQ/IQ fallback
            if c.HQ_Rank > 0: priority.append("HQ")
            if c.MQ_Rank > 0: priority.append("MQ")
            if c.IQ_Rank > 0: priority.append("IQ")

            # --- Special seats
            for sc in ["PD", "CD", "AC", "MM", "NR", "NC", "NM"]:
                if sc in seat_groups[base]:
                    priority.append(sc)

            # --- SM last
            if "SM" in seat_groups[base]:
                priority.append("SM")

            # remove duplicates, preserve order
            priority = list(dict.fromkeys(priority))

            for sc in priority:
                skey = (grp, typ, course, college, sc)
                if seat_map[skey] <= 0:
                    continue
                if not eligible_category(sc, c.Category):
                    continue
                if not passes_special(sc, flag, c):
                    continue

                seat_map[skey] -= 1
                results.append({
                    "RollNo": c.RollNo,
                    "OPNO": op.OPNO,
                    "College": college,
                    "Course": course,
                    "SeatCategory": sc,
                    "AllotCode": make_allot_code(dec["prog"], typ, course, college, sc)
                })
                break
            else:
                continue
            break

    # -------------------------------------------------
    # OUTPUT
    # -------------------------------------------------
    df = pd.DataFrame(results)
    st.success(f"Total Allotted: {len(df)}")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    st.download_button("Download Allotment CSV", buf, "PG_Medical_Allotment.csv")


if __name__ == "__main__":
    pg_med_allotment()
