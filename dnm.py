# hq_mq_iq.py
import streamlit as st
import pandas as pd
from io import BytesIO

def dnm_allotment():

    st.title("🎓 Admission Allotment – DNBM")
    st.write("Upload the three files (CSV or XLSX): Candidates, Seat Matrix, Option Entry")

    # ----------------------------------------------------
    # UNIVERSAL FILE READER
    # ----------------------------------------------------
    def read_any(file):
        name = file.name.lower()

        if name.endswith(".csv"):
            file.seek(0)
            return pd.read_csv(file, encoding="ISO-8859-1")

        if name.endswith((".xlsx", ".xls")):
            file.seek(0)
            try:
                xls = pd.ExcelFile(file, engine="odf")
                return pd.read_excel(xls)
            except Exception:
                file.seek(0)
                return pd.read_csv(file, encoding="ISO-8859-1")

        file.seek(0)
        return pd.read_csv(file, encoding="ISO-8859-1")

    # ----------------------------------------------------
    # FILE UPLOAD
    # ----------------------------------------------------
    cand_file = st.file_uploader("1️⃣ Candidates File", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry", type=["csv", "xlsx"])

    if not (cand_file and seat_file and opt_file):
        return

    try:
        cand  = read_any(cand_file)
        seats = read_any(seat_file)
        opts  = read_any(opt_file)
    except Exception as e:
        st.error(f"File loading failed: {e}")
        return

    st.success("Files uploaded successfully. Processing…")

    # ----------------------------------------------------
    # SEAT MATRIX CLEAN
    # ----------------------------------------------------
    req_cols = ["grp", "typ", "college", "course", "category", "SEAT"]
    for c in req_cols:
        if c not in seats.columns:
            st.error(f"Seat file missing column: {c}")
            return

    for c in ["grp", "typ", "college", "course", "category"]:
        seats[c] = seats[c].astype(str).str.upper().str.strip()

    seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

    seat_map = {}
    for _, r in seats.iterrows():
        key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
        seat_map[key] = seat_map.get(key, 0) + r["SEAT"]

    # ----------------------------------------------------
    # OPTION ENTRY CLEAN
    # ----------------------------------------------------
    for c in ["RollNo", "OPNO", "Optn", "ValidOption", "Delflg"]:
        if c not in opts.columns:
            st.error(f"OptionEntry missing column: {c}")
            return

    opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper()
    opts["Delflg"]      = opts["Delflg"].astype(str).str.upper()
    opts["Optn"]        = opts["Optn"].astype(str).str.upper()

    opts = opts[
        (opts["OPNO"] != 0) &
        (opts["ValidOption"] == "Y") &
        (opts["Delflg"] != "Y")
    ].sort_values(["RollNo", "OPNO"])

    # ----------------------------------------------------
    # RANK NORMALIZATION
    # ----------------------------------------------------
    for r in ["HQ_Rank", "MQ_Rank", "IQ_Rank"]:
        if r not in cand.columns:
            cand[r] = 0

        cand[r] = pd.to_numeric(cand[r], errors="coerce").fillna(0).astype(int)
        cand[r] = cand[r].replace(0, 9999999)

    cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype("Int64")
    opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype("Int64")

    # ----------------------------------------------------
    # OPTION DECODER
    # ----------------------------------------------------
    def decode_opt(opt):
        if len(opt) < 7:
            return None
        return opt[0], opt[1], opt[2:4], opt[4:7]

    # ----------------------------------------------------
    # ALLOTMENT ENGINE
    # ----------------------------------------------------
    rounds = [
        ("HQ", "HQ_Rank"),
        ("MQ", "MQ_Rank"),
        ("IQ", "IQ_Rank")
    ]

    allotments = []
    allotted = set()

    for quota, rank_col in rounds:
        for _, c in cand.sort_values(rank_col).iterrows():

            roll = int(c["RollNo"])
            if roll in allotted or c[rank_col] == 9999999:
                continue

            for _, o in opts[opts["RollNo"] == roll].iterrows():
                dec = decode_opt(o["Optn"])
                if not dec:
                    continue

                g, t, crs, clg = dec
                key = (g, t, clg, crs, quota)

                if seat_map.get(key, 0) > 0:
                    seat_map[key] -= 1
                    allotted.add(roll)

                    allotments.append({
                        "RollNo": roll,
                        "Quota": quota,
                        "grp": g,
                        "typ": t,
                        "College": clg,
                        "Course": crs,
                        "RankUsed": c[rank_col]
                    })
                    break

    # ----------------------------------------------------
    # OUTPUT
    # ----------------------------------------------------
    df = pd.DataFrame(allotments)

    st.subheader("🟩 Allotment Result")
    st.write(f"Total Allotted: **{len(df)}**")

    if df.empty:
        st.warning("No allotments found.")
        return

    st.dataframe(df, use_container_width=True)

    buf = BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)

    st.download_button(
        "⬇️ Download Result",
        data=buf,
        file_name="dnm_allotment.csv",
        mime="text/csv"
    )
