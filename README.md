# AGDL Dynamic T&A Tracker - User & Deployment Guide

## 1. Overview
The **AGDL Dynamic T&A Tracker** is a professional, high-performance web tool developed for the Merchandising team at **Aman Knittings Ltd (AGDL)**. It connects directly with the AGDL ERP server (`http://202.51.184.171/agdlerp`) using your credentials (`mishu` / `Mishu@722`) to automate and track Time & Action calendars across all running styles.

---

## 2. Key Features Built

1. **ERP Live Integration**:
   - **User Authentication**: Automated backend session handling via `/AGDLERP/Login/CheckUser`.
   - **Buyer Selection**: Instant dropdown listing of all 80+ buyers (Kmart, Target, Big W, etc.).
   - **Running Styles Filter**: Automatically determines running vs closed styles using ERP BOM status tags (`=>Running`).
   - **Style-wise Costing Items**: Extracted directly from Final Costing details (`LoadCostingDetails`).
   - **Conditional Costing / Non-Costing Milestones**:
     - *Fusing Data Sheet*: Automatically added if Fusing exists in final costing.
     - *Metal Data Sheet*: Automatically added if metal items (Shank, Snap, Ring Poppers, Metal Button, Buckle) exist in final costing.
     - *Standard Basic Milestones*: Pretest, QA Status, GPT Test, PP Status, Overall Close.
   - **Garment Order Qty**: Linked directly from ERP Master OCB / Final Costing.

2. **Sync Inhoused with ERP**:
   - One-click button: Queries ERP BOM (`GetCostingValueVsBookedValue`), refreshes Booked Qty, Received (IH) Qty, and Balance Qty.
   - Items with `Bal Qty <= 0` or marked `Closed`/`Approved` are automatically flagged.

3. **Auto-Hiding & Incremental Weekly Process**:
   - Merchandisers update only pending tasks.
   - Filter checkbox: "Hide Fully Inhoused / Closed Tasks" toggles view cleanly so closed items don't clutter ongoing work.
   - Persistent storage in `tna_data.json` preserves your notes and progress week over week.

4. **Add / Remove Controls**:
   - **Check & Add New Styles from ERP**: Scans ERP and adds newly raised or pending running styles without overwriting existing data.
   - **Add Style Manually**: Manually input style name, revision, and order quantity.
   - **Add Custom Task**: Add special style tasks (e.g. Wash Approval, Barcode Sticker, Fit Sample).
   - **Remove Styles & Tasks**: Delete anytime with 1 click.

5. **Reporting & Sharing**:
   - **Export Excel**: Generates dual-sheet Excel matching your exact Reference T&A format (`Sheet1` Detailed and `Sheet3` Summary).
   - **Email Report Modal**: Generates executive Markdown & rich text summary ready to paste into email to Management.

---

## 3. How to Run Locally (On Office PC / Laptop)
1. Double-click **`Run_TNA_Tracker.bat`** in this folder:
   ```
   D:\OneDrive - Aman Knittings Ltd\Antigravity\T&A Tool - AGDL\Run_TNA_Tracker.bat
   ```
2. The web server starts and your browser will automatically open:
   ```
   http://localhost:5000
   ```
3. To share on your local office network with other team members, they can open:
   ```
   http://<YOUR_PC_IP>:5000
   ```

---

## 4. Free Cloud Server Deployment (Live 24/7 Anywhere)

Because the tool is lightweight and written in Python/Flask with standard `Procfile` and `requirements.txt`, you can deploy it to free hosting platforms in minutes:

### Option A: Render.com (Recommended - 100% Free)
1. Push this folder to a GitHub repository (e.g., `github.com/your-username/agdl-tna-tracker`).
2. Go to [https://render.com](https://render.com) and create a free account.
3. Click **New +** -> **Web Service**.
4. Connect your GitHub repository.
5. Set:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: Free
6. Click **Deploy Web Service**. Render gives you a free live URL (e.g., `https://agdl-tna-tracker.onrender.com`) accessible from anywhere!

> **Network Note on Cloud Deployment**: Since your ERP server IP `202.51.184.171` is a public IP, cloud platforms (Render, Railway, Fly.io) can connect directly to it, allowing your team to sync from anywhere.

### Option B: Railway.app (Free / Low Cost)
1. Connect your GitHub repo on [https://railway.app](https://railway.app).
2. Railway detects Python automatically and deploys using `Procfile`.
