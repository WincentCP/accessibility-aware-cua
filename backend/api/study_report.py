"""Generate a concise local PDF report for one completed participant session."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _register_fonts() -> tuple[str, str]:
    regular = "Vera"
    bold = "VeraBd"
    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    if regular not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular, font_dir / "Vera.ttf"))
    if bold not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(bold, font_dir / "VeraBd.ttf"))
    return regular, bold


def _duration(start: str | None, end: str | None) -> str:
    if not start or not end:
        return "Belum tersedia"
    seconds = max(0, int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()))
    minutes, remaining = divmod(seconds, 60)
    return f"{minutes} menit {remaining} detik"


def build_study_report(result: dict[str, Any]) -> bytes:
    regular, bold = _register_fonts()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Laporan Sesi Penelitian",
        author="Accessibility-Aware CUA",
    )
    sample = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle", parent=sample["Title"], fontName=bold, fontSize=19,
        leading=24, textColor=colors.HexColor("#243141"), alignment=TA_CENTER,
    )
    heading = ParagraphStyle(
        "ReportHeading", parent=sample["Heading2"], fontName=bold, fontSize=12,
        leading=16, spaceBefore=12, spaceAfter=7, textColor=colors.HexColor("#315f73"),
    )
    body = ParagraphStyle(
        "ReportBody", parent=sample["BodyText"], fontName=regular, fontSize=9,
        leading=13, textColor=colors.HexColor("#243141"),
    )
    small = ParagraphStyle("ReportSmall", parent=body, fontSize=7.5, leading=10)

    events = list(result.get("events") or [])
    event_counts = Counter(str(item.get("kind", "UNKNOWN")) for item in events)
    completed_at = next(
        (str(item.get("at")) for item in reversed(events) if item.get("kind") == "SESSION_COMPLETED"),
        None,
    )
    task_rows: list[list[str]] = [["Kegiatan", "Hasil", "Durasi"]]
    active: dict[str, str] = {}
    for event in events:
        kind = event.get("kind")
        task_id = str(event.get("task_id", ""))
        if kind == "TASK_STARTED":
            active[task_id] = str(event.get("at"))
        elif kind == "TASK_COMPLETED":
            task_rows.append([
                task_id,
                str(event.get("outcome", "Tidak tersedia")),
                _duration(active.get(task_id), str(event.get("at"))),
            ])

    profile_rows = [
        ["Nama", result.get("participant_name") or "Tidak tersedia"],
        ["Ejaan nama", result.get("participant_name_spelling") or "Tidak tersedia"],
        ["Kelas", result.get("participant_class") or "Tidak tersedia"],
        ["Umur", f"{result.get('participant_age')} tahun" if result.get("participant_age") else "Tidak tersedia"],
        ["Kode sesi", result.get("participant_code") or "Tidak tersedia"],
    ]
    summary_rows = [
        ["Status", result.get("status", "Tidak tersedia")],
        ["Durasi sesi", _duration(result.get("created_at"), completed_at)],
        ["Kegiatan selesai", f"{result.get('task_index', 0)} dari {result.get('task_count', 0)}"],
        ["Peserta di bawah umur", "Ya" if result.get("is_minor") else "Tidak"],
        [
            "Persetujuan wali (prosedur eksternal)",
            "Terkonfirmasi" if result.get("guardian_consent_confirmed") else "Belum tercatat",
        ],
        ["Status rekaman", result.get("recording_state", "Tidak tersedia")],
        ["Pengulangan instruksi", str(event_counts["TASK_INSTRUCTION_REPEAT"])],
        ["Bantuan karena kebingungan", str(event_counts["GUIDANCE_EVENT"])],
        ["Intervensi peneliti", str(event_counts["RESEARCHER_INTERVENTION"])],
    ]

    def data_table(rows: list[list[Any]], widths: list[float]) -> Table:
        normalized = [[Paragraph(escape(str(cell)), body) for cell in row] for row in rows]
        table = Table(normalized, colWidths=widths, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), regular),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e3f0f3")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#243141")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d0db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return table

    story: list[Any] = [
        Paragraph("Laporan Sesi Penelitian", title),
        Paragraph("Accessibility-Aware Computer-Use Agent", body),
        Spacer(1, 8 * mm),
        Paragraph("Profil peserta", heading),
        data_table(profile_rows, [45 * mm, 112 * mm]),
        Paragraph("Ringkasan sesi", heading),
        data_table(summary_rows, [55 * mm, 102 * mm]),
        Paragraph("Hasil setiap kegiatan", heading),
    ]
    if len(task_rows) > 1:
        task_table = Table(
            [[Paragraph(escape(str(cell)), body) for cell in row] for row in task_rows],
            colWidths=[28 * mm, 72 * mm, 57 * mm],
            repeatRows=1,
        )
        task_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#315f73")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d0db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(task_table)
    else:
        story.append(Paragraph("Belum ada kegiatan yang tercatat selesai.", body))

    feedback = (result.get("feedback") or {}).get("text") or "Tidak ada feedback."
    story.extend([
        Paragraph("Feedback peserta", heading),
        Paragraph(escape(str(feedback)), body),
        PageBreak(),
        Paragraph("Transkrip percakapan", heading),
    ])
    utterances = list(result.get("utterances") or [])
    if utterances:
        for item in utterances:
            story.append(Paragraph(
                f"{escape(str(item.get('at', '')))}: {escape(str(item.get('text', '')))}",
                small,
            ))
            story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph("Belum ada transkrip.", body))
    story.extend([
        Spacer(1, 6 * mm),
        Paragraph(
            "Catatan privasi: laporan ini memuat data pribadi peserta. Simpan secara terbatas sesuai prosedur penelitian dan jangan masukkan ke Git.",
            small,
        ),
    ])
    document.build(story)
    return buffer.getvalue()
