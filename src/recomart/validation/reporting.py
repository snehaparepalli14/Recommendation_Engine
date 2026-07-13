from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json_report(destination: Path, report: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_pdf_report(destination: Path, report: dict[str, Any]) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    body_style = styles["BodyText"]
    body_style.fontSize = 8
    body_style.leading = 10

    def paragraph(value: object) -> Paragraph:
        safe_text = (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return Paragraph(safe_text, body_style)

    def make_table(rows: list[list[object]], widths: list[float]) -> Table:
        table = Table(
            [[paragraph(cell) for cell in row] for row in rows],
            colWidths=widths,
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B7C9D6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    def add_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5B6573"))
        canvas.drawString(
            document.leftMargin,
            0.45 * inch,
            "RecoMart - Data Quality Report",
        )
        canvas.drawRightString(
            letter[0] - document.rightMargin,
            0.45 * inch,
            f"Page {document.page}",
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(destination),
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.7 * inch,
    )

    story: list[Any] = [
        Paragraph("RecoMart Data Quality Report", title_style),
        Spacer(1, 8),
        paragraph(
            f"Validation run ID: {report['run_id']}<br/>"
            f"Generated: {report['generated_at']}<br/>"
            f"Overall quality-gate status: <b>{report['status']}</b>"
        ),
        Spacer(1, 10),
        Paragraph("Quality-gate summary", heading_style),
    ]

    summary_rows: list[list[object]] = [
        ["Dataset", "Total", "Valid", "Invalid", "Pass rate", "Duplicates"]
    ]

    for entity, profile in report["datasets"].items():
        summary_rows.append(
            [
                entity,
                profile["total_records"],
                profile["valid_records"],
                profile["invalid_records"],
                f"{profile['pass_rate_percent']:.2f}%",
                profile["duplicate_count"],
            ]
        )

    story.append(
        make_table(
            summary_rows,
            [1.2 * inch, 0.65 * inch, 0.65 * inch, 0.65 * inch, 0.8 * inch, 0.8 * inch],
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        paragraph(
            "The validation process completes with issues when records are "
            "quarantined. It fails only when required raw source files are missing."
        )
    )

    for entity, profile in report["datasets"].items():
        story.append(PageBreak())
        story.append(Paragraph(f"{entity.title()} details", heading_style))
        story.append(
            paragraph(
                f"Source: {profile['source_file']}<br/>"
                f"Valid output: {profile['valid_output']}<br/>"
                f"Quarantine output: {profile['quarantine_output']}"
            )
        )
        story.append(Spacer(1, 8))

        missing_rows: list[list[object]] = [
            ["Field", "Missing count", "Missing percentage"]
        ]

        for field, values in profile["missing_values"].items():
            missing_rows.append(
                [field, values["count"], f"{values['percent']:.2f}%"]
            )

        story.append(Paragraph("Missing-value summary", heading_style))
        story.append(
            make_table(missing_rows, [3.4 * inch, 1.5 * inch, 1.5 * inch])
        )
        story.append(Spacer(1, 8))

        failure_rows: list[list[object]] = [["Rule", "Failure count"]]

        for rule, count in profile["rule_failures"].items():
            failure_rows.append([rule, count])

        if len(failure_rows) == 1:
            failure_rows.append(["No failures", 0])

        story.append(Paragraph("Rule-failure summary", heading_style))
        story.append(make_table(failure_rows, [4.8 * inch, 1.6 * inch]))
        story.append(Spacer(1, 8))
        story.append(Paragraph("Observation", heading_style))
        story.append(paragraph(profile["observation"]))

    document.build(story, onFirstPage=add_footer, onLaterPages=add_footer)