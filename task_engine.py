import re
from typing import List, Dict, Any

# Strict category sorting order: Basic > Fabric > Sewing Accs > Finishing Accs
CATEGORY_ORDER = {
    "Basic": 1,
    "Fabric": 2,
    "Sewing Accs": 3,
    "Finishing Accs": 4
}

# Basic Milestones ordered sequence:
# Any Data Sheet (Fusing/Interlining, Metal) -> Pretest -> QA Status -> PP/Garment Test -> Overall Close -> PP Status -> Style Close
BASIC_ITEM_SEQUENCE = [
    "Fusing / Interlining Data Sheet",
    "Metal Data Sheet",
    "Pretest",
    "QA Status",
    "PP/Garment Test",
    "Overall Close",
    "PP Status",
    "Style Close"
]

# Standard non-costing items required for garments T&A
STANDARD_BASIC_ITEMS = [
    "Pretest",
    "QA Status",
    "PP/Garment Test",
    "Overall Close",
    "PP Status",
    "Style Close"
]

# Metal keywords to detect if Metal Data Sheet should be added
METAL_KEYWORDS = ["shank", "snap", "ring popper", "metal button", "buckle", "rivet", "eyelet"]

# Interlining / Fusing keywords
FUSING_INTERLINING_KEYWORDS = ["fusing", "interlining"]

def get_basic_sort_key(item_name: str) -> int:
    """Returns the sorting rank for Basic items according to user sequence."""
    lower = item_name.lower()
    if "fusing" in lower or "interlining" in lower:
        return 1
    if "metal" in lower:
        return 2
    if "pretest" in lower:
        return 3
    if "qa status" in lower:
        return 4
    if "pp/garment test" in lower or "gpt" in lower or "garment test" in lower:
        return 5
    if "overall close" in lower:
        return 6
    if "pp status" in lower:
        return 7
    if "style close" in lower or "style closing" in lower:
        return 8
    return 10

def categorize_item(item_name: str) -> str:
    """Categorizes items into Fabric, Sewing Accs, Finishing Accs, or Basic."""
    lower = item_name.lower()
    if any(k in lower for k in ["pretest", "qa status", "pp/garment test", "gpt test", "pp status", "overall close", "style close", "data sheet"]):
        return "Basic"
    if any(k in lower for k in ["fabric", "pocketing", "lining", "rib", "denim", "twill", "fusing", "interlining"]):
        return "Fabric"
    if any(k in lower for k in ["thread", "elastic", "tape", "care label", "button", "zipper", "velcro"]):
        return "Sewing Accs"
    if any(k in lower for k in ["poly", "carton", "hanger", "sticker", "tag", "rfid", "gumtape", "drawcord", "draw cord", "sizer"]):
        return "Finishing Accs"
    return "Finishing Accs"

def sort_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sorts tasks strictly:
    1. Category order: Basic > Fabric > Sewing Accs > Finishing Accs.
    2. Inside Basic: Any Data Sheet > Pretest > QA Status > PP/Garment Test > Overall Close > PP Status > Style Close.
    3. Inside other categories: Alphabetical by item name.
    """
    def task_sort_tuple(t: Dict[str, Any]):
        cat = t.get("category", "")
        cat_rank = CATEGORY_ORDER.get(cat, 99)
        if cat == "Basic":
            b_rank = get_basic_sort_key(t.get("item_name", ""))
            return (cat_rank, b_rank, t.get("item_name", ""))
        return (cat_rank, 0, t.get("item_name", ""))

    return sorted(tasks, key=task_sort_tuple)

def generate_style_tasks(
    costing_items: List[Dict[str, Any]],
    bom_items: List[Dict[str, Any]],
    garment_qty: Any = 0
) -> List[Dict[str, Any]]:
    """
    Generates a structured list of tasks and items for a style according to AGDL T&A rules:
    1. Style-wise Costing Items (from Final Costing)
    2. Dynamic Fusing / Interlining Data Sheet:
       - If Fusing or Interlining is in costing, adds 'Fusing / Interlining Data Sheet'
    3. Dynamic Metal Data Sheet:
       - If metal items (Shank, Snap, Ring Poppers, Metal Button, Buckle) are in costing
    4. Non-costing basic milestones in exact order:
       Pretest > QA Status > PP/Garment Test > Overall Close > PP Status > Style Close
    5. Links Booked, Inhoused, Balance Qty from BOM items.
    """
    tasks = []
    task_idx = 1

    has_fusing_or_interlining = False
    has_metal = False

    # Map BOM items by normalized item name for quick IH lookup
    bom_map = {}
    for b in bom_items:
        norm_name = re.sub(r"[^a-zA-Z0-9]", "", b.get("item_name", "").lower())
        bom_map[norm_name] = b

    for ci in costing_items:
        raw_name = ci.get("ItemGroupName") or ci.get("ItemDescription") or ""
        raw_name = raw_name.strip()
        if not raw_name or any(ign in raw_name.lower() for ign in ["wages", "cm", "commission", "courier"]):
            continue

        lower_name = raw_name.lower()
        if any(fk in lower_name for fk in FUSING_INTERLINING_KEYWORDS):
            has_fusing_or_interlining = True
        if any(mk in lower_name for mk in METAL_KEYWORDS):
            has_metal = True

        category = categorize_item(raw_name)

        # Match with BOM in-house data
        norm_ci = re.sub(r"[^a-zA-Z0-9]", "", lower_name)
        matched_bom = bom_map.get(norm_ci)
        if not matched_bom:
            for b_norm, b_data in bom_map.items():
                if b_norm in norm_ci or norm_ci in b_norm:
                    matched_bom = b_data
                    break

        booked_qty = matched_bom["booked_qty"] if matched_bom else float(ci.get("CONSDZN") or 0)
        ih_qty = matched_bom["ih_qty"] if matched_bom else 0.0
        bal_qty = matched_bom["bal_qty"] if matched_bom else booked_qty
        uom = matched_bom["uom"] if matched_bom else (ci.get("UOM") or "")

        if booked_qty > 0:
            if bal_qty <= 0 and ih_qty > 0:
                update_str = f"Fully Inhoused ({ih_qty:g} {uom})"
                status = "Closed"
            elif ih_qty > 0:
                update_str = f"{booked_qty:g} {uom} Booked, {ih_qty:g} {uom} Inhoused, Balance to i/h {bal_qty:g} {uom}"
                status = "In Progress"
            else:
                update_str = f"{booked_qty:g} {uom} Booked, 0 {uom} Inhoused, Balance to i/h {bal_qty:g} {uom}"
                status = "Pending"
        else:
            update_str = "Booking Pending"
            status = "Pending"

        tasks.append({
            "id": f"task_{task_idx}",
            "item_name": raw_name,
            "category": category,
            "is_costing": True,
            "garment_qty": garment_qty,
            "uom": uom,
            "booked_qty": booked_qty,
            "ih_qty": ih_qty,
            "bal_qty": bal_qty,
            "updates": update_str,
            "task_notes": "",
            "color_approval": "Approved" if status == "Closed" else "Pending",
            "status": status,
            "is_hidden": False
        })
        task_idx += 1

    # 1. Add Fusing / Interlining Data Sheet if applicable
    if has_fusing_or_interlining:
        tasks.append({
            "id": f"task_{task_idx}",
            "item_name": "Fusing / Interlining Data Sheet",
            "category": "Basic",
            "is_costing": False,
            "garment_qty": garment_qty,
            "uom": "Pcs",
            "booked_qty": 0,
            "ih_qty": 0,
            "bal_qty": 0,
            "updates": "Pending",
            "task_notes": "Follow up fusing/interlining test & data sheet",
            "color_approval": "N/A",
            "status": "Pending",
            "is_hidden": False
        })
        task_idx += 1

    # 2. Add Metal Data Sheet if applicable
    if has_metal:
        tasks.append({
            "id": f"task_{task_idx}",
            "item_name": "Metal Data Sheet",
            "category": "Basic",
            "is_costing": False,
            "garment_qty": garment_qty,
            "uom": "Pcs",
            "booked_qty": 0,
            "ih_qty": 0,
            "bal_qty": 0,
            "updates": "Pending",
            "task_notes": "Follow up metal calibration report",
            "color_approval": "N/A",
            "status": "Pending",
            "is_hidden": False
        })
        task_idx += 1

    # 3. Add Standard Non-Costing Milestones in exact sequence
    for std_name in STANDARD_BASIC_ITEMS:
        tasks.append({
            "id": f"task_{task_idx}",
            "item_name": std_name,
            "category": "Basic",
            "is_costing": False,
            "garment_qty": garment_qty,
            "uom": "",
            "booked_qty": 0,
            "ih_qty": 0,
            "bal_qty": 0,
            "updates": "Pending",
            "task_notes": "",
            "color_approval": "Pending",
            "status": "Pending",
            "is_hidden": False
        })
        task_idx += 1

    return sort_tasks(tasks)

def is_task_completed(task: Dict[str, Any]) -> bool:
    """Checks if a task/item is fully closed, completed, or inhoused."""
    status = (task.get("status") or "").lower()
    updates = (task.get("updates") or "").lower()
    
    closed_keywords = ["closed", "approved", "done", "completed", "fully inhoused"]
    if any(k in status for k in closed_keywords):
        return True
    if any(k in updates for k in closed_keywords):
        return True

    booked = float(task.get("booked_qty") or 0)
    ih = float(task.get("ih_qty") or 0)
    bal = float(task.get("bal_qty") or 0)
    if booked > 0 and ih >= booked and bal <= 0:
        return True

    return False
