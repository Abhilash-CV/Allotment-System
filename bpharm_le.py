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
# CATEGORY ELIGIBILITY  (Case C + SM priority)
# =========================================================
def eligible_for_category(seat_cat: str, cand_cat: str) -> bool:
    """
    Case C:
      • Seat category is fixed.
      • SC seat → only SC candidate
      • EZ seat → only EZ candidate
      • SM seat → anybody
      • NA/NULL/NAN candidate → only SM
      • Other categories (SC, ST, EZ, MU, EW, …) → can take their own category + SM
    """
    seat_cat = str(seat_cat).upper().strip()
    cand_cat = str(cand_cat).upper().strip()

    if cand_cat in ("", "NULL", "NA", "NAN"):
        cand_cat = "NA"

    # SM seat: open to all, including NA
    if seat_cat == "SM":
        return True

    # NA candidates → only SM, cannot occupy any reserved category seat
    if cand_cat == "NA":
        return False

    # Other community candidates → only their own category (SC→SC, EZ→EZ, etc.)
    return seat_cat == cand_cat


# =========================================================
# Decode Option Code
# =========================================================
def decode_opt(opt: str):
    """
    BLE option pattern (like your other programs):

      index 0 : grp (e.g. 'B')
      index 1 : typ ('G' / 'S')
      2-3     : course (2 chars)
      4-6     : college (3 chars)
      7+      : flags (ignored for BLE)

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
    """
    11-char final allot code:
        grp(1) + typ(1) + course(2) + college(3) + category(2) twice
    Example:
        BGVLKKMSMSM
    """
    cat2 = str(category).upper().strip()[:2]
    return f"{grp}{typ}{course}{college}{cat2}{cat2}"


# =========================================================
# Build Preferences + Stable Matching (Gale–Shapley)
# =========================================================
def build_preferences(cand_df, opts_df, seats_df):
    """
    Build:
      prefs[roll]      = ordered list of seat_keys in preference order
                         seat_key = (grp, typ, college, course, category)
      seat_cap[seat]   = capacity (SEAT)
      rank[roll]       = BRank (lower better)
    """

    # ---------- Clean seats ----------
    for col in ["grp", "typ", "college", "course", "category"]:
        seats_df[col] = seats_df[col].astype(str).str.upper().str.strip()
    seats_df["SEAT"] = pd.to_numeric(seats_df["SEAT"], errors="coerce").fillna(0).astype(int)

    # seat capacity map
    seat_cap = {}
    # base key (grp, typ, college, course) → set of categories
    base_to_cats = {}

    for _, r in seats_df.iterrows():
        full_key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        base_key = (r["grp"], r["typ"], r["college"], r["course"])

        seat_cap[full_key] = seat_cap.get(full_key, 0) + r["SEAT"]
        base_to_cats.setdefault(base_key, set()).add(r["category"])

    # ---------- Index options by candidate ----------
    opts_by_roll = {}
    for _, r in opts_df.iterrows():
        opts_by_roll.setdefault(r["RollNo"], []).append(r)

    # Sort options by OPNO inside each candidate → preference order
    for roll in opts_by_roll:
        opts_by_roll[roll].sort(key=lambda row: row["OPNO"])

    # ---------- Build preferences ----------
    prefs = {}
    rank = {}

    for _, c in cand_df.iterrows():
        roll = c["RollNo"]
        brank = int(c["BRank"])
        rank[roll] = brank

        cand_cat = str(c.get("Category", "")).upper().strip()
        if roll not in opts_by_roll:
            continue

        pref_list = []
        seen_seats = set()

        for op in opts_by_roll[roll]:
            dec = decode_opt(op["Optn"])
            if not dec:
                continue

            grp = dec["grp"]
            typ = dec["typ"]
            course = dec["course"]
            college = dec["college"]

            base_key = (grp, typ, college, course)
            if base_key not in base_to_cats:
                continue

            cats_here = list(base_to_cats[base_key])

            # Category ordering for this *option*:
            #   1) SM (open seat) first
            #   2) then candidate's own category (SC, EZ, MU…)
            #   3) then any others (but eligibility will filter them)
            def cat_priority(cat):
                cat_u = cat.upper()
                if cat_u == "SM":
                    return 0
                if cat_u == cand_cat and cat_u not in ("", "NA", "NULL", "NAN"):
                    return 1
                return 2

            cats_here.sort(key=cat_priority)

            for sc in cats_here:
                full_key = (grp, typ, college, course, sc)
                if full_key in seen_seats:
                    continue
                if seat_cap.get(full_key, 0) <= 0:
                    continue
                if not eligible_for_category(sc, cand_cat):
                    continue

                seen_seats.add(full_key)
                pref_list.append(full_key)

        if pref_list:
            prefs[roll] = pref_list

    return prefs, seat_cap, rank


def stable_allocation(prefs, seat_cap, rank):
    """
    Gale–Shapley stable matching for college admission (capacitated):

      • prefs[roll] is candidate preference list over seat_keys
      • seat_cap[seat_key] is number of slots
      • rank[roll] is BRank; lower is better (seat preference over candidates)

    Result:
      assignments: dict[seat_key] -> list[roll]
    """
    assignments = {k: [] for k in seat_cap}
    next_prop_index = {roll: 0 for roll in prefs}
    free_candidates = list(prefs.keys())

    def worst_candidate(c_list):
        return max(c_list, key=lambda r: rank.get(r, 10**9))

    while free_candidates:
        roll = free_candidates.pop()
        pref = prefs[roll]

        # Try next seats in preference list until placed or exhausted
        while next_prop_index[roll] < len(pref):
            seat_key = pref[next_prop_index[roll]]
            next_prop_index[roll] += 1

            cap = seat_cap[seat_key]
            current = assignments[seat_key]

            # Free slot available → accept
            if len(current) < cap:
                current.append(roll)
                break

            # Seat is full → may replace worst if this candidate is better
            worst = worst_candidate(current)
            if rank.get(roll, 10**9) < rank.get(worst, 10**9):
                current.remove(worst)
                current.append(roll)
                # Evicted candidate gets back to free list if they still have remaining prefs
                if next_prop_index[worst] < len(prefs[worst]):
                    free_candidates.append(worst)
                break
            # else: seat prefers its current candidates → try next seat in prefs

        # If candidate exhausted prefs → remains unmatched

    return assignments


# =========================================================
#      Streamlit BLE Page
# =========================================================
def bpharm_le_allotment():
    st.title("💊 B.Pharm Lateral Entry – Gale–Shapley Allotment (BRank-based)")

    st.markdown("Upload the three input files:")

    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"], key="ble_cand")
    seat_file = st.file_uploader("2️⃣ Seat Matrix File", type=["csv", "xlsx"], key="ble_seat")
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"], key="ble_opt")

    if not (cand_file and seat_file and opt_file):
        return

    # ---------- Load ----------
    cand = read_any(cand_file)
    seats = read_any(seat_file)
    opts = read_any(opt_file)

    st.success("✔ Files loaded successfully")

    # =====================================================
    # CLEAN CANDIDATES
    # =====================================================
    if "RollNo" not in cand.columns or "BRank" not in cand.columns:
        st.error("Candidate file must contain 'RollNo' and 'BRank' columns.")
        return

    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").fillna(0).astype(int)
    cand["BRank"]  = pd.to_numeric(cand["BRank"], errors="coerce").fillna(9999999).astype(int)

    if "Category" not in cand.columns:
        cand["Category"] = ""

    # Normalise commonly used control columns
    for col in ["Category", "Minority", "Status", "EligibleOptn"]:
        if col in cand.columns:
            cand[col] = cand[col].astype(str).str.upper().str.strip()
        else:
            cand[col] = ""

    # Filters:
    #   • BRank > 0
    #   • Status != 'S'
    #   • EligibleOptn != 'N' (if present)
    mask = cand["BRank"] > 0
    if "Status" in cand.columns:
        mask &= (cand["Status"] != "S")
    if "EligibleOptn" in cand.columns:
        mask &= (cand["EligibleOptn"] != "N")

    cand = cand[mask].copy()
    # ordering: best rank first
    cand = cand.sort_values("BRank")

    # =====================================================
    # CLEAN OPTIONS
    # =====================================================
    required_opt_cols = {"RollNo", "OPNO", "Optn", "ValidOption", "Delflg"}
    missing = required_opt_cols - set(opts.columns)
    if missing:
        st.error(f"Option Entry file missing columns: {', '.join(missing)}")
        return

    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").fillna(0).astype(int)
    opts["OPNO"]   = pd.to_numeric(opts["OPNO"], errors="coerce").fillna(0).astype(int)
    opts["Optn"]   = opts["Optn"].astype(str).str.upper().str.strip()

    opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper().str.strip()
    opts["Delflg"]      = opts["Delflg"].astype(str).str.upper().str.strip()

    opts = opts[
        (opts["RollNo"] > 0) &
        (opts["OPNO"] > 0) &
        (opts["ValidOption"] == "Y") &
        (opts["Delflg"] != "Y")
    ].copy()

    opts = opts.sort_values(["RollNo", "OPNO"])

    st.info(f"Candidates considered: {len(cand)} | Options: {len(opts)} | Total seats: {seats['SEAT'].sum()}")

    # =====================================================
    # BUILD PREFS + RUN GALE–SHAPLEY
    # =====================================================
    prefs, seat_cap, rank = build_preferences(cand, opts, seats)
    st.write(f"Candidates with at least one eligible preference: **{len(prefs)}**")

    assignments = stable_allocation(prefs, seat_cap, rank)

    # -----------------------------------------------------
    # Pre-index OPNO for (RollNo, grp, typ, college, course)
    # -----------------------------------------------------
    op_index = {}
    for _, r in opts.iterrows():
        dec = decode_opt(r["Optn"])
        if not dec:
            continue
        key = (r["RollNo"], dec["grp"], dec["typ"], dec["college"], dec["course"])
        opno = int(r["OPNO"])
        if key not in op_index or opno < op_index[key]:
            op_index[key] = opno

    # =====================================================
    # BUILD RESULT
    # =====================================================
    records = []
    for seat_key, rlist in assignments.items():
        grp, typ, college, course, seat_cat = seat_key
        for roll in rlist:
            row = cand[cand["RollNo"] == roll].head(1)
            brank = int(row["BRank"].iloc[0]) if not row.empty else None
            cand_cat = row["Category"].iloc[0] if not row.empty else ""

            opno = op_index.get((roll, grp, typ, college, course), None)
            allot_code = make_allot_code(grp, typ, course, college, seat_cat)

            records.append({
                "RollNo": roll,
                "BRank": brank,
                "CandidateCategory": cand_cat,
                "grp": grp,
                "typ": typ,
                "College": college,
                "Course": course,
                "SeatCategory": seat_cat,
                "OPNO": opno,
                "AllotCode": allot_code,
            })

    result = pd.DataFrame(records).sort_values(["BRank", "RollNo"])

    st.subheader("✅ BLE Allotment (Stable, BRank-based)")
    st.write(f"Total Allotted: **{len(result)}**")

    if not result.empty:
        st.dataframe(result, use_container_width=True)

        buf = BytesIO()
        result.to_csv(buf, index=False)
        buf.seek(0)

        st.download_button(
            "⬇ Download BPharm LE Allotment CSV",
            buf,
            "BPharm_LE_Allotment.csv",
            "text/csv",
        )
    else:
        st.warning("No candidates were allotted. Check category codes, seat matrix and options.")


# Standalone run support (optional)
if __name__ == "__main__":
    st.set_page_config("BLE Allotment", layout="wide")
    bpharm_le_allotment()
