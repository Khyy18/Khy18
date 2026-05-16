"""Pydantic models for OCR endpoints."""

from typing import Dict

from pydantic import BaseModel, Field


class OcrProcessRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded image")
    filename: str = Field(default="document.jpg", max_length=255)


class OcrField(BaseModel):
    key: str
    value: str
    confidence: float = 1.0


class OcrProcessResponse(BaseModel):
    doc_type: str = Field(..., description="Type: invoice/timesheet/receipt/payslip/unknown")
    fields: Dict[str, str] = Field(default_factory=dict)
    raw_text: str = ""


class OcrToExcelRequest(BaseModel):
    doc_type: str
    fields: Dict[str, str]
    title: str = "\u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043d\u044b\u0439 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442"
