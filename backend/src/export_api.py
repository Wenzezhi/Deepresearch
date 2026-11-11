
from io import BytesIO
import re
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH


router = APIRouter(prefix="/export", tags=["report-export"])


class ExportRequest(BaseModel):
    title: str = Field(default="研究报告", max_length=200)
    markdown: str = Field(..., min_length=1, max_length=2_000_000)


def add_markdown_to_doc(document: Document, markdown: str):
    """将常见 Markdown 内容转换为 Word 段落和表格。"""
    lines = markdown.splitlines()
    paragraph_buffer = []

    def flush_paragraph():
        if paragraph_buffer:
            text = " ".join(paragraph_buffer).strip()
            if text:
                document.add_paragraph(text)
            paragraph_buffer.clear()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            flush_paragraph()
            i += 1
            continue

        if line.startswith("```"):
            flush_paragraph()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            p = document.add_paragraph()
            run = p.add_run("\n".join(code_lines))
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            level = min(len(heading.group(1)), 3)
            document.add_heading(heading.group(2), level=level)
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines):
            separator = lines[i + 1].strip()
            if re.match(r"^\|?[\s:|-]+\|?$", separator):
                flush_paragraph()
                rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    cells = [
                        cell.strip()
                        for cell in lines[i].strip().strip("|").split("|")
                    ]
                    if not all(re.fullmatch(r"[:\-\s]+", c or "-") for c in cells):
                        rows.append(cells)
                    i += 1

                if rows:
                    width = max(len(row) for row in rows)
                    table = document.add_table(rows=0, cols=width)
                    table.style = "Table Grid"
                    for row_index, values in enumerate(rows):
                        cells = table.add_row().cells
                        for col_index in range(width):
                            value = values[col_index] if col_index < len(values) else ""
                            cells[col_index].text = value
                            if row_index == 0:
                                for run in cells[col_index].paragraphs[0].runs:
                                    run.bold = True
                continue

        if line.startswith(("- ", "* ", "+ ")):
            flush_paragraph()
            document.add_paragraph(line[2:], style="List Bullet")
            i += 1
            continue

        if re.match(r"^\d+[.)]\s+", line):
            flush_paragraph()
            text = re.sub(r"^\d+[.)]\s+", "", line)
            document.add_paragraph(text, style="List Number")
            i += 1
            continue

        if line.startswith(">"):
            flush_paragraph()
            document.add_paragraph(line.lstrip("> ").strip(), style="Quote")
            i += 1
            continue

        paragraph_buffer.append(line)
        i += 1

    flush_paragraph()


@router.post("/word")
def export_word(payload: ExportRequest):
    document = Document()

    section = document.sections[0]
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.8)
    section.right_margin = Cm(2.8)

    normal = document.styles["Normal"]
    normal.font.name = "宋体"
    normal.font.size = Pt(11)

    title = document.add_heading(payload.title, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    add_markdown_to_doc(document, payload.markdown)

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": 'attachment; filename="research-report.docx"'
        },
    )
