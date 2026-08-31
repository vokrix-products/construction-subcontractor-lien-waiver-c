import os
import io
import json
import csv
import datetime

from openai import OpenAI

ALLOWED_STATUSES = [
    "missing:critical",
    "draft:warning",
    "requested:warning",
    "opened_viewed:warning",
    "signed:good",
    "notarized:good",
    "valid:good",
    "flagged:critical",
    "rejected:critical",
    "expired:critical",
    "conditional_received:warning",
    "unconditional_needed:warning",
    "payment_confirmed:good",
    "matched_ready_to_release:good",
    "blocked:critical",
    "overdue:critical",
    "not_required:good",
]
ALLOWED_STATUSES_SET = set(ALLOWED_STATUSES)

WAIVER_FIELDS = [
    "project_name",
    "project_owner_entity",
    "general_contractor_name",
    "hiring_party_customer_name",
    "subcontractor_or_supplier_company_name",
    "trade_scope_description",
    "waiver_type",
    "waiver_period_start_date",
    "waiver_period_end_date",
    "invoice_or_pay_application_number",
    "invoice_or_pay_application_amount",
    "approved_amount",
    "amount_paid_to_date",
    "retainage_amount_or_percentage",
    "waiver_amount_listed",
    "date_waiver_generated",
    "date_waiver_requested_sent",
    "date_waiver_due_deadline",
    "date_waiver_signed",
    "date_waiver_notarized",
    "notary_name_and_commission_expiration",
    "signer_name",
    "signer_email",
    "signer_role_title",
    "document_id_file_name",
    "source_file_type",
    "e_signature_provider_reference_envelope_id",
    "payment_confirmation_date",
    "payment_confirmation_amount",
    "source_system_quickbooks_procore_sage_xero",
]


def _parse_date(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("none", "null", "n/a", ""):
        return None
    try:
        return datetime.date.fromisoformat(s.split("T")[0]).isoformat()
    except Exception:
        pass
    try:
        return datetime.date.fromisoformat(s).isoformat()
    except Exception:
        pass
    return None


def _map_status(value):
    v = str(value).lower().strip().replace(" ", "_").replace("-", "_")
    mapping = {
        "missing": "missing:critical",
        "draft": "draft:warning",
        "requested": "requested:warning",
        "opened": "opened_viewed:warning",
        "viewed": "opened_viewed:warning",
        "signed": "signed:good",
        "notarized": "notarized:good",
        "valid": "valid:good",
        "flagged": "flagged:critical",
        "rejected": "rejected:critical",
        "expired": "expired:critical",
        "conditional_received": "conditional_received:warning",
        "conditional": "conditional_received:warning",
        "unconditional_needed": "unconditional_needed:warning",
        "payment_confirmed": "payment_confirmed:good",
        "payment": "payment_confirmed:good",
        "matched_ready_to_release": "matched_ready_to_release:good",
        "matched": "matched_ready_to_release:good",
        "ready_to_release": "matched_ready_to_release:good",
        "blocked": "blocked:critical",
        "overdue": "overdue:critical",
        "not_required": "not_required:good",
        "waived": "not_required:good",
    }
    return mapping.get(v, "not_required:good")


def _find_due_date(row):
    for key, value in row.items():
        if any(token in key.lower() for token in ("due", "deadline")):
            parsed = _parse_date(value)
            if parsed:
                return parsed
    return None


def _extract_title_from_row(row):
    candidates = [
        "subcontractor_or_supplier_company_name",
        "subcontractor_company_name",
        "supplier_company_name",
        "subcontractor",
        "supplier",
        "vendor_name",
        "vendor",
        "company_name",
        "project_name",
        "name",
        "title",
    ]
    for key in candidates:
        if key in row:
            val = str(row[key]).strip()
            if val:
                return val
    for v in row.values():
        if v and str(v).strip():
            return str(v).strip()
    return "Untitled"


def _fallback_records(text):
    lines = text.splitlines()
    if not lines:
        return [{"title": "Untitled", "status": "not_required:good", "details": {"raw_text": text}, "due_date": None}]
    first_line = lines[0]
    delimiter = None
    if "," in first_line:
        delimiter = ","
    elif "\t" in first_line:
        delimiter = "\t"
    elif ";" in first_line:
        delimiter = ";"

    if delimiter is not None:
        try:
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            rows = list(reader)
            if rows:
                records = []
                for row in rows:
                    title = _extract_title_from_row(row)
                    details = {}
                    for k, v in row.items():
                        if v is not None and str(v).strip() != "":
                            details[k] = str(v).strip()
                    status = "not_required:good"
                    for k, v in row.items():
                        if k.lower() in ("status", "waiver_status", "document_status"):
                            status = _map_status(v)
                            break
                    due_date = _find_due_date(row)
                    records.append({
                        "title": title,
                        "status": status,
                        "details": details,
                        "due_date": due_date,
                    })
                return records
        except Exception:
            pass

    return [{"title": "Untitled", "status": "not_required:good", "details": {"raw_text": text}, "due_date": None}]


def _parse_json_records(content):
    try:
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
        data = json.loads(content)
        if isinstance(data, dict):
            data = [data]
        records = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            status = item.get("status") or "not_required:good"
            if status not in ALLOWED_STATUSES_SET:
                status = _map_status(status)
            due_date = _parse_date(item.get("due_date"))
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            clean_details = {str(k): (str(v) if v is not None else "") for k, v in details.items()}
            records.append({
                "title": title,
                "status": status,
                "due_date": due_date,
                "details": clean_details,
            })
        return records
    except Exception:
        return []


def process_file(file_bytes: bytes) -> list:
    if not isinstance(file_bytes, bytes):
        raise TypeError("file_bytes must be bytes")

    text = ""

    # 1) Try pdfplumber first
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_texts = []
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                page_texts.append(page_text)
            text = "\n".join(page_texts).strip()
    except Exception:
        pass

    # 2) Try openpyxl when PDF extraction found no text
    if not text:
        try:
            import openpyxl
            workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
            rows = []
            for sheet in workbook.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    rows.append("\t".join("" if cell is None else str(cell) for cell in row))
            text = "\n".join(rows).strip()
        except Exception:
            pass

    # 3) Fallback to UTF-8 text/CSV decode, then latin-1 if needed
    if not text:
        try:
            text = file_bytes.decode("utf-8", errors="ignore").strip()
        except Exception:
            text = file_bytes.decode("latin-1", errors="ignore").strip()

    if not text:
        return [{"title": "Untitled", "status": "not_required:good", "details": {"raw_text": ""}, "due_date": None}]

    # Prefer DeepSeek extraction when configured
    try:
        ai_records = _extract_with_deepseek(text)
        if ai_records:
            return ai_records
    except Exception:
        pass

    return _fallback_records(text)
