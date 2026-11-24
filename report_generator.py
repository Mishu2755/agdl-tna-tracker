import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

BD_TZ = timezone(timedelta(hours=6))

def get_bd_now() -> datetime:
    return datetime.now(BD_TZ)

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm

from task_engine import CATEGORY_ORDER, sort_tasks

def generate_excel_report(storage_data: Dict[str, Any], output_path: Path) -> Path:
    """
    Generates a high-quality Excel T&A Report:
    - Sheet1: Full Detailed Tracking (Freeze Pane at Row 1, Color Approval column, Category sorting)
    - Sheet3: Executive Summary (Freeze Pane at Row 1)
    """
    wb = openpyxl.Workbook()
    
    # ------------------ SHEET 1: Detailed T&A ------------------
    ws1 = wb.active
    ws1.title = "Sheet1"
    ws1.freeze_panes = "A2" # Freeze 1st row
    
    headers1 = [
        "Style", "Garment Qty (Pcs)", "Item Category", "Items", 
        f"Updates ({get_bd_now().strftime('%d-%m-%y')})", "Tasks", 
        "UOM", "Book Qty", "I/H Qty", "Bal Qty", "Color Approval", "Status"
    ]
    
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )
    
    ws1.append(headers1)
    for col in range(1, len(headers1) + 1):
        cell = ws1.cell(1, col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    styles = storage_data.get("styles", {})
    row_idx = 2

    for style_id, s_info in styles.items():
        style_name = s_info.get("style_name") or style_id
        g_qty = s_info.get("garment_qty", 0)
        tasks = sort_tasks(s_info.get("tasks", []))

        for t in tasks:
            if t.get("is_hidden"):
                continue

            ws1.append([
                style_name,
                g_qty,
                t.get("category", ""),
                t.get("item_name", ""),
                t.get("updates", ""),
                t.get("task_notes", "") if str(t.get("task_notes", "")).strip() != "0" else "",
                t.get("uom", ""),
                t.get("booked_qty", 0),
                t.get("ih_qty", 0),
                t.get("bal_qty", 0),
                t.get("color_approval", ""),
                t.get("status", "")
            ])

            fill_color = "F2F5F9" if row_idx % 2 == 0 else "FFFFFF"
            status_val = str(t.get("status", "")).lower()
            if "closed" in status_val or "approved" in status_val or "done" in status_val:
                fill_color = "E2EFDA"
            elif "pending" in status_val and float(t.get("bal_qty") or 0) > 0:
                fill_color = "FFF2CC"

            for c in range(1, len(headers1) + 1):
                cell = ws1.cell(row_idx, c)
                cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
                cell.border = thin_border
                cell.font = Font(name="Calibri", size=9)
                if c in [2, 8, 9, 10]:
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                elif c in [1, 3, 4, 7, 11, 12]:
                    cell.alignment = Alignment(horizontal="left", vertical="center")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

            row_idx += 1

    # ------------------ SHEET 3: Executive Summary ------------------
    ws3 = wb.create_sheet(title="Sheet3")
    ws3.freeze_panes = "A2" # Freeze 1st row
    headers3 = ["Style", "Garment Qty (Pcs)", "Item Category", "Items", f"Updates ({get_bd_now().strftime('%d-%m-%y')})", "Tasks"]
    ws3.append(headers3)
    
    header_fill3 = PatternFill(start_color="203764", end_color="203764", fill_type="solid")
    for col in range(1, len(headers3) + 1):
        cell = ws3.cell(1, col)
        cell.font = header_font
        cell.fill = header_fill3
        cell.alignment = Alignment(horizontal="center", vertical="center")

    r3_idx = 2
    for style_id, s_info in styles.items():
        style_name = s_info.get("style_name") or style_id
        g_qty = s_info.get("garment_qty", 0)
        tasks = sort_tasks(s_info.get("tasks", []))

        is_first_row = True
        for t in tasks:
            if t.get("is_hidden"):
                continue

            ws3.append([
                style_name if is_first_row else "",
                g_qty if is_first_row else "",
                t.get("category", ""),
                t.get("item_name", ""),
                t.get("updates", ""),
                t.get("task_notes", "") if str(t.get("task_notes", "")).strip() != "0" else ""
            ])
            is_first_row = False

            fill_c = "F9FAFB" if r3_idx % 2 == 0 else "FFFFFF"
            for c in range(1, len(headers3) + 1):
                cell = ws3.cell(r3_idx, c)
                cell.fill = PatternFill(start_color=fill_c, end_color=fill_c, fill_type="solid")
                cell.border = thin_border
                cell.font = Font(name="Calibri", size=9)

            r3_idx += 1

    for ws in [ws1, ws3]:
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 50)

    wb.save(output_path)
    return output_path

def generate_pdf_report(storage_data: Dict[str, Any], output_path: Path) -> Path:
    """
    Generates a professional A4 Landscape PDF T&A report:
    - Formatted to fit printable A4 page width perfectly (297mm x 210mm).
    - Compact typography and clean table layout.
    - Category sorted: Basic > Fabric > Sewing Accs > Finishing Accs.
    """
    # A4 Landscape: width = 297mm (841.89 pt), height = 210mm (595.27 pt)
    # Printable margin: 8mm each side -> usable width ~ 841.89 - (16mm in pt) ~ 796 pt
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0f172a")
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#475569")
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.5,
        leading=8,
        textColor=colors.HexColor("#1e293b")
    )
    cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a")
    )
    cell_header = ParagraphStyle(
        "TableHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.white,
        alignment=1 # Center
    )

    buyer_name = storage_data.get("selected_buyer", {}).get("name", "All Buyers")
    now_str = get_bd_now().strftime("%d-%b-%Y %I:%M %p")

    elements = []

    # Header block
    elements.append(Paragraph(f"<b>AGDL T&amp;A TRACKER</b>", title_style))
    elements.append(Paragraph(f"<b>Aman Graphics &amp; Designs Ltd.</b> | Buyer: <b>{buyer_name}</b> | Status: <b>Active Running Styles</b> | Generated: {now_str}", subtitle_style))
    elements.append(Spacer(1, 4 * mm))

    # Column widths summing to 796 pt
    # Style (90), GarmentQty (42), Category (54), Item (95), Updates (190), TaskNotes (120), Book (42), IH (42), Bal (42), Status (42), ColorAppr (37)
    col_widths = [90, 42, 54, 95, 185, 115, 42, 42, 42, 45, 44]

    headers = [
        Paragraph("Style", cell_header),
        Paragraph("Garment Qty", cell_header),
        Paragraph("Category", cell_header),
        Paragraph("Item / Event", cell_header),
        Paragraph("Latest Updates", cell_header),
        Paragraph("Task / Action Note", cell_header),
        Paragraph("Book Qty", cell_header),
        Paragraph("I/H Qty", cell_header),
        Paragraph("Bal Qty", cell_header),
        Paragraph("Status", cell_header),
        Paragraph("Color Appr.", cell_header),
    ]

    table_data = [headers]
    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94a3b8")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
    ]

    all_styles = storage_data.get("styles", {})
    row_idx = 1

    for style_id, s_info in all_styles.items():
        style_name = s_info.get("style_name") or style_id
        try:
            g_qty = int(float(s_info.get("garment_qty") or 0))
        except Exception:
            g_qty = 0
        tasks = sort_tasks(s_info.get("tasks", []))

        is_first = True
        for t in tasks:
            if t.get("is_hidden"):
                continue

            status_txt = str(t.get("status", "")).strip()
            is_closed = status_txt.lower() in ["closed", "approved", "done", "completed"]
            bg_color = colors.HexColor("#f0fdf4") if is_closed else (colors.HexColor("#f8fafc") if row_idx % 2 == 0 else colors.white)

            table_styles.append(("BACKGROUND", (0, row_idx), (-1, row_idx), bg_color))

            b_qty = float(t.get("booked_qty") or 0)
            ih_qty = float(t.get("ih_qty") or 0)
            bal_qty = float(t.get("bal_qty") or 0)
            uom = t.get("uom", "")

            b_str = f"{b_qty:g} {uom}" if b_qty > 0 else "-"
            ih_str = f"{ih_qty:g} {uom}" if ih_qty > 0 else "0"
            bal_str = f"{bal_qty:g} {uom}" if bal_qty > 0 else "0"

            row = [
                Paragraph(style_name if is_first else "", cell_bold),
                Paragraph(f"{g_qty:,}" if is_first else "", cell_style),
                Paragraph(t.get("category", ""), cell_style),
                Paragraph(t.get("item_name", ""), cell_bold),
                Paragraph(t.get("updates", ""), cell_style),
                Paragraph(t.get("task_notes", "") if str(t.get("task_notes", "")).strip() != "0" else "", cell_style),
                Paragraph(b_str, cell_style),
                Paragraph(ih_str, cell_style),
                Paragraph(bal_str, cell_style),
                Paragraph(status_txt, cell_style),
                Paragraph(t.get("color_approval", ""), cell_style),
            ]
            table_data.append(row)
            is_first = False
            row_idx += 1

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(table_styles))
    elements.append(t)

    doc.build(elements)
    return output_path
