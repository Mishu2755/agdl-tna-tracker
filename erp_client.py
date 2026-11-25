import requests
import json
import logging
import datetime
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ERPClient")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_URL = "http://202.51.184.171/AGDLERP"
DEFAULT_USER = "mishu"
DEFAULT_PASS = "Mishu@722"

def parse_ms_date(d_str: Any) -> Optional[datetime.datetime]:
    if not d_str:
        return None
    m = re.search(r"\d{10,}", str(d_str))
    if m:
        try:
            return datetime.datetime.fromtimestamp(int(m.group(0)) / 1000)
        except Exception:
            return None
    return None

class ERPClient:
    def __init__(self, base_url: str = BASE_URL, username: str = DEFAULT_USER, password: str = DEFAULT_PASS):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.is_authenticated = False
        self._running_cache = {}

    def login(self) -> bool:
        """Authenticate with AGDL ERP system."""
        try:
            url = f"{self.base_url}/Login/CheckUser"
            payload = {"UserCode": self.username, "Password": self.password}
            headers = {"Content-Type": "application/json; charset=utf-8"}
            
            resp = self.session.post(url, data=json.dumps(payload), headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0 and data[0].get("UserName"):
                    self.is_authenticated = True
                    logger.info(f"ERP Login successful as {data[0].get('UserName')}")
                    return True
            logger.error(f"Login failed. Status: {resp.status_code}, Resp: {resp.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"ERP login error: {e}")
            return False

    def ensure_login(self) -> bool:
        if not self.is_authenticated:
            return self.login()
        return True

    def _request_json(self, method: str, url: str, timeout: int = 15, **kwargs) -> Any:
        """Executes HTTP request expecting JSON; re-authenticates once if ASP.NET session expired."""
        if not self.ensure_login():
            return None
        for attempt in range(2):
            try:
                if method.upper() == "POST":
                    resp = self.session.post(url, timeout=timeout, **kwargs)
                else:
                    resp = self.session.get(url, timeout=timeout, **kwargs)

                if resp.status_code == 200:
                    txt = resp.text.lstrip()
                    if txt.startswith("<"):
                        # ASP.NET redirected to HTML login page due to expired session
                        logger.warning(f"ERP session expired while fetching {url}; re-logging in...")
                        self.is_authenticated = False
                        if attempt == 0 and self.login():
                            continue
                        return None
                    return resp.json()
                elif resp.status_code in (401, 403) and attempt == 0:
                    self.is_authenticated = False
                    if self.login():
                        continue
            except Exception as e:
                logger.error(f"ERP request error ({url}, attempt {attempt+1}): {e}")
                if attempt == 0:
                    self.is_authenticated = False
                    self.login()
        return None

    def get_buyers(self) -> List[Dict[str, str]]:
        """Fetch all buyers from ERP."""
        url = f"{self.base_url}/MarchantModule/FinalCosting/LoadBuyer"
        buyers = self._request_json("GET", url, timeout=15)
        if not isinstance(buyers, list):
            return []
        result = []
        for b in buyers:
            code = b.get("Code")
            name = b.get("Value")
            if code and name and code != "-1":
                result.append({"code": code, "name": name})
        return result

    def get_running_bom_dict(self) -> Dict[str, str]:
        """Fetch all running styles across ERP BOM."""
        bom_url = f"{self.base_url}/Procurement/BOM/LoadBOMStyle"
        data = self._request_json("GET", bom_url, params={"keyword": "Running"}, timeout=15)
        if isinstance(data, list):
            self._running_cache = {item["Code"]: item.get("Value", "") for item in data}
            return self._running_cache
        return {}

    def get_style_capacity_schedule(self, ocb_id: str) -> Dict[str, Any]:
        """
        Extracts capacity booking schedule and PO data:
        1. oc_date: Style Confirmation / OC Date
        2. first_ffd: Earliest FFD among style POs
        3. last_ffd: Latest FFD among style POs
        4. first_tna_date: Fabric Inhouse Date of the 1st FFD PO
        5. is_pending: True if last FFD shipment date is pending (last FFD >= today AND total shipped < total ordered)
        """
        default_res = {
            "is_pending": False,
            "oc_date": None,
            "first_ffd": None,
            "last_ffd": None,
            "first_tna_date": None,
            "po_count": 0,
            "total_order_qty": 0,
            "total_ship_qty": 0
        }

        if not ocb_id:
            return default_res

        try:
            url = f"{self.base_url}/Report/GetCapacityData"
            raw = self._request_json("GET", url, params={"OCBID": ocb_id}, timeout=12)
            if not isinstance(raw, dict):
                return default_res

            d = raw.get("data", {})
            hdr = d.get("header", {})
            pos = d.get("poList", [])

            oc_date_dt = parse_ms_date(hdr.get("OCDate"))

            if not pos:
                return {
                    **default_res,
                    "oc_date": oc_date_dt.strftime("%d-%b-%Y") if oc_date_dt else None
                }

            now = datetime.datetime.now()
            po_records = []
            total_order = 0.0
            total_ship = 0.0

            for p in pos:
                ffd = parse_ms_date(p.get("FFD")) or parse_ms_date(p.get("Exfydate"))
                fab_ih = parse_ms_date(p.get("FabricInhouseDate"))
                o_qty = float(p.get("OrderQty") or 0)
                s_qty = float(p.get("ShipQty") or 0)
                total_order += o_qty
                total_ship += s_qty

                if ffd:
                    po_records.append({
                        "ffd": ffd,
                        "fab_ih": fab_ih,
                        "order_qty": o_qty,
                        "ship_qty": s_qty,
                        "status": p.get("OrderStatus") or ""
                    })

            if not po_records:
                return {
                    **default_res,
                    "oc_date": oc_date_dt.strftime("%d-%b-%Y") if oc_date_dt else None,
                    "po_count": len(pos)
                }

            # Sort POs chronologically by FFD
            po_records.sort(key=lambda x: x["ffd"])

            first_po = po_records[0]
            last_po = po_records[-1]

            first_ffd_dt = first_po["ffd"]
            last_ffd_dt = last_po["ffd"]
            first_fab_ih_dt = first_po["fab_ih"]

            # If full shipment done or last FFD shipment date passed, style is NOT running
            is_shipment_done = (total_order > 0 and total_ship >= total_order)
            is_date_passed = (last_ffd_dt < now)
            is_pending = (not is_shipment_done) and (not is_date_passed)

            return {
                "is_pending": is_pending,
                "oc_date": oc_date_dt.strftime("%d-%b-%Y") if oc_date_dt else "N/A",
                "first_ffd": first_ffd_dt.strftime("%d-%b-%Y") if first_ffd_dt else "N/A",
                "last_ffd": last_ffd_dt.strftime("%d-%b-%Y") if last_ffd_dt else "N/A",
                "first_tna_date": first_fab_ih_dt.strftime("%d-%b-%Y") if first_fab_ih_dt else "N/A",
                "po_count": len(pos),
                "total_order_qty": total_order,
                "total_ship_qty": total_ship
            }

        except Exception as e:
            logger.warning(f"Error checking Capacity schedule for {ocb_id}: {e}")

        return default_res

    def get_styles_for_buyer(self, buyer_code: str, running_only: bool = True) -> List[Dict[str, Any]]:
        """
        Retrieves styles for selected buyer.
        Enforces strict 'Running' criteria:
        1. Tagged Running in ERP BOM.
        2. From Capacity Booking: Last FFD date is in the future AND total shipment not complete.
        """
        if not self.ensure_login():
            return []
        try:
            running_dict = self.get_running_bom_dict()

            url = f"{self.base_url}/MarchantModule/FinalCosting/LoadStyle"
            headers = {"Content-Type": "application/json; charset=utf-8"}
            raw_styles = self._request_json("POST", url, data=json.dumps({"ContactID": buyer_code}), headers=headers, timeout=20)
            if not isinstance(raw_styles, list):
                logger.error(f"Failed to fetch styles for buyer {buyer_code}")
                return []

            results = []
            
            for st in raw_styles:
                val = st.get("Value", "")  # e.g. "08S23WS005 - B-22-2"
                ocb_id = st.get("Code", "")  # e.g. "OCB-21-12"
                
                parts = val.split(" - ")
                costing_id = parts[-1].strip() if len(parts) > 1 else ""
                style_name = " - ".join(parts[:-1]).strip() if len(parts) > 1 else val.strip()

                is_bom_running = costing_id in running_dict
                bom_val = running_dict.get(costing_id, "")
                garment_type = ""
                bom_style_name = ""

                if bom_val:
                    b_parts = [p.strip() for p in bom_val.split("=>")]
                    if len(b_parts) >= 4:
                        bom_style_name = b_parts[0]
                        garment_type = b_parts[2]

                if running_only:
                    if not is_bom_running:
                        continue
                    
                    # Verify Capacity Booking schedule: last FFD must be pending and shipment incomplete
                    sched = self.get_style_capacity_schedule(ocb_id)
                    if not sched["is_pending"]:
                        logger.info(f"Skipping style '{val}' - last FFD passed or full shipment done ({sched.get('last_ffd')})")
                        continue
                else:
                    sched = self.get_style_capacity_schedule(ocb_id)

                results.append({
                    "ocb_id": ocb_id,
                    "costing_id": costing_id,
                    "style_name": bom_style_name or style_name,
                    "display_value": val,
                    "status": "Running",
                    "garment_type": garment_type,
                    "oc_date": sched.get("oc_date"),
                    "first_ffd": sched.get("first_ffd"),
                    "last_ffd": sched.get("last_ffd"),
                    "first_tna_date": sched.get("first_tna_date")
                })

            return results
        except Exception as e:
            logger.error(f"Error in get_styles_for_buyer: {e}")
            return []

    def get_style_ocb_details(self, ocb_id: str) -> Optional[Dict[str, Any]]:
        """Fetch OCB details (OrderQty, CostingID, StyleName, FOB, etc.)"""
        url = f"{self.base_url}/MarchantModule/FinalCosting/LoadOCB"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        data = self._request_json("POST", url, data=json.dumps({"OCBID": ocb_id}), headers=headers, timeout=15)
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    def get_costing_items(self, costing_id: str) -> List[Dict[str, Any]]:
        """Fetch style-wise costing items list from Final Costing details."""
        url = f"{self.base_url}/MarchantModule/FinalCosting/LoadCostingDetails"
        data = self._request_json("GET", url, params={"CostingID": costing_id}, timeout=15)
        return data if isinstance(data, list) else []

    def get_bom_inhoused_status(self, costing_id: str) -> List[Dict[str, Any]]:
        """
        Check in-house status from ERP BOM:
        Returns items with BookedQty, RcvQty (Inhoused), and BalanceQty.
        """
        url = f"{self.base_url}/Procurement/BOM/GetCostingValueVsBookedValue"
        data = self._request_json("GET", url, params={"FinalCostingID": costing_id}, timeout=20)
        if not isinstance(data, list):
            return []
        results = []
        for itm in data:
            try:
                item_name = itm.get("ItemGroupName") or itm.get("Items") or ""
                booked = float(itm.get("BookedQty") or 0)
                rcv = float(itm.get("RcvQty") or 0) # Inhoused
                balance = booked - rcv if booked > 0 else 0
                results.append({
                    "item_name": str(item_name).strip(),
                    "uom": itm.get("UOM") or "",
                    "booked_qty": booked,
                    "ih_qty": rcv,
                    "bal_qty": balance,
                    "total_cost": float(itm.get("TOTALCOST") or 0),
                    "is_inhoused": (booked > 0 and balance <= 0)
                })
            except Exception as e:
                logger.warning(f"Skipping malformed BOM item in {costing_id}: {e}")
        return results
