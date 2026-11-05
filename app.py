
"""
PropCheck Karnataka - Streamlit Frontend

Run:
    streamlit run app.py
"""

import requests
import streamlit as st


# ----------------------------------------------------------
# Application configuration
# ----------------------------------------------------------

API_URL = "http://localhost:8000"

st.set_page_config(

    page_title="PropCheck Karnataka",

    page_icon="🏡",

    layout="wide",

)


# ----------------------------------------------------------
# Styling
# ----------------------------------------------------------

st.markdown(
    """
    <style>

    .main {
        background-color: #F7F9FC;
    }

    .risk-card {
        padding: 22px;
        border-radius: 12px;
        background-color: white;
        border: 1px solid #E5E7EB;
    }

    .small-note {
        color: #667085;
        font-size: 13px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------
# Header
# ----------------------------------------------------------

st.title("🏡 PropCheck Karnataka")

st.subheader(
    "Property Document Risk Screening"
)

st.write(
    """
    Upload a Sale Deed or Encumbrance Certificate
    to identify preliminary document-based risk flags.
    """
)

st.caption(
    "Prototype only — not a legally binding title opinion."
)


# ----------------------------------------------------------
# Sidebar
# ----------------------------------------------------------

with st.sidebar:

    st.title("PropCheck")

    st.write("Property buyer dashboard")

    st.divider()

    st.info(
        """
        Supported document types:

        - Sale Deed
        - Encumbrance Certificate
        - Mother Deed
        - Other property PDFs
        """
    )

    st.caption(
        "Current version uses placeholder extraction."
    )


# ----------------------------------------------------------
# Upload document
# ----------------------------------------------------------

uploaded_file = st.file_uploader(

    "Upload property document",

    type=["pdf"],

)

if uploaded_file:

    st.success(
        f"Selected: {uploaded_file.name}"
    )

    if st.button(
        "Analyze Property Document",
        type="primary",
        use_container_width=True,
    ):

        with st.spinner(
            "Analyzing document..."
        ):

            try:

                response = requests.post(

                    f"{API_URL}/api/analyze-document",

                    files={

                        "file": (

                            uploaded_file.name,

                            uploaded_file.getvalue(),

                            "application/pdf",

                        )

                    },

                    timeout=120,

                )

                response.raise_for_status()

                report = response.json()

                st.session_state["report"] = report

            except requests.RequestException as error:

                st.error(
                    f"Analysis failed: {error}"
                )


# ----------------------------------------------------------
# Display report
# ----------------------------------------------------------

if "report" in st.session_state:

    report = st.session_state["report"]

    extracted = report["extracted_data"]

    risk = report["risk_analysis"]

    st.divider()

    st.header("Property Risk Report")

    score = risk["risk_score"]

    if score == "RED":

        st.error(
            "🔴 RED — Significant potential risks detected"
        )

    elif score == "YELLOW":

        st.warning(
            "🟡 YELLOW — Further verification required"
        )

    else:

        st.success(
            "🟢 GREEN — No high-severity rules triggered"
        )

    st.write(
        risk["legal_opinion_summary"]
    )

    # ------------------------------------------------------
    # Property details
    # ------------------------------------------------------

    st.subheader(
        "Extracted Property Information"
    )

    details = extracted["property_details"]

    col1, col2 = st.columns(2)

    with col1:

        st.metric(

            "Current Owner",

            extracted.get(
                "current_owner_name"
            ) or "Not identified",

        )

        st.metric(

            "Survey Number",

            details.get(
                "survey_number"
            ) or "Not identified",

        )

        st.metric(

            "Khata / PID",

            details.get(
                "khata_pid_number"
            ) or "Not identified",

        )

    with col2:

        st.metric(

            "Village",

            details.get(
                "village"
            ) or "Not identified",

        )

        st.metric(

            "Hobli",

            details.get(
                "hobli"
            ) or "Not identified",

        )

        st.metric(

            "Document Type",

            extracted.get(
                "document_type"
            ),

        )

    # ------------------------------------------------------
    # Findings
    # ------------------------------------------------------

    st.subheader(
        "Detected Risk Findings"
    )

    if not risk["findings"]:

        st.info(
            "No findings were generated."
        )

    for finding in risk["findings"]:

        with st.expander(

            f"{finding['severity']} — "
            f"{finding['category']}",

            expanded=True,

        ):

            st.write(
                finding["finding"]
            )

            st.markdown(
                "**Recommended next step**"
            )

            st.write(
                finding["recommendation"]
            )

    # ------------------------------------------------------
    # Missing information
    # ------------------------------------------------------

    st.subheader(
        "Missing Information"
    )

    missing = extracted.get(
        "missing_information",
        [],
    )

    if missing:

        for item in missing:

            st.write(
                f"• {item}"
            )

    else:

        st.write(
            "No missing information flags."
        )

    # ------------------------------------------------------
    # Download PDF
    # ------------------------------------------------------

    report_id = report["report_id"]

    pdf_response = requests.get(

        f"{API_URL}/api/reports/{report_id}/pdf",

        timeout=120,

    )

    if pdf_response.ok:

        st.download_button(

            label="Download Legal Risk Report PDF",

            data=pdf_response.content,

            file_name=(
                f"PropCheck-{report_id}.pdf"
            ),

            mime="application/pdf",

            use_container_width=True,

        )

    # ------------------------------------------------------
    # Disclaimer
    # ------------------------------------------------------

    st.divider()

    st.warning(
        risk["disclaimer"]
    )


# ----------------------------------------------------------
# Report history
# ----------------------------------------------------------

st.divider()

st.header("Previous Reports")

if st.button("Refresh Report History"):

    try:

        history_response = requests.get(

            f"{API_URL}/api/reports",

            timeout=30,

        )

        history_response.raise_for_status()

        history = history_response.json()

        if history:

            st.dataframe(

                history,

                use_container_width=True,

                hide_index=True,

            )

        else:

            st.info(
                "No reports saved yet."
            )

    except requests.RequestException:

        st.error(
            "Could not connect to the backend."
        )
