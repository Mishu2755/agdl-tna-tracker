import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("TNAStorage")
DATA_FILE = Path(__file__).resolve().parent / "tna_data.json"

class TNAStorage:
    def __init__(self, filepath: Path = DATA_FILE):
        self.filepath = filepath
        self.lock = threading.Lock()
        self._last_mtime = 0.0
        self.data: Dict[str, Any] = {
            "selected_buyer": {"code": "C/20/1", "name": "Kmart"},
            "styles": {}, # key: style_id/costing_id
            "last_synced": None,
            "metadata": {}
        }
        self.load()

    def _reload_if_needed(self):
        """Checks if file on disk has changed and reloads to keep multi-user concurrent edits fresh."""
        try:
            if self.filepath.exists():
                mtime = self.filepath.stat().st_mtime
                if mtime > self._last_mtime:
                    self.load()
        except Exception as e:
            logger.debug(f"Error checking mtime: {e}")

    def load(self):
        with self.lock:
            if self.filepath.exists():
                try:
                    with open(self.filepath, "r", encoding="utf-8") as f:
                        self.data = json.load(f)
                    self._last_mtime = self.filepath.stat().st_mtime
                    logger.info(f"Loaded T&A data: {len(self.data.get('styles', {}))} styles.")
                except Exception as e:
                    logger.error(f"Error loading {self.filepath}: {e}")
            else:
                self.save()

    def save(self):
        with self.lock:
            try:
                temp_file = self.filepath.with_suffix(".tmp")
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2, ensure_ascii=False)
                temp_file.replace(self.filepath)
                self._last_mtime = self.filepath.stat().st_mtime
            except Exception as e:
                logger.error(f"Error saving to {self.filepath}: {e}")

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
