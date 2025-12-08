import streamlit as st
import pandas as pd
from io import BytesIO

# =========================================================
# Helpers
# =========================================================

def read_any(f):
    """Read CSV or Excel with tolerant CSV parsing."""
    name = f.name.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(f)
    return pd.read_csv(f, encoding="ISO-8859-1", on_bad_lines="skip")


# =========================================================
# CATEGORY ELIGIBILITY (UPDATED)
# =========================================================
def eligible_for_category(seat_cat: str, cand_cat: str) -> bool:
    """
    Correct rule:
    1) SM open to all
    2) NA / NULL / NAN / blank → ONLY SM
    3) SC/ST/EZ/MU/EW etc → category + SM
    """
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NULL", "NA", "NAN"):
        cand_cat = "NA"

    # SM is open to everyone
    if seat_cat == "SM":
        return True

    # NA candidates—eligible ONLY for SM
    if cand_cat == "NA":
        return False

    # Others—eligible only for their category (besides SM)
    return seat_cat == cand_cat


# =========================================================
# OPTION DECODER
# =========================================================
def decode_opt(opt: str):
    """
    BLE format:
       0   : grp (B)
       1   : type G/S
       2-3 : course
       4-6 : college
       7.. : flags (ignored)
    """
    opt = str(opt).upper().strip()
    if len(opt) < 7:
        return None
    return {
        "grp": opt[0],
        "typ": opt[1],
        "course": opt[2:4],
        "college": opt[4:7],
        "raw": opt,
    }


def make_allot_code(grp, typ, course, college, category):
    """Final 11-character BLE allotment code."""
    cat2 = category[:2].upper()
    return f"{grp}{typ}{course}{college}{cat2}{cat2}"


# =========================================================
#     B.Pharm Lateral Entry Allotment
# =========================================================
def bpharm_le_allotment():

    st.title("💊 B.Pharm Lateral Entry – Allotment (Gale–Shapley Style)")

    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"], key="ble_cand")
    seat_file = st.file_uploader("2️⃣ Seat Matrix File", type=["csv", "xlsx"], key="ble_seat")
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"], key="ble_opt")

    if not (cand_file and seat_file and opt_file):
        return

    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("✔ Files Loaded Successfully")

    # =====================================================
    # CLEAN SEAT MATRIX
    # =====================================================
    required = ["grp", "typ", "college", "course", "category", "SEAT"]
    for col in required:
        if col not in seats.columns:
            st.error(f"Missing column in Seat Matrix: {col}")
            st.stop()

    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_cap = {}
    seat_index = {}

    for _, r in seats.iterrows():
        full = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        base = (r["grp"], r["typ"], r["college"], r["course"])

        seat_cap[full] = seat_cap.get(full, 0) + r["SEAT"]

        if base not in seat_index:
            seat_index[base] = {}
        seat_index[base][r["category"]] = seat_cap[full]

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["BRank"] = pd.to_numeric(cand.get("BRank", 0), errors="coerce").fillna(9999999).astype(int)
    cand["Category"] = cand.get("Category", "").astype(str).str.upper().str.strip()
    cand["Status"] = cand.get("Status", "").astype(str).str.upper().str.strip()
    cand["EligibleOptn"] = cand.get("EligibleOptn", "").astype(str).str.upper().str.strip()

    # Valid candidate filters
    cand = cand[(cand["BRank"] > 0) & (cand["Status"] != "S")]

    if "EligibleOptn" in cand.columns:
        cand = cand[cand["EligibleOptn"] != "N"]

    cand = cand.sort_values("BRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts["Optn"]   = opts["Optn"].astype(str).str.upper().str.strip()

    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"].astype(str).str.upper() == "Y") &
        (opts["Delflg"].astype(str).str.upper() != "Y")
    ]

    opts = opts.sort_values(["RollNo", "OPNO"])

    # Build option index
    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    st.info(f"Candidates: {len(cand)} | Options: {len(opts)} | Total Seats: {sum(seat_cap.values())}")

    # =====================================================
    #      GALE–SHAPLEY STYLE CANDIDATE PROPOSAL
    # =====================================================
    allotments = []

    for _, C in cand.iterrows():
        roll = C["RollNo"]
        cand_cat = C["Category"]

        if roll not in opts_by_roll:
            continue

        for op in opts_by_roll[roll]:

            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            grp = dec["grp"]
            typ = dec["typ"]
            course = dec["course"]
            college = dec["college"]

            base = (grp, typ, college, course)
            if base not in seat_index:
                continue

            available_cats = seat_index[base]

            # Category priority: own category → SM
            priority = []
            if cand_cat not in ("", "NA", "NULL", "NAN") and cand_cat in available_cats:
                priority.append(cand_cat)
            if "SM" in available_cats:
                priority.append("SM")

            chosen = None

            for sc in priority:
                full_key = (grp, typ, college, course, sc)

                if seat_cap.get(full_key, 0) <= 0:
                    continue

                if not eligible_for_category(sc, cand_cat):
                    continue

                chosen = (sc, full_key)
                break

            if not chosen:
                continue

            sc, full_key = chosen
            seat_cap[full_key] -= 1
            seat_index[base][sc] = seat_cap[full_key]

            allot_code = make_allot_code(grp, typ, course, college, sc)

            allotments.append({
                "RollNo": roll,
                "BRank": C["BRank"],
                "Category": cand_cat,
                "grp": grp,
                "typ": typ,
                "College": college,
                "Course": course,
                "SeatCategory": sc,
                "AllotCode": allot_code,
                "OPNO": op["OPNO"],
            })

            break  # stop after first valid allotment

    # =====================================================
    # OUTPUT
    # =====================================================
    result = pd.DataFrame(allotments)

    st.subheader("🎉 Allotment Completed")
    st.write(f"Total Allotted: **{len(result)}**")

    if not result.empty:
        st.dataframe(result)

        buf = BytesIO()
        result.to_csv(buf, index=False)
        buf.seek(0)

        st.download_button(
            "⬇ Download BLE Allotment",
            buf,
            "BLE_Allotment.csv",
            "text/csv",
        )
    else:
        st.warning("⚠ No candidates allotted — check seat matrix / category rules / options.")
