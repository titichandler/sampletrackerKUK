"""Streamlit sample request form connected to SQLite."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from sampletracker.db.database import get_engine, migrate_schema, save_sample_requests

SESSION_SAMPLES_KEY = "pending_samples"
ADD_FORM_VERSION_KEY = "add_form_version"
FORMULA_FILE_PATH = Path(__file__).resolve().parents[2] / "EU FORMULAS DATABASE.xlsx"
ENTRY_LIBRARY = "From formula library"
ENTRY_MANUAL = "Enter manually"
MANUAL_CODE_PLACEHOLDER = "MANUAL"


def _init_session_state() -> None:
    if SESSION_SAMPLES_KEY not in st.session_state:
        st.session_state[SESSION_SAMPLES_KEY] = []
    if ADD_FORM_VERSION_KEY not in st.session_state:
        st.session_state[ADD_FORM_VERSION_KEY] = 0


def is_valid_email(email: str) -> bool:
    """Basic email format check."""
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def validate_request_header(
    email: str,
    request_origin: str,
) -> list[str]:
    """Validate required request-level fields."""
    errors: list[str] = []
    if not email.strip():
        errors.append("Email address is required.")
    elif not is_valid_email(email):
        errors.append("Enter a valid email address.")
    if not request_origin.strip():
        errors.append("Request origin is required.")
    return errors


def validate_sample_line(
    formula_code: str,
    formula_name: str,
    num_samples: int,
    *,
    manual_entry: bool,
) -> list[str]:
    """Return validation error messages for a single sample line."""
    errors: list[str] = []
    if manual_entry:
        if not formula_name.strip():
            errors.append("Formula name is required for manual entry.")
    else:
        if not formula_code.strip():
            errors.append("Formula code is required.")
        if not formula_name.strip():
            errors.append("Formula name is required.")
    if num_samples <= 0:
        errors.append("Number of samples must be greater than 0.")
    return errors


@st.cache_data(show_spinner=False)
def load_formula_options() -> list[dict[str, str]]:
    """Load formula code/name options from Excel columns B (code) and C (name)."""
    if not FORMULA_FILE_PATH.exists():
        return []

    frame = pd.read_excel(FORMULA_FILE_PATH, header=0, usecols=[1, 2])
    frame.columns = ["formula_code", "formula_name"]
    cleaned = (
        frame.dropna(subset=["formula_code", "formula_name"])
        .assign(
            formula_code=lambda df: df["formula_code"].astype(str).str.strip(),
            formula_name=lambda df: df["formula_name"].astype(str).str.strip(),
        )
    )
    cleaned = cleaned[(cleaned["formula_code"] != "") & (cleaned["formula_name"] != "")]
    return cleaned.to_dict(orient="records")


def _formula_label(option: dict[str, str]) -> str:
    """Display format used by the searchable formula dropdown."""
    return f"{option['formula_code']} - {option['formula_name']}"


def _pending_table_rows() -> list[dict[str, Any]]:
    """Build display rows for the pending-samples table."""
    pending: list[dict[str, Any]] = st.session_state[SESSION_SAMPLES_KEY]
    return [
        {
            "#": index + 1,
            "Entry": sample["entry_type"],
            "Formula Code": (
                "-" if sample["formula_code"] == MANUAL_CODE_PLACEHOLDER else sample["formula_code"]
            ),
            "Formula Name": sample["formula_name"],
            "Number of Samples": sample["num_samples"],
        }
        for index, sample in enumerate(pending)
    ]


def _render_pending_table() -> None:
    """Show a table of all samples added before submit."""
    pending = st.session_state[SESSION_SAMPLES_KEY]

    if not pending:
        st.info("No samples added yet. Use the form above to add your first sample.")
        st.table(
            {
                "#": ["—"],
                "Entry": ["—"],
                "Formula Code": ["(none yet)"],
                "Formula Name": ["(none yet)"],
                "Number of Samples": ["—"],
            }
        )
        return

    st.table(_pending_table_rows())


def _ensure_database_schema() -> None:
    """Make sure existing SQLite files include newer columns."""
    engine = get_engine()
    migrate_schema(engine)
    engine.dispose()


def main() -> None:
    st.set_page_config(page_title="Sample Request Kobo UK", layout="wide")
    _init_session_state()
    _ensure_database_schema()

    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] * {
            font-family: "Calibri Light", Calibri, "Segoe UI", Arial, sans-serif !important;
        }
        html, body, [data-testid="stAppViewContainer"] {
            font-size: 16px !important;
        }
        p, label, [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {
            font-size: 16px !important;
        }
        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] label {
            font-weight: 700 !important;
            color: #4a2f6d !important;
        }
        .app-title-bar {
            width: 100vw;
            position: relative;
            left: 50%;
            right: 50%;
            margin-left: -50vw;
            margin-right: -50vw;
            background-color: #e9e0fa;
            border-bottom: 1px solid #d6c6f0;
            padding: 0.85rem 0;
            text-align: center;
            margin-bottom: 2rem;
        }
        .app-title-text {
            font-size: 1.6rem;
            font-weight: 700;
            color: #2a2d3a;
            display: block;
        }
        .stTable table th, .stTable table td {
            text-align: center !important;
        }
        div[data-testid="stForm"] {
            border: 1px solid #e6e9ef;
            border-radius: 10px;
            padding: 0.75rem 1rem;
            background-color: #fbfcfe;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="app-title-bar">
            <span class="app-title-text">Sample Request Kobo UK</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    row_1_col_1, row_1_col_2 = st.columns(2)
    with row_1_col_1:
        email = st.text_input(
            "Email address *",
            placeholder="name@company.com",
            key="request_email",
        )
    with row_1_col_2:
        request_origin = st.text_input(
            "Request origin *",
            placeholder="e.g. Marketing, Sales, Internal R&D",
            key="request_origin",
        )

    row_2_col_1, row_2_col_2 = st.columns(2)
    with row_2_col_1:
        include_due_date = st.checkbox("Set a due date (optional)", key="include_due_date")
    with row_2_col_2:
        due_date = st.date_input(
            "Due date",
            value=date.today(),
            disabled=not include_due_date,
            key="due_date",
        )
    due_date_value = due_date if include_due_date else None

    formula_options = load_formula_options()
    form_id = st.session_state[ADD_FORM_VERSION_KEY]

    # Radio must be outside the form so the UI updates immediately when switching modes.
    entry_mode = st.radio(
        "How do you want to add this sample? *",
        options=[ENTRY_LIBRARY, ENTRY_MANUAL],
        horizontal=True,
        key="sample_entry_mode",
    )
    manual_entry = entry_mode == ENTRY_MANUAL

    form_suffix = "manual" if manual_entry else "library"
    with st.form(f"add_sample_form_{form_id}_{form_suffix}"):
        form_col_1, form_col_2 = st.columns([3, 1])
        with form_col_1:
            if manual_entry:
                formula_name = st.text_input(
                    "Formula name *",
                    placeholder="Type the formula name",
                    help="Use this when the formula is not in the library list.",
                )
                manual_code = st.text_input(
                    "Formula code (optional)",
                    placeholder="Leave blank if unknown",
                )
                formula_code = manual_code.strip() or MANUAL_CODE_PLACEHOLDER
            elif not formula_options:
                st.warning(
                    "Formula library file is unavailable. Choose **Enter manually** above."
                )
                formula_code = ""
                formula_name = ""
            else:
                selected_formula = st.selectbox(
                    "Formula (search by code or name) *",
                    options=formula_options,
                    format_func=_formula_label,
                    help="Type to search by code or formula name.",
                )
                formula_code = selected_formula["formula_code"]
                formula_name = selected_formula["formula_name"]

        with form_col_2:
            num_samples = st.number_input(
                "Number of samples *",
                min_value=0,
                step=1,
                value=1,
            )

        add_clicked = st.form_submit_button(
            "Add sample to list",
            use_container_width=True,
        )

    st.divider()
    _render_pending_table()
    st.caption(f"Current samples in queue: **{len(st.session_state[SESSION_SAMPLES_KEY])}**")

    submit_clicked = st.button(
        "Submit full request",
        type="primary",
        use_container_width=True,
    )

    if add_clicked:
        if not manual_entry and not formula_options:
            st.error("Cannot add from library while the Excel formula file is missing.")
        else:
            errors = validate_sample_line(
                formula_code,
                formula_name,
                int(num_samples),
                manual_entry=manual_entry,
            )
            if errors:
                for message in errors:
                    st.error(message)
            else:
                st.session_state[SESSION_SAMPLES_KEY].append(
                    {
                        "formula_code": formula_code.strip(),
                        "formula_name": formula_name.strip(),
                        "num_samples": int(num_samples),
                        "entry_type": "Manual" if manual_entry else "Library",
                    }
                )
                st.session_state[ADD_FORM_VERSION_KEY] += 1
                st.rerun()

    if "last_saved_requests" in st.session_state:
        saved_number = st.session_state.pop("last_saved_request_number", "")
        st.success(f"Request **{saved_number}** saved successfully.")
        st.table(st.session_state.pop("last_saved_requests"))

    if submit_clicked:
        pending = st.session_state[SESSION_SAMPLES_KEY]
        header_errors = validate_request_header(email, request_origin)
        if header_errors:
            for message in header_errors:
                st.error(message)
            return
        if not pending:
            st.warning("Add at least one sample to the table before submitting.")
            return

        email_value = email.strip()
        origin_value = request_origin.strip()
        items_to_save = [
            {
                "formula_code": sample["formula_code"],
                "formula_name": sample["formula_name"],
                "num_samples": sample["num_samples"],
                "due_date": due_date_value,
                "request_origin": origin_value,
                "email": email_value,
            }
            for sample in pending
        ]

        try:
            saved = save_sample_requests(items_to_save)
        except Exception as exc:
            st.error(f"Could not save request: {exc}")
            return

        st.session_state[SESSION_SAMPLES_KEY] = []
        st.session_state["last_saved_request_number"] = saved[0]["request_number"]
        st.session_state["last_saved_requests"] = [
            {
                "Request Number": row["request_number"],
                "ID": row["id"],
                "Email": row["email"],
                "Request Origin": row["request_origin"],
                "Formula Code": (
                    "-" if row["formula_code"] == MANUAL_CODE_PLACEHOLDER else row["formula_code"]
                ),
                "Formula Name": row["formula_name"],
                "Number of Samples": row["num_samples"],
                "Due Date": row["due_date"] or "—",
                "Created At": row["created_at"],
            }
            for row in saved
        ]
        st.rerun()


if __name__ == "__main__":
    main()
