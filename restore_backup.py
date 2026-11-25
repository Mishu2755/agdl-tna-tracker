"""
AGDL T&A Recovery Helper:
Restores task notes, latest updates, and statuses from an exported Excel report file.
"""
import sys
import openpyxl
from pathlib import Path
from storage import TNAStorage

def restore_from_excel(excel_path: str):
    file_path = Path(excel_path)
    if not file_path.exists():
        print(f"[ERROR] File not found: {excel_path}")
        return

    print(f"[INFO] Opening {file_path.name}...")
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active # Sheet1

    store = TNAStorage()
    styles = store.get_styles()

    restored_count = 0
    # Headers in Sheet1:
    # Col 1: Style, Col 2: Garment Qty, Col 3: Category, Col 4: Items, Col 5: Updates, Col 6: Tasks (Notes), Col 11: Color Approval, Col 12: Status
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        style_name = str(row[0]).strip()
        item_name = str(row[3] or "").strip().lower()
        updates = str(row[4] or "").strip()
        task_notes = str(row[5] or "").strip()
        color_approval = str(row[10] or "").strip() if len(row) > 10 else ""
        status = str(row[11] or "").strip() if len(row) > 11 else ""

        # Find matching style
        matched_style = None
        for sid, s in styles.items():
            if s.get("style_name", "").strip().lower() == style_name.lower():
                matched_style = s
                break
        
        if not matched_style:
            continue

        for t in matched_style.get("tasks", []):
            if t.get("item_name", "").strip().lower() == item_name:
                updated = False
                if updates and updates != "Pending" and updates != t.get("updates"):
                    t["updates"] = updates
                    updated = True
                if task_notes and task_notes != "0" and task_notes != t.get("task_notes"):
                    t["task_notes"] = task_notes
                    updated = True
                if color_approval and color_approval != "Pending" and color_approval != t.get("color_approval"):
                    t["color_approval"] = color_approval
                    updated = True
                if status and status != t.get("status"):
                    t["status"] = status
                    updated = True
                
                if updated:
                    restored_count += 1

    store.save()
    print(f"[SUCCESS] Restored {restored_count} task entries from Excel into tna_data.json!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        restore_from_excel(sys.argv[1])
    else:
        print("Usage: python restore_backup.py <path_to_excel_file.xlsx>")
