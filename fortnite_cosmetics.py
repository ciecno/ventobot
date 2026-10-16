import json
import os
import urllib.request
from typing import List, Dict, Optional

COSMETICS_FILE = os.path.join(os.path.dirname(__file__), "fortnite_cosmetics.json")

class FortniteCosmetics:
    _items: List[Dict[str, str]] = []
    _loaded: bool = False

    @classmethod
    def load(cls):
        """Load cosmetics from local JSON cache if not already loaded."""
        if cls._loaded and cls._items:
            return
        if not os.path.exists(COSMETICS_FILE):
            cls.refresh_cache()
        else:
            try:
                with open(COSMETICS_FILE, "r", encoding="utf-8") as f:
                    cls._items = json.load(f)
                cls._loaded = True
            except Exception:
                cls.refresh_cache()

    @classmethod
    def refresh_cache(cls) -> bool:
        """Fetch full cosmetics database from fortnite-api.com and save locally."""
        try:
            req = urllib.request.Request(
                "https://fortnite-api.com/v2/cosmetics/br",
                headers={"User-Agent": "FortniteBot/1.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8")).get("data", [])

            items = []
            seen = set()
            for item in data:
                t = item.get("type", {}).get("value")
                name = item.get("name", "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                if t == "outfit":
                    items.append({"name": name, "type": "skin", "label": f"👕 {name} (Skin)"})
                elif t == "pickaxe":
                    items.append({"name": name, "type": "pickaxe", "label": f"⛏️ {name} (Pickaxe)"})
                elif t == "emote":
                    items.append({"name": name, "type": "dance", "label": f"💃 {name} (Dance/Emote)"})

            with open(COSMETICS_FILE, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False)
            cls._items = items
            cls._loaded = True
            return True
        except Exception as e:
            print(f"[COSMETICS] Cache update error: {e}")
            return False

    @classmethod
    def search(cls, query: str, category: Optional[str] = None, limit: int = 25) -> List[Dict[str, str]]:
        """
        Fast autocomplete search for cosmetics.
        Prioritizes:
        1. Exact matches
        2. Prefix matches (starts with query)
        3. Word-starts matches (e.g. 'scott' in 'Travis Scott')
        4. Substring matches
        """
        cls.load()
        q = query.lower().strip()
        if not q:
            filtered = cls._items if not category else [i for i in cls._items if i["type"] == category]
            return filtered[:limit]

        exact_matches = []
        prefix_matches = []
        word_matches = []
        substr_matches = []

        for item in cls._items:
            if category and item["type"] != category:
                continue
            name_lower = item["name"].lower()
            if name_lower == q:
                exact_matches.append(item)
            elif name_lower.startswith(q):
                prefix_matches.append(item)
            elif any(w.startswith(q) for w in name_lower.split()):
                word_matches.append(item)
            elif q in name_lower:
                substr_matches.append(item)

        results = exact_matches + prefix_matches + word_matches + substr_matches
        
        # Deduplicate while preserving order
        deduped = []
        seen = set()
        for r in results:
            if r["name"] not in seen:
                seen.add(r["name"])
                deduped.append(r)
                if len(deduped) >= limit:
                    break

        return deduped
