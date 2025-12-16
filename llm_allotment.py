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


def eligible(seat_cat, cand_cat, special3):
    seat_cat = seat_cat.upper()
    cand_cat = cand_cat.upper()
    special3 = special3.upper()

    if seat_cat == "PD":
        return special3 == "PD"

    if seat_cat == "SM":
        return True

    if cand_cat in ("", "NA", "NULL"):
        return False

    return seat_cat == cand_cat


def allot_code(grp, typ, course, college, cat):
    c = cat[:2].upper()
    return f"{grp}{typ}{course}{college}{c}{c}"


# =====================================================
# MAIN
# =====================================================
def llm_allotment():

    st.title("⚖️ LLM Counselling – Upgrade Protected")

    phase = st.selectbox("Phase", [1, 2, 3, 4], index=0)

    cand_f = st.file_uploader("Candidates", type=["csv", "xlsx"])
    opt_f  = st.file_uploader("Option Entry", type=["csv", "xlsx"])
    seat_f = st.file_uploader("Seat Matrix", type=["csv", "xlsx"])
    prev_f = None

    if phase > 1:
        prev_f = st.file_uploader("Previous Allotment", type=["csv", "xlsx"])

    if not cand_f or not opt_f or not seat_f:
        return
    if phase > 1 and not prev_f:
        return

    cand = read_any(cand_f)
    opts = read_any(opt_f)
    seats = read_any(seat_f)
    prev = read_any(prev_f) if prev_f else None

    # -------------------------------------------------
    # Seats
    # -------------------------------------------------
    for c in ["grp","typ","college","course","category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()
    seats["SEAT"] = seats["SEAT"].astype(int)

    seat_cap = {}
    for _, r in seats.iterrows():
        k = (r.grp, r.typ, r.college, r.course, r.category)
        seat_cap[k] = seat_cap.get(k, 0) + r.SEAT

    # -------------------------------------------------
    # Previous allotments (for upgrade)
    # -------------------------------------------------
    curr_map = {}
    if phase > 1:
        for _, r in prev.iterrows():
            if not r.get("Curr_Admn"):
                continue
            code = r["Curr_Admn"]
            curr_map[r["RollNo"]] = {
                "grp": code[0],
                "typ": code[1],
                "course": code[2:4],
                "college": code[4:7],
                "cat": code[7:9],
                "opno": r.get(f"OPNO_{phase-1}", 9999)
            }

    # -------------------------------------------------
    # Candidates
    # -------------------------------------------------
    cand["LRank"] = pd.to_numeric(cand["LRank"], errors="coerce")
    cand = cand[cand["LRank"] > 0]
    cand = cand.sort_values("LRank")

    for c in ["Category","Special3"]:
        cand[c] = cand.get(c, "").astype(str).str.upper()

    if phase > 1:
        js = f"JoinStatus_{phase-1}"
        cand = cand[~cand.get(js, "").isin(["N","TC"])]

    # -------------------------------------------------
    # Options
    # -------------------------------------------------
    opts["RollNo"] = opts["RollNo"].astype(int)
    opts["OPNO"] = opts["OPNO"].astype(int)
    opts["Optn"] = opts["Optn"].astype(str).str.upper()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].isin(["Y","T"]))
    ].sort_values(["RollNo","OPNO"])

    opt_map = {}
    for _, r in opts.iterrows():
        opt_map.setdefault(r.RollNo, []).append(r)

    # -------------------------------------------------
    # Allotment
    # -------------------------------------------------
    final = []

    for _, c in cand.iterrows():
        roll = c.RollNo
        cat = c.Category
        sp3 = c.Special3

        current = curr_map.get(roll)
        best_opno = current["opno"] if current else 9999
        best_seat = current

        for op in opt_map.get(roll, []):
            if op.OPNO >= best_opno:
                break

            d = decode_opt(op.Optn)
            if not d:
                continue

            for seat_cat in seats[
                (seats.grp == d["grp"]) &
                (seats.typ == d["typ"]) &
                (seats.college == d["college"]) &
                (seats.course == d["course"])
            ]["category"]:

                key = (d["grp"], d["typ"], d["college"], d["course"], seat_cat)
                if seat_cap.get(key, 0) <= 0:
                    continue
                if not eligible(seat_cat, cat, sp3):
                    continue

                # Upgrade
                if current:
                    old_key = (
                        current["grp"], current["typ"],
                        current["college"], current["course"],
                        current["cat"]
                    )
                    seat_cap[old_key] += 1

                seat_cap[key] -= 1
                best_seat = {
                    "grp": d["grp"],
                    "typ": d["typ"],
                    "course": d["course"],
                    "college": d["college"],
                    "cat": seat_cat,
                    "opno": op.OPNO
                }
                break
            if best_seat != current:
                break

        if best_seat:
            final.append({
                "RollNo": roll,
                "LRank": c.LRank,
                "OPNO": best_seat["opno"],
                "AllotCode": allot_code(
                    best_seat["grp"],
                    best_seat["typ"],
                    best_seat["course"],
                    best_seat["college"],
                    best_seat["cat"]
                )
            })

    # -------------------------------------------------
    # Output
    # -------------------------------------------------
    df = pd.DataFrame(final)

    st.success(f"Allotted: {len(df)}")
    st.dataframe(df)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "Download Allotment",
        buf,
        f"LLM_Phase_{phase}_Final.csv",
        "text/csv"
    )
