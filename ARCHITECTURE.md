# AGDL Dynamic T&A Tracker - System Architecture & Plan

## 1. Overview
The AGDL Dynamic T&A Tracker is a high-performance web-based Time & Action management tool designed for Merchandising Managers and merchandisers at Aman Knittings Ltd. It connects seamlessly to the live AGDL ERP system (`http://202.51.184.171/agdlerp`) using the verified credentials (`mishu` / `Mishu@722`).

## 2. Core Functional Modules
1. **ERP Authentication & Session Manager (`erp_client.py`)**:
   - High-speed direct REST API session (`/AGDLERP/Login/CheckUser`).
   - Retrieves active buyers via `/MarchantModule/FinalCosting/LoadBuyer`.
   - Discovers styles for any buyer via `/MarchantModule/FinalCosting/LoadStyle`.
   - Identifies "Running" vs "Closed" styles automatically using `/Procurement/BOM/LoadBOMStyle` status tag (`=>Running` or `=>Closed`).
   - Fetches garment quantity and style metadata via `/MarchantModule/FinalCosting/LoadOCB`.
   - Fetches style-wise costing items list via `/MarchantModule/FinalCosting/LoadCostingDetails`.
   - Checks In-house (IH) status, booked qty, received qty, and balance qty via `/Procurement/BOM/GetCostingValueVsBookedValue`.

2. **Costing & Non-Costing Item Dynamic Generator**:
   - **Costing Items**: Extracted directly from Final Costing details (Fabric, Trims, Pocketing, Sewing Thread, Care label, Poly, Carton, etc.).
   - **Conditional Costing / Non-Costing Additions**:
     - *Fusing Data Sheet*: Automatically added if 'Fusing' exists in the style's costing items.
     - *Metal Data Sheet*: Automatically added if metal items (Shank / Snap / Ring Poppers / Metal Button / Buckle) exist in final costing.
   - **Standard Non-Costing Milestones (Basic)**:
     - Pretest
     - QA Status
     - GPT Test
     - PP Status
     - Overall Close
   - Garment Order Qty automatically linked to each row.

3. **Incremental Weekly Persistence (`storage.py`)**:
   - Stores all active styles, tasks, updates, and statuses in a local structured JSON/SQLite database (`tna_data.json`).
   - Once a merchandiser writes comments, updates, or tasks, they are permanently stored.
   - When returning next day/week, merchandisers only update pending tasks.
   - Auto-Closing Filter: Any task/item marked as `Closed`, `Approved`, `Done`, `Completed`, or with `Bal Qty <= 0` (and fully received) can be auto-hidden from pending views while preserved in history.

4. **Sync & Management Actions**:
   - **"Sync Inhoused with ERP"**: Reconnects with ERP, refreshes Booked, Inhoused (IH), and Balance Qty, and flags completed items.
   - **"Check & Add New Styles from ERP"**: Checks ERP for newly added or pending styles under the selected buyer and adds them without overwriting existing data.
   - **Manual Style Controls**: Add or remove styles manually anytime.
   - **Manual Task Controls**: Add, remove, or edit custom tasks, categories, and deadlines.

5. **Executive T&A Report Generator**:
   - Professional HTML view with real-time status badges, summary metrics (Total Styles, Pending Actions, Inhoused %, Overdue Tasks).
   - Instant 1-Click Excel Export formatted identically to the reference T&A Excel workbook (`Sheet3` and `Sheet1` formats).
   - "Copy Email Summary" button generating a clean Markdown / rich-text email briefing ready to paste into Outlook or Gmail.

6. **Free Cloud Deployment Ready**:
   - Packaged with standard `requirements.txt`, `Procfile`, and instructions for 100% free hosting on platforms like Render.com, Railway, Fly.io, or Hugging Face Spaces, as well as 1-click local Windows execution via `.bat`.
