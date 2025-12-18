import streamlit as st
import pandas as pd
from io import BytesIO

st.title("🎓 Admission Allotment – HQ / MQ / IQ")

st.write("Upload the three files (CSV or XLSX): Candidates, Seat Matrix, Option Entry")

# ----------------------------------------------------
# UNIVERSAL FILE READER (NO openpyxl REQUIRED)
# ----------------------------------------------------
def read_any(file):
    name = file.name.lower()

    # Case 1: CSV → direct read
    if name.endswith(".csv"):
        file.seek(0)
        return pd.read_csv(file, encoding="ISO-8859-1")

    # Case 2: XLSX/XLS → use ODF engine (works on simple tables)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        file.seek(0)
        try:
            xls = pd.ExcelFile(file, engine="odf")
            df = pd.read_excel(xls)
            return df
        except Exception:
            # Fallback: many Excel files exported from web systems are actually CSV internally
            file.seek(0)
            return pd.read_csv(file, encoding="ISO-8859-1")

    # Unknown extension → fallback
    file.seek(0)
    return pd.read_csv(file, encoding="ISO-8859-1")


# ----------------------------------------------------
# FILE UPLOADERS
# ----------------------------------------------------
cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"])
seat_file = st.file_uploader("2️⃣ Seat Matrix", type=["csv", "xlsx"])
opt_file  = st.file_uploader("3️⃣ Option Entry", type=["csv", "xlsx"])


if cand_file and seat_file and opt_file:

    # ----------------------------------------------------
    # LOAD FILES USING SAFE LOADER
    # ----------------------------------------------------
    try:
        cand = read_any(cand_file)
        seats = read_any(seat_file)
        opts = read_any(opt_file)
    except Exception as e:
        st.error(f"File loading failed: {e}")
        st.stop()

    st.success("Files uploaded successfully. Processing…")

    # ----------------------------------------------------
    # CLEAN + NORMALIZE SEAT MATRIX
    # ----------------------------------------------------
    required_cols = ["grp", "typ", "college", "course", "category", "SEAT"]
    for col in required_cols:
        if col not in seats.columns:
            st.error(f"Seat file missing column: {col}")
            st.stop()

    for col in ["grp", "typ", "college", "course", "category"]:
        seats[col] = seats[col].astype(str).str.strip().str.upper()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    # build seat availability map
    seat_map = {}
    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_map[key] = seat_map.get(key, 0) + r["SEAT"]

    # ----------------------------------------------------
    # CLEAN OPTION ENTRIES
    # ----------------------------------------------------
    for col in ["RollNo", "OPNO", "Optn", "ValidOption", "Delflg"]:
        if col not in opts.columns:
            st.error(f"OptionEntry file missing column: {col}")
            st.stop()

    opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper().str.strip()
    opts["Delflg"] = opts["Delflg"].astype(str).str.upper().str.strip()
    opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()

    opts = opts[
        (opts["OPNO"] != 0) &
        (opts["ValidOption"] == "Y") &
        (opts["Delflg"] != "Y")
    ].copy()

    opts = opts.sort_values(["RollNo", "OPNO"])

    # ----------------------------------------------------
    # CLEAN RANKS
    # ----------------------------------------------------
    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank"]:
        if col not in cand.columns:
            cand[col] = 0

    for col in ["HQ_Rank", "MQ_Rank", "IQ_Rank"]:
        cand[col] = pd.to_numeric(cand[col], errors="coerce").fillna(0).astype(int)
        cand[col] = cand[col].replace(0, 9999999)

    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype("Int64")
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype("Int64")

    # ----------------------------------------------------
    # OPTN DECODER (MGADMCGG → M | G | AD | MCG)
    # ----------------------------------------------------
    def decode_opt(opt):
        opt = opt.strip().upper()
        if len(opt) < 7:
            return None
        grp = opt[0]
        typ = opt[1]
        course = opt[2:4]
        college = opt[4:7]
        return grp, typ, course, college

    # ----------------------------------------------------
    # RUN ALLOTMENT (HQ → MQ → IQ)
    # ----------------------------------------------------
    quota_rounds = [
        ("HQ", "HQ_Rank"),
        ("MQ", "MQ_Rank"),
        ("IQ", "IQ_Rank"),
    ]

    allotments = []
    already_allotted = set()

    for quota_cat, rank_col in quota_rounds:
        sorted_cand = cand.sort_values(rank_col)

        for _, c in sorted_cand.iterrows():
            roll = int(c["RollNo"])
            rank_val = int(c[rank_col])

            if rank_val == 9999999:
                continue

            if roll in already_allotted:
                continue

            # options for this candidate
            c_opts = opts[opts["RollNo"] == roll]
            if c_opts.empty:
                continue

            # try each option in order
            for _, op in c_opts.iterrows():
                dec = decode_opt(op["Optn"])
                if not dec:
                    continue

                og, otyp, ocourse, oclg = dec

                key = (og, otyp, oclg, ocourse, quota_cat)

                if seat_map.get(key, 0) > 0:
                    seat_map[key] -= 1
                    already_allotted.add(roll)

                    allotments.append({
                        "RollNo": roll,
                        "Quota": quota_cat,
                        "grp": og,
                        "typ": otyp,
                        "College": oclg,
                        "Course": ocourse,
                        "RankUsed": rank_val
                    })

                    break  # stop after first successful option

    # ----------------------------------------------------
    # RESULTS
    # ----------------------------------------------------
    result_df = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Result")
    st.write(f"Total Allotted: **{len(result_df)}**")

    if not result_df.empty:
        st.dataframe(result_df)

        buf = BytesIO()
        result_df.to_csv(buf, index=False)
        buf.seek(0)

        st.download_button(
            "⬇️ Download Allotment Result CSV",
            data=buf,
            file_name="allotment_result.csv",
            mime="text/csv"
        )
    else:
        st.warning("No allotments. Check ranks, OPTN codes, seat categories, and matching rules.")
