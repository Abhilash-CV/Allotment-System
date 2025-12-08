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


def decode_opt(opt: str):
    """
    Decode option code: similar to your PG/DNM pattern.

    Indexing:
        0 : program group (e.g. 'B')
        1 : type         (e.g. 'G'/'S')
        2-3 : course     (2 chars)
        4-6 : college    (3 chars)
        7+ : flags (ignored here)
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


def eligible_for_category(seat_cat: str, cand_cat: str) -> bool:
    """
    Simple category eligibility:
      - SM open to all.
      - NA/null/"" candidates → only SM.
      - Others → their own category + SM.
    """
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NULL", "NA"):
        cand_cat = "NA"

    if seat_cat == "SM":
        return True

    if cand_cat == "NA":
        return False

    return seat_cat == cand_cat


def make_allot_code(grp, typ, course, college, category):
    """
    Allot code pattern (11 chars, consistent with your style):
      grp(1) + typ(1) + course(2) + college(3) + category(2) repeated
    e.g.  B G VL KKM SM SM → BGVLKKMSMSM
    """
    cat2 = str(category).upper().strip()[:2]
    return f"{grp}{typ}{course}{college}{cat2}{cat2}"


# =========================================================
# MAIN: B.Pharm Lateral Entry Allotment
# =========================================================

def bpharm_le_allotment():
    st.title("💊 B.Pharm Lateral Entry – Allotment (Gale–Shapley style)")

    st.markdown("Upload the three CSV/Excel files:")

    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"], key="bpl_cand")
    seat_file = st.file_uploader("2️⃣ Seat Matrix File", type=["csv", "xlsx"], key="bpl_seat")
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"], key="bpl_opt")

    if not (cand_file and seat_file and opt_file):
        return

    # ---------------- Load -----------------
    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("✅ Files loaded")

    # =====================================================
    # CLEAN SEAT MATRIX
    # =====================================================
    required_seat_cols = ["grp", "typ", "college", "course", "category", "SEAT"]
    for col in required_seat_cols:
        if col not in seats.columns:
            st.error(f"Seat file missing column: {col}")
            st.stop()

    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    # Build seat capacity index: key = (grp, typ, college, course, category)
    seat_cap = {}
    # Also index by (grp, typ, college, course) → available categories dict
    seat_index = {}

    for _, r in seats.iterrows():
        key_full = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        key_base = (r["grp"], r["typ"], r["college"], r["course"])
        seat_cap[key_full] = seat_cap.get(key_full, 0) + r["SEAT"]

        if key_base not in seat_index:
            seat_index[key_base] = {}
        seat_index[key_base][r["category"]] = seat_cap[key_full]

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    if "RollNo" not in cand.columns or "BRank" not in cand.columns:
        st.error("Candidate file must have 'RollNo' and 'BRank' columns.")
        st.stop()

    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["BRank"]  = pd.to_numeric(cand["BRank"], errors="coerce").fillna(9999999).astype(int)

    if "Category" not in cand.columns:
        cand["Category"] = ""

    for col in ["Category", "Minority", "Status", "EligibleOptn", "ConfirmFlag"]:
        if col in cand.columns:
            cand[col] = cand[col].astype(str).str.upper().str.strip()
        else:
            cand[col] = ""

    # Filter candidates:
    # - BRank > 0
    # - if EligibleOptn exists, keep only 'Y'
    # - if Status column has 'S' (similar to PG), we can exclude them
    mask = cand["BRank"] > 0
    if "EligibleOptn" in cand.columns:
        mask &= (cand["EligibleOptn"] != "N")
    if "Status" in cand.columns:
        mask &= (cand["Status"] != "S")
    cand = cand[mask].copy()

    # Candidate ordering = BRank ascending (best rank proposes first)
    cand = cand.sort_values("BRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    if "RollNo" not in opts.columns or "OPNO" not in opts.columns or "Optn" not in opts.columns:
        st.error("Option file must have 'RollNo', 'OPNO', and 'Optn' columns.")
        st.stop()

    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)

    for col in ["ValidOption", "Delflg", "Optn"]:
        if col not in opts.columns:
            if col == "ValidOption":
                opts[col] = "Y"
            else:
                opts[col] = ""
        opts[col] = opts[col].astype(str).str.upper().str.strip()

    # Valid options only
    opts = opts[
        (opts["OPNO"] > 0) &
        (opts["ValidOption"] == "Y") &
        (opts["Delflg"] != "Y")
    ].copy()

    # Sort by (RollNo, OPNO) = preference order
    opts = opts.sort_values(["RollNo", "OPNO"])

    # Index options by candidate for fast access
    opts_by_roll = {}
    for _, r in opts.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    st.info(f"Candidates considered: {len(cand)} | Options: {len(opts)} | Seat slots: {sum(seat_cap.values())}")

    # =====================================================
    # GALE–SHAPLEY-STYLE ALLOTMENT
    # (Candidate-proposing, but with fixed seat capacity)
    # =====================================================
    allotments = []

    for _, C in cand.iterrows():
        roll = C["RollNo"]
        cand_cat = C["Category"]

        if roll not in opts_by_roll:
            continue

        cand_opts = opts_by_roll[roll]

        for op in cand_opts:
            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            grp    = dec["grp"]
            typ    = dec["typ"]
            course = dec["course"]
            college = dec["college"]

            base_key = (grp, typ, college, course)
            if base_key not in seat_index:
                continue

            # Category priority:
            #   1. Candidate's own category (if not NA/NULL)
            #   2. SM
            # (We *could* add more fallbacks, but this is common rule)
            categories_here = seat_index[base_key]
            priority = []

            if cand_cat not in ("", "NA", "NULL") and cand_cat in categories_here:
                priority.append(cand_cat)
            if "SM" in categories_here:
                priority.append("SM")

            # Try categories in order
            chosen_cat = None
            chosen_full_key = None

            for sc in priority:
                full_key = (grp, typ, college, course, sc)
                if seat_cap.get(full_key, 0) <= 0:
                    continue
                if not eligible_for_category(sc, cand_cat):
                    continue
                chosen_cat = sc
                chosen_full_key = full_key
                break

            if not chosen_cat:
                # No suitable seat for this option; move to next option
                continue

            # Allot this candidate to this seat
            seat_cap[chosen_full_key] -= 1
            seat_index[base_key][chosen_cat] = seat_cap[chosen_full_key]

            allot_code = make_allot_code(grp, typ, course, college, chosen_cat)

            allotments.append({
                "RollNo": roll,
                "BRank": C["BRank"],
                "Category": cand_cat,
                "grp": grp,
                "typ": typ,
                "College": college,
                "Course": course,
                "SeatCategory": chosen_cat,
                "AllotCode": allot_code,
                "OPNO": op["OPNO"],
            })

            # Candidate stops after first successful seat (candidate-optimal)
            break

    # =====================================================
    # OUTPUT
    # =====================================================
    result = pd.DataFrame(allotments)

    st.subheader("✅ Allotment Result")
    st.write(f"Total Allotted: **{len(result)}**")

    if not result.empty:
        st.dataframe(result)

        buf = BytesIO()
        result.to_csv(buf, index=False)
        buf.seek(0)

        st.download_button(
            "⬇ Download B.Pharm Lateral Entry Allotment",
            buf,
            "BPharm_LE_Allotment.csv",
            "text/csv",
        )
    else:
        st.warning("No candidates were allotted. Please check category codes, option codes and seat matrix consistency.")
