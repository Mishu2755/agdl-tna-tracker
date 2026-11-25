import os
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from task_engine import sort_tasks

try:
    import psycopg2
    from psycopg2.extras import Json
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

logger = logging.getLogger("TNAStorage")
DATA_FILE = Path(__file__).resolve().parent / "tna_data.json"

class TNAStorage:
    def __init__(self, filepath: Path = DATA_FILE):
        self.filepath = filepath
        self.db_url = os.environ.get("DATABASE_URL", "").strip()
        self.use_db = bool(self.db_url and HAS_PSYCOPG2)
        self.lock = threading.Lock()
        self._local = threading.local()
        self._last_mtime = 0.0
        self._last_db_updated_at = None
        self.data: Dict[str, Any] = {
            "selected_buyer": {"code": "C/20/1", "name": "Kmart"},
            "styles": {}, # key: style_id/costing_id
            "last_synced": None,
            "metadata": {}
        }
        if self.use_db:
            self._init_db()
        self.load()

    def _get_conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None and not conn.closed:
            return conn
        conn = psycopg2.connect(self.db_url, connect_timeout=15)
        self._local.conn = conn
        return conn

    def _reset_conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None

    def _run_db(self, fn):
        """Runs a DB callback with thread-local connection reuse and 1 auto-reconnect retry."""
        for attempt in range(2):
            conn = None
            try:
                conn = self._get_conn()
                res = fn(conn)
                conn.commit()
                return res
            except Exception as e:
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                self._reset_conn()
                if attempt == 0:
                    logger.debug(f"DB retry after transient error: {e}")
                    continue
                raise

    def _init_db(self):
        try:
            def _create(conn):
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS tna_store (
                            id TEXT PRIMARY KEY,
                            data JSONB NOT NULL,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
            self._run_db(_create)
            logger.info("Connected to PostgreSQL persistent database (tna_store ready).")
        except Exception as e:
            logger.error(f"PostgreSQL init failed, falling back to local JSON: {e}")
            self.use_db = False

    def _reload_if_needed(self):
        """Checks if file on disk or PostgreSQL row has changed and reloads to keep multi-user concurrent edits fresh."""
        if self.use_db:
            try:
                def _check(conn):
                    with conn.cursor() as cur:
                        cur.execute("SELECT updated_at FROM tna_store WHERE id = 'main'")
                        return cur.fetchone()
                row = self._run_db(_check)
                if row and row[0] != self._last_db_updated_at:
                    self.load()
            except Exception as e:
                logger.debug(f"DB mtime check error: {e}")
            return

        try:
            if self.filepath.exists():
                mtime = self.filepath.stat().st_mtime
                if mtime > self._last_mtime:
                    self.load()
        except Exception as e:
            logger.debug(f"Error checking mtime: {e}")

    def load(self):
        with self.lock:
            if self.use_db:
                try:
                    def _load_or_seed(conn):
                        with conn.cursor() as cur:
                            cur.execute("SELECT data, updated_at FROM tna_store WHERE id = 'main'")
                            row = cur.fetchone()
                            if row:
                                return ("loaded", row[0], row[1])
                            seed_data = self.data
                            if self.filepath.exists():
                                with open(self.filepath, "r", encoding="utf-8") as f:
                                    seed_data = json.load(f)
                                logger.info(f"Seeding PostgreSQL from local JSON ({len(seed_data.get('styles', {}))} styles)...")
                            cur.execute(
                                "INSERT INTO tna_store (id, data, updated_at) VALUES ('main', %s, CURRENT_TIMESTAMP) RETURNING updated_at",
                                (Json(seed_data),)
                            )
                            r2 = cur.fetchone()
                            return ("seeded", seed_data, r2[0] if r2 else None)

                    status, payload, ts = self._run_db(_load_or_seed)
                    self.data = payload if isinstance(payload, dict) else json.loads(payload)
                    self._last_db_updated_at = ts
                    if status == "loaded":
                        logger.info(f"Loaded T&A data from PostgreSQL: {len(self.data.get('styles', {}))} styles.")
                    return
                except Exception as e:
                    logger.error(f"Error loading from PostgreSQL: {e}")

            if self.filepath.exists():
                try:
                    with open(self.filepath, "r", encoding="utf-8") as f:
                        self.data = json.load(f)
                    self._last_mtime = self.filepath.stat().st_mtime
                    logger.info(f"Loaded T&A data: {len(self.data.get('styles', {}))} styles.")
                except Exception as e:
                    logger.error(f"Error loading {self.filepath}: {e}")
            else:
                self._save_unlocked()

    def _save_unlocked(self):
        if self.use_db:
            try:
                def _upsert(conn):
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO tna_store (id, data, updated_at)
                            VALUES ('main', %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (id) DO UPDATE
                            SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
                            RETURNING updated_at;
                            """,
                            (Json(self.data),)
                        )
                        return cur.fetchone()
                row = self._run_db(_upsert)
                if row:
                    self._last_db_updated_at = row[0]
            except Exception as e:
                logger.error(f"Error saving to PostgreSQL: {e}")

        try:
            temp_file = self.filepath.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.filepath)
            self._last_mtime = self.filepath.stat().st_mtime
        except Exception as e:
            logger.error(f"Error saving to {self.filepath}: {e}")

    def save(self):
        with self.lock:
            self._save_unlocked()

    def get_styles(self) -> Dict[str, Any]:
        self._reload_if_needed()
        return self.data.get("styles", {})

    def get_styles_by_buyer(self, buyer_code: Optional[str] = None) -> Dict[str, Any]:
        self._reload_if_needed()
        all_styles = self.get_styles()
        if not buyer_code or buyer_code == "ALL":
            return all_styles
        return {
            sid: s for sid, s in all_styles.items()
            if s.get("buyer_code") == buyer_code or (not s.get("buyer_code") and buyer_code == "C/20/1")
        }

    def get_style(self, costing_id: str) -> Optional[Dict[str, Any]]:
        self._reload_if_needed()
        return self.data.get("styles", {}).get(costing_id)

    def upsert_style(self, costing_id: str, style_info: Dict[str, Any]):
        self._reload_if_needed()
        if "styles" not in self.data:
            self.data["styles"] = {}
        
        if costing_id in self.data["styles"]:
            # Preserve existing tasks and user notes while updating metadata
            existing = self.data["styles"][costing_id]
            for k, v in style_info.items():
                if k != "tasks":
                    existing[k] = v
        else:
            self.data["styles"][costing_id] = style_info
        self.save()

    def upsert_styles_batch(self, style_entries: List[tuple]):
        """Batch inserts/updates multiple styles in a single atomic save."""
        if not style_entries:
            return
        self._reload_if_needed()
        if "styles" not in self.data:
            self.data["styles"] = {}
        for costing_id, style_info in style_entries:
            if costing_id in self.data["styles"]:
                existing = self.data["styles"][costing_id]
                for k, v in style_info.items():
                    if k != "tasks":
                        existing[k] = v
            else:
                self.data["styles"][costing_id] = style_info
        self.data["last_synced"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()

    def apply_bom_updates_batch(self, bom_results: Dict[str, List[Dict[str, Any]]], sort_fn) -> int:
        """Merges ERP BOM quantities across many styles into the latest DB state in a single save."""
        self._reload_if_needed()
        styles = self.data.get("styles", {})
        updated_items = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        for cid, bom_items in bom_results.items():
            if not bom_items or cid not in styles:
                continue
            s_info = styles[cid]
            bom_map = {str(b.get("item_name", "")).lower(): b for b in bom_items if b.get("item_name")}
            tasks = s_info.get("tasks", [])

            for t in tasks:
                if not t.get("is_costing"):
                    continue
                t_name = str(t.get("item_name", "")).lower()
                matched = bom_map.get(t_name)
                if not matched:
                    for b_name, b_val in bom_map.items():
                        if b_name in t_name or t_name in b_name:
                            matched = b_val
                            break

                if matched:
                    uom = matched.get("uom") or t.get("uom") or ""
                    t["booked_qty"] = matched["booked_qty"]
                    t["ih_qty"] = matched["ih_qty"]
                    t["bal_qty"] = matched["bal_qty"]
                    t["uom"] = uom

                    if matched["booked_qty"] > 0 and matched["bal_qty"] <= 0 and matched["ih_qty"] > 0:
                        t["status"] = "Closed"
                        t["updates"] = f"Fully Inhoused ({matched['ih_qty']:g} {uom})".strip()
                    elif matched["ih_qty"] > 0:
                        t["updates"] = f"{matched['booked_qty']:g} {uom} Booked, {matched['ih_qty']:g} {uom} Inhoused, Balance to i/h {matched['bal_qty']:g} {uom}"
                    t["last_modified"] = now_str
                    updated_items += 1

            s_info["tasks"] = sort_fn(tasks)

        self.data["last_synced"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()
        return updated_items

    def delete_style(self, costing_id: str):
        self._reload_if_needed()
        if costing_id in self.data.get("styles", {}):
            del self.data["styles"][costing_id]
            self.save()

    def get_tasks(self, costing_id: str) -> List[Dict[str, Any]]:
        self._reload_if_needed()
        style = self.get_style(costing_id)
        if style:
            return style.get("tasks", [])
        return []

    def update_task(self, costing_id: str, task_id: str, update_data: Dict[str, Any]):
        self._reload_if_needed()
        style = self.get_style(costing_id)
        if not style:
            return
        tasks = style.get("tasks", [])
        for t in tasks:
            if str(t.get("id")) == str(task_id):
                t.update(update_data)
                t["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                break
        self.save()

    def bulk_update_tasks(self, task_items: List[Dict[str, str]], update_dict: Dict[str, Any]) -> int:
        """Atomically updates multiple tasks across multiple styles in a single save."""
        self._reload_if_needed()
        count = 0
        styles = self.data.get("styles", {})
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        for item in task_items:
            sid = item.get("style_id")
            tid = item.get("task_id")
            if sid in styles:
                for t in styles[sid].get("tasks", []):
                    if str(t.get("id")) == str(tid):
                        t.update(update_dict)
                        t["last_modified"] = now_str
                        count += 1
                        break
        
        if count > 0:
            self.save()
        return count

    def add_custom_task(self, costing_id: str, task_data: Dict[str, Any]):
        self._reload_if_needed()
        style = self.get_style(costing_id)
        if not style:
            return
        if "tasks" not in style:
            style["tasks"] = []
        
        new_id = f"custom_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        task_data["id"] = new_id
        task_data["is_custom"] = True
        task_data["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        style["tasks"].append(task_data)
        style["tasks"] = sort_tasks(style["tasks"])
        self.save()

    def delete_task(self, costing_id: str, task_id: str):
        self._reload_if_needed()
        style = self.get_style(costing_id)
        if not style:
            return
        style["tasks"] = [t for t in style.get("tasks", []) if str(t.get("id")) != str(task_id)]
        self.save()

    def set_buyer(self, code: str, name: str):
        self._reload_if_needed()
        self.data["selected_buyer"] = {"code": code, "name": name}
        self.save()

    def get_buyer(self) -> Dict[str, str]:
        self._reload_if_needed()
        return self.data.get("selected_buyer", {"code": "C/20/1", "name": "Kmart"})

    def set_last_synced(self):
        self._reload_if_needed()
        self.data["last_synced"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()
