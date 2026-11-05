
"""
PropCheck Karnataka
-------------------
Property document screening prototype.

IMPORTANT:
This application produces preliminary document-based risk flags.
It does not establish ownership, verify government records, or
provide a legally binding title opinion.

Run:
    uvicorn main:app --reload
"""

import os
import re
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.units import mm


# ==========================================================
# 1. APPLICATION SETTINGS
# ==========================================================

APP_NAME = "PropCheck Karnataka"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = DATA_DIR / "reports"

DATABASE_PATH = DATA_DIR / "propcheck.db"

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB

DATA_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title=APP_NAME,
    description=(
        "Preliminary Karnataka property document "
        "screening and title risk analysis."
    ),
    version="1.0.0",
)


# ==========================================================
# 2. DATABASE
# ==========================================================

def get_connection():
    """Create a connection to the SQLite database."""

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    """
    Create the report history table if it does not exist.

    SQLite is used for this prototype.
    A production application would need authentication,
    access controls, and a managed database.
    """

    with get_connection() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (

                report_id TEXT PRIMARY KEY,

                created_at TEXT NOT NULL,

                filename TEXT NOT NULL,

                risk_score TEXT NOT NULL,

                report_json TEXT NOT NULL

            )
            """
        )

        connection.commit()


initialize_database()


# ==========================================================
# 3. DATA MODELS
# ==========================================================

class OwnershipRecord(BaseModel):
    """One transaction in the ownership history."""

    seller: Optional[str] = None

    buyer: Optional[str] = None

    date: Optional[str] = None

    document_reference: Optional[str] = None


class PropertyDetails(BaseModel):
    """Basic property identification information."""

    survey_number: Optional[str] = None

    khata_pid_number: Optional[str] = None

    village: Optional[str] = None

    hobli: Optional[str] = None

    district: Optional[str] = None

    property_type: Optional[str] = None


class ExtractedDocument(BaseModel):
    """Structured information extracted from a PDF."""

    document_type: str = "Unknown"

    current_owner_name: Optional[str] = None

    property_details: PropertyDetails = Field(
        default_factory=PropertyDetails
    )

    ownership_chain: list[OwnershipRecord] = Field(
        default_factory=list
    )

    liabilities: list[str] = Field(
        default_factory=list
    )

    document_mentions: list[str] = Field(
        default_factory=list
    )

    missing_information: list[str] = Field(
        default_factory=list
    )

    extraction_method: str = "placeholder"


class RiskFinding(BaseModel):
    """One detected risk."""

    category: str

    severity: str

    finding: str

    recommendation: str


class RiskAnalysis(BaseModel):
    """Overall risk assessment."""

    risk_score: str

    findings: list[RiskFinding]

    legal_opinion_summary: str

    disclaimer: str


class AnalysisReport(BaseModel):
    """Complete PropCheck report."""

    report_id: str

    created_at: str

    filename: str

    extracted_data: ExtractedDocument

    risk_analysis: RiskAnalysis


# ==========================================================
# 4. PDF TEXT EXTRACTION
# ==========================================================

def extract_pdf_text(file_path: Path) -> str:
    """
    Extract selectable text from a PDF.

    Scanned PDFs require OCR.
    This function does not perform OCR.
    """

    try:

        document = fitz.open(file_path)

        text_parts = []

        for page in document:

            text_parts.append(page.get_text())

        document.close()

        extracted_text = "\n".join(text_parts)

        if not extracted_text.strip():

            raise HTTPException(
                status_code=422,
                detail=(
                    "No selectable text found. "
                    "This PDF may be scanned. "
                    "OCR support is required."
                ),
            )

        return extracted_text

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=422,
            detail=f"Could not read PDF: {error}",
        )


# ==========================================================
# 5. PLACEHOLDER DOCUMENT EXTRACTION ENGINE
# ==========================================================

def find_first(patterns: list[str], text: str):
    """
    Try multiple regular expressions.

    Returns the first match or None.
    """

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:

            return match.group(1).strip()

    return None


def extract_document_information(
    text: str,
) -> ExtractedDocument:
    """
    Placeholder extraction function.

    This is where a future LLM extraction service
    will be connected.

    Current version:
    - Detects a few common fields using regex.
    - Detects keywords.
    - Does not understand legal context reliably.
    """

    text_lower = text.lower()

    # ------------------------------------------------------
    # Current owner
    # ------------------------------------------------------

    owner = find_first(
        [
            r"purchaser\s*[:\-]\s*([^\n,]+)",
            r"buyer\s*[:\-]\s*([^\n,]+)",
            r"vendee\s*[:\-]\s*([^\n,]+)",
        ],
        text,
    )

    # ------------------------------------------------------
    # Survey number
    # ------------------------------------------------------

    survey_number = find_first(
        [
            r"survey\s*(?:no\.?|number)\s*[:\-]?\s*"
            r"([A-Za-z0-9/\-]+)",

            r"sy\.?\s*no\.?\s*[:\-]?\s*"
            r"([A-Za-z0-9/\-]+)",
        ],
        text,
    )

    # ------------------------------------------------------
    # Khata / PID
    # ------------------------------------------------------

    khata_pid = find_first(
        [
            r"khata\s*(?:no\.?|number)?\s*[:\-]?\s*"
            r"([A-Za-z0-9/\-]+)",

            r"pid\s*(?:no\.?|number)?\s*[:\-]?\s*"
            r"([A-Za-z0-9/\-]+)",
        ],
        text,
    )

    # ------------------------------------------------------
    # Village and Hobli
    # ------------------------------------------------------

    village = find_first(
        [
            r"village\s*[:\-]\s*([^\n,]+)",
        ],
        text,
    )

    hobli = find_first(
        [
            r"hobli\s*[:\-]\s*([^\n,]+)",
        ],
        text,
    )

    # ------------------------------------------------------
    # Document type
    # ------------------------------------------------------

    if "encumbrance certificate" in text_lower:

        document_type = "Encumbrance Certificate"

    elif "sale deed" in text_lower:

        document_type = "Sale Deed"

    elif "mother deed" in text_lower:

        document_type = "Mother Deed"

    else:

        document_type = "Unknown"

    # ------------------------------------------------------
    # Document mentions
    # ------------------------------------------------------

    keywords = [
        "dc conversion",
        "gram panchayat",
        "form 9",
        "form 11",
        "mother deed",
        "mortgage",
        "bank charge",
        "release deed",
        "conversion order",
    ]

    mentions = [
        keyword
        for keyword in keywords
        if keyword in text_lower
    ]

    # ------------------------------------------------------
    # Liabilities
    # ------------------------------------------------------

    liabilities = []

    liability_keywords = [
        "mortgage",
        "bank charge",
        "equitable mortgage",
        "loan",
        "charge created",
    ]

    for keyword in liability_keywords:

        if keyword in text_lower:

            liabilities.append(
                f"Potential liability mention: {keyword}"
            )

    # ------------------------------------------------------
    # Missing information
    # ------------------------------------------------------

    missing_information = []

    if not owner:

        missing_information.append(
            "Current owner name not extracted"
        )

    if not survey_number:

        missing_information.append(
            "Survey number not extracted"
        )

    if not khata_pid:

        missing_information.append(
            "Khata/PID number not extracted"
        )

    if "mother deed" not in text_lower:

        missing_information.append(
            "Mother Deed not identified in this document"
        )

    # ------------------------------------------------------
    # Return structured data
    # ------------------------------------------------------

    return ExtractedDocument(

        document_type=document_type,

        current_owner_name=owner,

        property_details=PropertyDetails(

            survey_number=survey_number,

            khata_pid_number=khata_pid,

            village=village,

            hobli=hobli,

        ),

        ownership_chain=[],

        liabilities=liabilities,

        document_mentions=mentions,

        missing_information=missing_information,

        extraction_method="regex_placeholder",

    )


# ==========================================================
# 6. PROPERTY RISK ANALYSIS ENGINE
# ==========================================================

def analyze_property_risk(
    extracted: ExtractedDocument,
    original_text: str,
) -> RiskAnalysis:
    """
    Evaluate preliminary property-document red flags.

    These are screening rules, not legal conclusions.
    """

    findings = []

    text_lower = original_text.lower()

    mentions = set(
        extracted.document_mentions
    )

    # ------------------------------------------------------
    # RULE 1: DC Conversion / Gram Panchayat
    # ------------------------------------------------------

    conversion_or_gp = (

        "dc conversion" in mentions

        or "gram panchayat" in mentions

    )

    form_9_or_11 = (

        "form 9" in mentions

        or "form 11" in mentions

    )

    if conversion_or_gp and not form_9_or_11:

        findings.append(
            RiskFinding(

                category="Land Conversion / Layout",

                severity="HIGH",

                finding=(
                    "The document mentions DC Conversion "
                    "or a Gram Panchayat layout, but "
                    "Form 9/Form 11 was not identified "
                    "in the supplied document."
                ),

                recommendation=(
                    "Obtain and independently verify the "
                    "applicable conversion order, approved "
                    "layout plan, and relevant Form 9/Form 11 "
                    "records with the competent authority."
                ),

            )
        )

    # ------------------------------------------------------
    # RULE 2: Missing Mother Deed / Ownership Chain
    # ------------------------------------------------------

    if "mother deed" not in text_lower:

        findings.append(
            RiskFinding(

                category="Title Chain",

                severity="MEDIUM",

                finding=(
                    "A Mother Deed was not identified "
                    "in the uploaded document."
                ),

                recommendation=(
                    "Obtain the historical title documents "
                    "and have a qualified Karnataka property "
                    "lawyer verify the ownership chain."
                ),

            )
        )

    # ------------------------------------------------------
    # RULE 3: Active Mortgage / Bank Charge
    # ------------------------------------------------------

    mortgage_keywords = [

        "mortgage",

        "bank charge",

        "equitable mortgage",

        "charge created",

    ]

    mortgage_found = any(

        keyword in text_lower

        for keyword in mortgage_keywords

    )

    release_found = any(

        keyword in text_lower

        for keyword in [

            "mortgage released",

            "charge satisfied",

            "release deed",

            "discharge of mortgage",

        ]

    )

    if mortgage_found and not release_found:

        findings.append(
            RiskFinding(

                category="Encumbrance",

                severity="CRITICAL",

                finding=(
                    "A mortgage or bank charge was detected "
                    "without a clearly identified release "
                    "or discharge in the supplied text."
                ),

                recommendation=(
                    "Obtain a current EC, bank loan closure "
                    "confirmation, and registered release "
                    "documents where applicable. Do not "
                    "assume the charge is active or cleared "
                    "based only on keyword detection."
                ),

            )
        )

    # ------------------------------------------------------
    # RULE 4: Missing extracted information
    # ------------------------------------------------------

    if extracted.missing_information:

        findings.append(
            RiskFinding(

                category="Document Completeness",

                severity="MEDIUM",

                finding=(
                    "Some key property information could "
                    "not be extracted from the document."
                ),

                recommendation=(
                    "Review the original document and "
                    "provide the missing supporting records."
                ),

            )
        )

    # ------------------------------------------------------
    # RULE 5: Unknown document
    # ------------------------------------------------------

    if extracted.document_type == "Unknown":

        findings.append(
            RiskFinding(

                category="Document Identification",

                severity="MEDIUM",

                finding=(
                    "The uploaded document type could "
                    "not be confidently identified."
                ),

                recommendation=(
                    "Confirm whether the file is a Sale Deed, "
                    "EC, Mother Deed, or another document."
                ),

            )
        )

    # ------------------------------------------------------
    # Calculate risk score
    # ------------------------------------------------------

    severity_order = {

        "CRITICAL": 4,

        "HIGH": 3,

        "MEDIUM": 2,

        "LOW": 1,

    }

    highest_severity = max(

        [

            severity_order.get(
                finding.severity,
                0,
            )

            for finding in findings

        ],

        default=0,

    )

    if highest_severity >= 4:

        risk_score = "RED"

    elif highest_severity >= 3:

        risk_score = "RED"

    elif highest_severity >= 2:

        risk_score = "YELLOW"

    else:

        risk_score = "GREEN"

    # ------------------------------------------------------
    # Generate simple-English opinion summary
    # ------------------------------------------------------

    if risk_score == "RED":

        summary = (
            "The supplied document contains significant "
            "potential title or encumbrance concerns. "
            "Further verification is necessary before "
            "proceeding with the transaction."
        )

    elif risk_score == "YELLOW":

        summary = (
            "The supplied document contains matters "
            "requiring further verification. Obtain "
            "supporting documents and seek professional "
            "review before proceeding."
        )

    else:

        summary = (
            "No high-severity red flags were detected "
            "by the current screening rules. This does "
            "not establish clear title or confirm that "
            "the property is legally safe to purchase."
        )

    disclaimer = (
        "This is an automated preliminary document "
        "screening report. It is not a legal opinion, "
        "title certificate, or guarantee of ownership. "
        "No independent government-record verification "
        "has been performed. Consult a qualified "
        "Karnataka property lawyer before purchasing."
    )

    return RiskAnalysis(

        risk_score=risk_score,

        findings=findings,

        legal_opinion_summary=summary,

        disclaimer=disclaimer,

    )


# ==========================================================
# 7. SAVE REPORT TO DATABASE
# ==========================================================

def save_report(
    report: AnalysisReport,
):
    """Save the completed report to SQLite."""

    with get_connection() as connection:

        connection.execute(

            """
            INSERT INTO reports (

                report_id,

                created_at,

                filename,

                risk_score,

                report_json

            )

            VALUES (?, ?, ?, ?, ?)

            """,

            (

                report.report_id,

                report.created_at,

                report.filename,

                report.risk_analysis.risk_score,

                report.model_dump_json(),

            ),

        )

        connection.commit()


# ==========================================================
# 8. PDF EXPORT
# ==========================================================

def export_report_pdf(
    report: AnalysisReport,
) -> Path:
    """
    Generate a simple PDF report.

    The report is stored in the local reports folder.
    """

    output_path = (
        REPORT_DIR
        / f"{report.report_id}.pdf"
    )

    document = SimpleDocTemplate(

        str(output_path),

        pagesize=A4,

        rightMargin=18 * mm,

        leftMargin=18 * mm,

        topMargin=18 * mm,

        bottomMargin=18 * mm,

    )

    styles = getSampleStyleSheet()

    story = []

    story.append(

        Paragraph(

            "PropCheck Karnataka",

            styles["Title"],

        )

    )

    story.append(

        Paragraph(

            "Preliminary Property Risk Screening Report",

            styles["Heading2"],

        )

    )

    story.append(

        Paragraph(

            f"Report ID: {report.report_id}",

            styles["Normal"],

        )

    )

    story.append(

        Paragraph(

            f"Date: {report.created_at}",

            styles["Normal"],

        )

    )

    story.append(Spacer(1, 12))

    story.append(

        Paragraph(

            "Risk Assessment",

            styles["Heading2"],

        )

    )

    story.append(

        Paragraph(

            f"Risk Score: {report.risk_analysis.risk_score}",

            styles["Normal"],

        )

    )

    story.append(Spacer(1, 8))

    story.append(

        Paragraph(

            report.risk_analysis.legal_opinion_summary,

            styles["BodyText"],

        )

    )

    story.append(Spacer(1, 12))

    story.append(

        Paragraph(

            "Extracted Property Information",

            styles["Heading2"],

        )

    )

    details = report.extracted_data.property_details

    property_table = [

        ["Field", "Extracted Value"],

        [

            "Current Owner",

            report.extracted_data.current_owner_name or "Not found",

        ],

        [

            "Survey Number",

            details.survey_number or "Not found",

        ],

        [

            "Khata / PID",

            details.khata_pid_number or "Not found",

        ],

        [

            "Village",

            details.village or "Not found",

        ],

        [

            "Hobli",

            details.hobli or "Not found",

        ],

        [

            "Document Type",

            report.extracted_data.document_type,

        ],

    ]

    table = Table(

        property_table,

        colWidths=[50 * mm, 115 * mm],

    )

    table.setStyle(

        TableStyle(

            [

                (

                    "BACKGROUND",

                    (0, 0),

                    (-1, 0),

                    colors.HexColor("#E8EEF7"),

                ),

                (

                    "GRID",

                    (0, 0),

                    (-1, -1),

                    0.5,

                    colors.grey,

                ),

                (

                    "VALIGN",

                    (0, 0),

                    (-1, -1),

                    "TOP",

                ),

                (

                    "PADDING",

                    (0, 0),

                    (-1, -1),

                    6,

                ),

            ]

        )

    )

    story.append(table)

    story.append(Spacer(1, 12))

    story.append(

        Paragraph(

            "Risk Findings",

            styles["Heading2"],

        )

    )

    if not report.risk_analysis.findings:

        story.append(

            Paragraph(

                "No rule-based findings were generated.",

                styles["BodyText"],

            )

        )

    for finding in report.risk_analysis.findings:

        story.append(

            Paragraph(

                f"<b>{finding.severity}: "
                f"{finding.category}</b>",

                styles["Normal"],

            )

        )

        story.append(

            Paragraph(

                finding.finding,

                styles["BodyText"],

            )

        )

        story.append(

            Paragraph(

                f"Recommendation: {finding.recommendation}",

                styles["BodyText"],

            )

        )

        story.append(Spacer(1, 8))

    story.append(Spacer(1, 12))

    story.append(

        Paragraph(

            "Important Disclaimer",

            styles["Heading2"],

        )

    )

    story.append(

        Paragraph(

            report.risk_analysis.disclaimer,

            styles["BodyText"],

        )

    )

    document.build(story)

    return output_path


# ==========================================================
# 9. API ENDPOINTS
# ==========================================================

@app.get("/")
def home():
    """API health check."""

    return {

        "application": APP_NAME,

        "status": "running",

        "version": "1.0.0",

    }


@app.post(

    "/api/analyze-document",

    response_model=AnalysisReport,

)

async def analyze_document(
    file: UploadFile = File(...),
):
    """
    Upload a PDF and analyze its contents.
    """

    if file.content_type != "application/pdf":

        raise HTTPException(

            status_code=400,

            detail="Only PDF files are accepted.",

        )

    # Read the file and enforce a size limit.

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:

        raise HTTPException(

            status_code=413,

            detail="PDF exceeds the 15 MB limit.",

        )

    if not content.startswith(b"%PDF-"):

        raise HTTPException(

            status_code=400,

            detail="The uploaded file is not a valid PDF.",

        )

    # Store temporarily.

    temporary_path = (
        DATA_DIR
        / f"{uuid.uuid4().hex}.pdf"
    )

    try:

        temporary_path.write_bytes(content)

        # Extract document text.

        text = extract_pdf_text(
            temporary_path
        )

        # Extract structured information.

        extracted_data = (
            extract_document_information(text)
        )

        # Evaluate risk.

        risk_analysis = analyze_property_risk(

            extracted_data,

            text,

        )

        # Create report.

        report = AnalysisReport(

            report_id=str(uuid.uuid4()),

            created_at=datetime.now(
                timezone.utc
            ).isoformat(),

            filename=file.filename or "uploaded.pdf",

            extracted_data=extracted_data,

            risk_analysis=risk_analysis,

        )

        # Save report.

        save_report(report)

        return report

    finally:

        # Remove temporary uploaded file.

        if temporary_path.exists():

            temporary_path.unlink()


@app.get("/api/reports")
def get_report_history():
    """
    Return report history.

    This is a prototype endpoint.
    It is not protected by user authentication.
    """

    with get_connection() as connection:

        rows = connection.execute(

            """
            SELECT
                report_id,
                created_at,
                filename,
                risk_score

            FROM reports

            ORDER BY created_at DESC

            """

        ).fetchall()

    return [

        dict(row)

        for row in rows

    ]


@app.get(
    "/api/reports/{report_id}"
)
def get_report(report_id: str):
    """Retrieve a complete saved report."""

    with get_connection() as connection:

        row = connection.execute(

            """
            SELECT report_json

            FROM reports

            WHERE report_id = ?

            """,

            (report_id,),

        ).fetchone()

    if not row:

        raise HTTPException(

            status_code=404,

            detail="Report not found.",

        )

    return json.loads(
        row["report_json"]
    )


@app.get(
    "/api/reports/{report_id}/pdf"
)
def download_report_pdf(
    report_id: str,
):
    """Generate and download the report PDF."""

    with get_connection() as connection:

        row = connection.execute(

            """
            SELECT report_json

            FROM reports

            WHERE report_id = ?

            """,

            (report_id,),

        ).fetchone()

    if not row:

        raise HTTPException(

            status_code=404,

            detail="Report not found.",

        )

    report = AnalysisReport.model_validate_json(

        row["report_json"]

    )

    pdf_path = export_report_pdf(report)

    return FileResponse(

        path=pdf_path,

        media_type="application/pdf",

        filename=f"PropCheck-{report_id}.pdf",

    )
