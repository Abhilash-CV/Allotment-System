import streamlit as st
import pandas as pd
from io import BytesIO


def pga_allotment():

    st.title("🎓 Admission Allotment System – ARank + Seat Category Priority")


    # ----------------------------------------------------
    # UNIVERSAL FILE READER
    # ----------------------------------------------------
    def read_any(file):
        name = file.name.lower()

        if name.endswith(".csv"):
            file.seek(0)
            return pd.read_csv(file, encoding="ISO-8859-1")

        if name.endswith(".xlsx") or name.endswith(".xls"):
            file.seek(0)
            try:
                xls = pd.ExcelFile(file, engine="odf")
                return pd.read_excel(xls)
            except:
                file.seek(0)
                return pd.read_csv(file, encoding="ISO-8859-1")

        file.seek(0)
        return pd.read_csv(file, encoding="ISO-8859-1")


    # ----------------------------------------------------
    # CATEGORY ELIGIBILITY LOGIC
    # ----------------------------------------------------
    def category_eligible(seat_cat, cand_cat):
        seat_cat = str(seat_cat).strip().upper()
        cand_cat = str(cand_cat or "").strip().upper()

        if seat_cat in ["AM", "SM"]:
            return True

        if cand_cat in ["NA", "NULL", "", None, "N/A"]:
            return False

        return seat_cat == cand_cat


    # ----------------------------------------------------
    # FILE UPLOADS
    # ----------------------------------------------------
    cand_file = st.file_uploader("1️⃣ Candidates File (ARank, Category, AIQ)", type=["csv", "xlsx"])
    seat_file = st.file_uploader("2️⃣ Seat Matrix (grp, typ, college, course, category, SEAT)", type=["csv", "xlsx"])
    opt_file  = st.file_uploader("3️⃣ Option Entry File", type=["csv", "xlsx"])

    if cand_file and seat_file and opt_file:

        cand = read_any(cand_file)
        seats = read_any(seat_file)
        opts = read_any(opt_file)

        st.success("Files loaded successfully! Running allotment...")


        # ----------------------------------------------------
        # CLEAN SEAT MATRIX
        # ----------------------------------------------------
        required_cols = ["grp","typ","college","course","category","SEAT"]
        for col in required_cols:
            if col not in seats.columns:
                st.error(f"Seat file missing column: {col}")
                st.stop()

        for col in ["grp","typ","college","course","category"]:
            seats[col] = seats[col].astype(str).str.upper().str.strip()

        seats["SEAT"] = pd.to_numeric(seats["SEAT"], errors="coerce").fillna(0).astype(int)

        seat_map = {}
        for _, r in seats.iterrows():
            key = (r["grp"], r["typ"], r["college"], r["course"], r["category"])
            seat_map[key] = seat_map.get(key, 0) + r["SEAT"]


        # ----------------------------------------------------
        # CLEAN OPTION ENTRY
        # ----------------------------------------------------
        opts["ValidOption"] = opts["ValidOption"].astype(str).str.upper().str.strip()
        opts["Delflg"] = opts["Delflg"].astype(str).str.upper().str.strip()
        opts["Optn"] = opts["Optn"].astype(str).str.upper().str.strip()

        opts = opts[(opts["OPNO"] != 0) &
                    (opts["ValidOption"] == "Y") &
                    (opts["Delflg"] != "Y")].copy()

        opts = opts.sort_values(["RollNo", "OPNO"])
        opts["RollNo"] = pd.to_numeric(opts["RollNo"], errors="coerce").astype("Int64")


        # ----------------------------------------------------
        # CLEAN CANDIDATE FILE
        # ----------------------------------------------------
        if "ARank" not in cand.columns:
            st.error("Candidate file missing ARank column.")
            st.stop()

        cand["ARank"] = pd.to_numeric(cand["ARank"], errors="coerce").fillna(9999999)
        cand["RollNo"] = pd.to_numeric(cand["RollNo"], errors="coerce").astype("Int64")

        if "Category" not in cand.columns:
            cand["Category"] = ""

        if "AIQ" not in cand.columns:
            cand["AIQ"] = ""

        cand_sorted = cand.sort_values("ARank")


        # ----------------------------------------------------
        # OPTION DECODER
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
        # RUN ALLOTMENT
        # ----------------------------------------------------
        allotments = []

        for _, c in cand_sorted.iterrows():
            roll = int(c["RollNo"])
            arank = int(c["ARank"])
            ccat = str(c["Category"]).strip().upper()

            if str(c.get("AIQ", "")).strip().upper() == "Y":
                continue

            c_opts = opts[opts["RollNo"] == roll]
            if c_opts.empty:
                continue

            for _, op in c_opts.iterrows():
                decoded = decode_opt(op["Optn"])
                if not decoded:
                    continue

                og, otyp, ocourse, oclg = decoded

                seat_rows = seats[
                    (seats["grp"] == og) &
                    (seats["typ"] == otyp) &
                    (seats["college"] == oclg) &
                    (seats["course"] == ocourse)
                ]

                if seat_rows.empty:
                    continue

                chosen_key = None
                chosen_cat = None

                priority_order = ["AM", "SM"]
                community_cats = sorted(
                    set(seat_rows["category"]) - {"AM", "SM"}
                )
                priority_order += community_cats

                for cat in priority_order:
                    for _, sr in seat_rows[seat_rows["category"] == cat].iterrows():

                        key = (sr["grp"], sr["typ"], sr["college"], sr["course"], sr["category"])
                        seat_cat = sr["category"]

                        if seat_map.get(key, 0) <= 0:
                            continue

                        if category_eligible(seat_cat, ccat):
                            chosen_key = key
                            chosen_cat = seat_cat
                            break

                    if chosen_key:
                        break

                if chosen_key:
                    seat_map[chosen_key] -= 1

                    allotments.append({
                        "RollNo": roll,
                        "ARank": arank,
                        "CandidateCategory": ccat,
                        "grp": og,
                        "typ": otyp,
                        "College": oclg,
                        "Course": ocourse,
                        "SeatCategoryAllotted": chosen_cat
                    })
                    break


        # ----------------------------------------------------
        # OUTPUT RESULT
        # ----------------------------------------------------
        result_df = pd.DataFrame(allotments)

        st.subheader("🟩 Allotment Result")
        st.write(f"✅ Total Allotted: **{len(result_df)}**")

        st.dataframe(result_df)

        buf = BytesIO()
        result_df.to_csv(buf, index=False)
        buf.seek(0)

        st.download_button(
            "⬇️ Download Allotment Result CSV",
            buf,
            "allotment_result.csv",
            "text/csv"
        )
