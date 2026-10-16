import json
import os
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
SEEN_FILE = os.path.join(BASE_DIR, "seen_accounts.json")
SEEN_IMAGES_FILE = os.path.join(BASE_DIR, "seen_images.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "channel_id": None,           # Discord channel ID where alerts will be sent
    "interval_minutes": 30,       # Frequency of checking in minutes (e.g. 30, 45, 60)
    "is_running": True,           # Whether automatic background monitoring is active
    "currency": "usd",            # Currency: usd, rub, eur
    "min_skins": 20,              # Minimum skin count (smin)
    "max_skins": 0,               # Maximum skin count (0 = no limit)
    "max_price": 50,              # Maximum price (pmax) in selected currency
    "min_price": 1,               # Minimum price (pmin) in selected currency
    "min_vbucks": 0,              # Minimum V-Bucks (vbmin)
    "psn_linkable": "nomatter",   # "yes", "no", "nomatter" (قابلية الربط بالسوني)
    "xbox_linkable": "nomatter",  # "yes", "no", "nomatter" (قابلية الربط بالإكس بوكس)
    "daybreak": 0,                # Minimum days of inactivity (أقل عدد أيام منذ آخر نشاط, 0 = no filter)
    "order_by": "price_to_up",    # price_to_up (cheapest first)
    "rare_keywords": [            # Rare skins to highlight in alerts
        "Travis Scott", "Renegade Raider", "Black Knight", "Ikonik",
        "Galaxy", "Wonder", "Wildcat", "OG Ghoul", "OG Skull",
        "Aerial Assault", "Scenario", "Minty", "Leviathan", "Floss",
        "Take The L", "Honor Guard", "Stealth Reflex", "Glow", "Neo Versa"
    ],
    "proof_channel_id": None,     # Channel ID where subscription proof screenshots are sent
    "proof_role_id": None,        # Role ID to assign when an image is sent in the proof channel
    "profit_amount": 10.0,        # Profit added to the original account price for resale
    "owner_id": None,             # Discord User ID of the owner to receive secret LZT buy links in DM (legacy)
    "dm_recipients": [],          # List of Discord User IDs to receive secret LZT buy links in DM
    "target_items": [],           # Specific custom skins/items to search for (e.g. ["Travis Scott", "Minty"])
    "filter_by_target": False,    # If True, strictly require one of target_items to be in the account (side option)
    "store_name": "VENTO",        # Branding / watermark store name used for generating showcase graphics
    "fixed_account_title": "🎮 Fortnite Special Account" # Static title for all account alert embeds
}

RECIPIENTS_FILE = os.path.join(BASE_DIR, "recipients.txt")

# Known username to Discord ID map for fast resolution
KNOWN_USERS: Dict[str, int] = {
    "0zvf": 407568388324589579,
    "0y5p": 1322676395893067859
}

def load_recipients_file() -> List[str]:
    """Load usernames or IDs from recipients.txt file."""
    if not os.path.exists(RECIPIENTS_FILE):
        default_content = (
            "# ====================================================================\n"
            "# قائمة مستلمي روابط الشراء في الخاص (Private DM Alert Recipients)\n"
            "# ====================================================================\n"
            "# اكتب اسم المستخدم (Username) أو الآيدي (User ID) هنا\n"
            "# كل اسم في سطر منفصل. يمكنك إضافة أو تعديل الأسماء في أي وقت:\n"
            "# ====================================================================\n\n"
            "0zvf\n"
            "0y5p\n"
        )
        try:
            with open(RECIPIENTS_FILE, "w", encoding="utf-8") as f:
                f.write(default_content)
        except Exception:
            pass
        return ["0zvf", "0y5p"]

    entries: List[str] = []
    try:
        with open(RECIPIENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                clean = line.strip()
                if clean and not clean.startswith("#"):
                    entries.append(clean)
    except Exception as e:
        print(f"[Config] Error reading recipients.txt: {e}")
    return entries

def save_recipients_file(entries: List[str]) -> None:
    """Save usernames or IDs to recipients.txt file."""
    try:
        header = (
            "# ====================================================================\n"
            "# قائمة مستلمي روابط الشراء في الخاص (Private DM Alert Recipients)\n"
            "# ====================================================================\n"
            "# اكتب اسم المستخدم (Username) أو الآيدي (User ID) هنا\n"
            "# كل اسم في سطر منفصل. يمكنك إضافة أو تعديل الأسماء في أي وقت:\n"
            "# ====================================================================\n\n"
        )
        content = header + "\n".join(entries) + "\n"
        with open(RECIPIENTS_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"[Config] Error saving recipients.txt: {e}")

def get_dm_recipients(config: Dict[str, Any], bot: Any = None) -> List[int]:
    """
    Retrieve all user IDs configured to receive private DMs.
    Prioritizes recipients.txt, resolving usernames to IDs.
    """
    file_entries = load_recipients_file()
    recipients: List[int] = []

    for entry in file_entries:
        # 1. Direct numeric ID
        try:
            val = int(entry)
            if val not in recipients:
                recipients.append(val)
            continue
        except ValueError:
            pass

        # 2. Known username map
        lower_name = entry.lower()
        if lower_name in KNOWN_USERS:
            uid = KNOWN_USERS[lower_name]
            if uid not in recipients:
                recipients.append(uid)
            continue

        # 3. Dynamic resolution via discord bot instance if available
        if bot:
            resolved = False
            for user in getattr(bot, "users", []):
                if user.name.lower() == lower_name or (getattr(user, "global_name", None) and user.global_name.lower() == lower_name):
                    if user.id not in recipients:
                        recipients.append(user.id)
                    KNOWN_USERS[lower_name] = user.id
                    resolved = True
                    break
            if not resolved and hasattr(bot, "guilds"):
                for guild in bot.guilds:
                    for member in guild.members:
                        if member.name.lower() == lower_name or (member.global_name and member.global_name.lower() == lower_name):
                            if member.id not in recipients:
                                recipients.append(member.id)
                            KNOWN_USERS[lower_name] = member.id
                            resolved = True
                            break
                    if resolved:
                        break

    # Fallback if recipients.txt is empty
    if not recipients:
        raw = config.get("dm_recipients", [])
        if isinstance(raw, list):
            for uid in raw:
                try:
                    val = int(uid)
                    if val not in recipients:
                        recipients.append(val)
                except (ValueError, TypeError):
                    pass
        legacy = config.get("owner_id")
        if legacy:
            try:
                val = int(legacy)
                if val not in recipients:
                    recipients.append(val)
            except (ValueError, TypeError):
                pass

    return recipients


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json or create with defaults."""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure all default keys exist
            for key, val in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = val
            if os.getenv("CHANNEL_ID"):
                try:
                    data["channel_id"] = int(os.getenv("CHANNEL_ID"))
                except Exception:
                    pass
            return data
    except Exception as e:
        print(f"[Config] Error loading config, using defaults: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Config] Error saving config: {e}")

def load_seen_accounts() -> List[int]:
    """Load list of previously seen account IDs."""
    if not os.path.exists(SEEN_FILE):
        return []
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_seen_accounts(seen_ids: List[int]) -> None:
    """Save seen account IDs (keeps up to 1000 items)."""
    try:
        # Keep only latest 1000 IDs to save disk and memory
        truncated = seen_ids[-1000:]
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(truncated, f, indent=2)
    except Exception as e:
        print(f"[Config] Error saving seen accounts: {e}")

def load_seen_images() -> List[Dict[str, Any]]:
    """Load previously seen proof image hashes."""
    if not os.path.exists(SEEN_IMAGES_FILE):
        return []
    try:
        with open(SEEN_IMAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_seen_images(seen_images: List[Dict[str, Any]]) -> None:
    """Save seen proof image hashes (keeps up to 2000 images)."""
    try:
        truncated = seen_images[-2000:]
        with open(SEEN_IMAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(truncated, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Config] Error saving seen images: {e}")

