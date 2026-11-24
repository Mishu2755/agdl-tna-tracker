import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("TNAStorage")
DATA_FILE = Path(__file__).resolve().parent / "tna_data.json"

class TNAStorage:
    def __init__(self, filepath: Path = DATA_FILE):
        self.filepath = filepath
        self.data: Dict[str, Any] = {
            "selected_buyer": {"code": "C/20/1", "name": "Kmart"},
            "styles": {}, # key: style_id/costing_id
            "last_synced": None,
            "metadata": {}
        }
        self.load()

    def load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                logger.info(f"Loaded T&A data: {len(self.data.get('styles', {}))} styles.")
            except Exception as e:
                logger.error(f"Error loading {self.filepath}: {e}")
        else:
            self.save()

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving to {self.filepath}: {e}")

    def get_styles(self) -> Dict[str, Any]:
        return self.data.get("styles", {})

    def get_style(self, costing_id: str) -> Optional[Dict[str, Any]]:
        return self.data.get("styles", {}).get(costing_id)

    def upsert_style(self, costing_id: str, style_info: Dict[str, Any]):
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
        if costing_id in self.data.get("styles", {}):
            del self.data["styles"][costing_id]
            self.save()

    def get_tasks(self, costing_id: str) -> List[Dict[str, Any]]:
        style = self.get_style(costing_id)
        if style:
            return style.get("tasks", [])
        return []

    def update_task(self, costing_id: str, task_id: str, update_data: Dict[str, Any]):
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

    def add_custom_task(self, costing_id: str, task_data: Dict[str, Any]):
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
        style = self.get_style(costing_id)
        if not style:
            return
        style["tasks"] = [t for t in style.get("tasks", []) if str(t.get("id")) != str(task_id)]
        self.save()

    def set_buyer(self, code: str, name: str):
        self.data["selected_buyer"] = {"code": code, "name": name}
        self.save()

    def get_buyer(self) -> Dict[str, str]:
        return self.data.get("selected_buyer", {"code": "C/20/1", "name": "Kmart"})

    def set_last_synced(self):
        self.data["last_synced"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.save()
