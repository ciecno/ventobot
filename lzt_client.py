import aiohttp
import re
import asyncio
import base64
import datetime
from typing import Dict, Any, List, Optional, Tuple

LZT_BASE_URL = "https://api.lzt.market"
LZT_FALLBACK_URL = "https://prod-api.lzt.market"

class LZTClient:
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token.strip() if api_token else ""

    def set_token(self, api_token: str):
        self.api_token = api_token.strip()

    def get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def get_fortnite_accounts(
        self,
        min_price: float = 1,
        max_price: float = 50,
        min_skins: int = 20,
        max_skins: int = 0,
        min_vbucks: int = 0,
        psn_linkable: str = "nomatter",
        xbox_linkable: str = "nomatter",
        currency: str = "usd",
        order_by: str = "price_to_up",
        page: int = 1,
        daybreak: int = 0,
        title: Optional[str] = None
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Search Fortnite accounts on LZT Market.
        Returns: (items_list, error_message)
        """
        if not self.api_token:
            return None, "Supplier API key is not configured! Please add it in .env or use the /set_token command."

        params: Dict[str, Any] = {
            "pmin": min_price,
            "pmax": max_price,
            "currency": currency,
            "order_by": order_by,
            "page": page
        }

        if min_skins > 0:
            params["smin"] = min_skins
        if max_skins > 0:
            params["smax"] = max_skins
        if min_vbucks > 0:
            params["vbmin"] = min_vbucks
        if psn_linkable in ["yes", "no"]:
            params["psn_linkable"] = psn_linkable
        if xbox_linkable in ["yes", "no"]:
            params["xbox_linkable"] = xbox_linkable
        if daybreak > 0:
            params["daybreak"] = daybreak
        if title and str(title).strip():
            params["title"] = str(title).strip()

        url = f"{LZT_BASE_URL}/epicgames"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.get_headers(), params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 401:
                        return None, "Error 401: Supplier API token is invalid or expired. Please update the supplier token."
                    if resp.status == 429:
                        return None, "Error 429: Supplier rate limit reached temporarily. Please wait a moment."
                    if resp.status != 200:
                        txt = await resp.text()
                        return None, f"Supplier server error ({resp.status}): {txt[:200]}"
                    
                    data = await resp.json()
                    items = data.get("items", [])
                    return items, None

        except asyncio.TimeoutError:
            return None, "Supplier server connection timed out. Please try again."
        except Exception as e:
            return None, f"Error while connecting to supplier: {str(e)}"

    async def get_item_image(
        self,
        item_id: int,
        image_type: str = "skins",
        session: Optional[aiohttp.ClientSession] = None,
        timeout_seconds: int = 15
    ) -> Optional[bytes]:
        """
        Fetch item image (skins, pickaxes, dances) as raw bytes from supplier API.
        """
        if not self.api_token:
            return None

        url = f"{LZT_BASE_URL}/{item_id}/image"
        params = {"type": image_type}

        async def _do_fetch(sess: aiohttp.ClientSession) -> Optional[bytes]:
            try:
                async with sess.get(
                    url,
                    headers=self.get_headers(),
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds, sock_read=timeout_seconds - 2)
                ) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "").lower()
                        if "image/" in content_type:
                            raw = await resp.read()
                            if len(raw) > 100:
                                return raw
                        try:
                            data = await resp.json(content_type=None)
                            if isinstance(data, dict):
                                b64_str = data.get("base64") or data.get("image")
                                if b64_str:
                                    if "," in b64_str:
                                        b64_str = b64_str.split(",", 1)[1]
                                    return base64.b64decode(b64_str.strip())
                        except Exception:
                            raw = await resp.read()
                            if raw and len(raw) > 100 and not raw.startswith(b"{"):
                                return raw
            except Exception:
                pass
            return None

        if session:
            return await _do_fetch(session)
        else:
            async with aiohttp.ClientSession() as new_sess:
                return await _do_fetch(new_sess)

    async def get_all_item_images(self, item_id: int, item_dict: Optional[Dict[str, Any]] = None) -> Dict[str, bytes]:
        """
        Fetch all locker images (skins, pickaxes, dances) using fast direct signed CDN links
        from item data, falling back to API endpoints if necessary.
        """
        results: Dict[str, bytes] = {}
        if not self.api_token:
            return results

        # 1. Fast direct signed CDN links (imagePreviewLinks.direct)
        direct_links = {}
        if item_dict and isinstance(item_dict.get("imagePreviewLinks"), dict):
            direct_links = item_dict["imagePreviewLinks"].get("direct", {})

        if direct_links:
            async with aiohttp.ClientSession(headers=self.get_headers()) as session:
                async def fetch_direct(t: str, url: str):
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                            if resp.status == 200:
                                raw = await resp.read()
                                if len(raw) > 100:
                                    return t, raw
                    except Exception:
                        pass
                    return t, None

                target_types = ["skins", "pickaxes", "dances"]
                tasks = [fetch_direct(t, direct_links[t]) for t in target_types if t in direct_links]
                if tasks:
                    responses = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in responses:
                        if isinstance(res, tuple) and res[1]:
                            results[res[0]] = res[1]

            if results:
                return results

        # 2. Fallback to API endpoints
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.get_item_image(item_id, "skins", session=session, timeout_seconds=25),
                self.get_item_image(item_id, "pickaxes", session=session, timeout_seconds=20),
                self.get_item_image(item_id, "dances", session=session, timeout_seconds=20)
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            types = ["skins", "pickaxes", "dances"]
            for t_name, res in zip(types, responses):
                if isinstance(res, bytes) and len(res) > 0:
                    results[t_name] = res

        return results

    @staticmethod
    def extract_skin_count(item: Dict[str, Any]) -> int:
        """
        Extract skin count from item attributes or from title.
        """
        # Try direct attributes if provided by API
        if "epicgames_fortnite_skin_count" in item and item["epicgames_fortnite_skin_count"]:
            try:
                return int(item["epicgames_fortnite_skin_count"])
            except (ValueError, TypeError):
                pass

        if "fortnite_skin_count" in item and item["fortnite_skin_count"]:
            try:
                return int(item["fortnite_skin_count"])
            except (ValueError, TypeError):
                pass
        
        if "skin_count" in item and item["skin_count"]:
            try:
                return int(item["skin_count"])
            except (ValueError, TypeError):
                pass

        # Try parsing from title (e.g. "150 skins", "80 skin", "120 скинов", "150+ skins")
        title = item.get("title", "")
        match = re.search(r'(\d+)\+?\s*(?:skins?|скин|скинов|سكن)', title, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass

        return 0

    @staticmethod
    def detect_rare_skins(title: str, rare_keywords: List[str]) -> List[str]:
        """Detect rare skins mentioned in title or description."""
        found = []
        lower_title = title.lower()
        for kw in rare_keywords:
            if kw.lower() in lower_title:
                found.append(kw)
        return found

    @staticmethod
    def detect_target_items(item: Dict[str, Any], target_items: List[str]) -> List[str]:
        """
        Detect user-specified target items (skins, pickaxes, emotes/dances) in an account's
        locker items (fortniteSkins, fortnitePickaxe, fortniteDance, fortniteGliders), title, or description.
        """
        if not target_items:
            return []
        
        found = []
        search_corpus = f"{item.get('title', '')} {item.get('description', '')}".lower()
        
        extra_info = []
        # Extract cosmetic items from account locker
        for locker_key in ["fortniteSkins", "fortnitePickaxe", "fortniteDance", "fortniteGliders"]:
            locker_list = item.get(locker_key)
            if isinstance(locker_list, list):
                for obj in locker_list:
                    if isinstance(obj, dict):
                        t_val = obj.get("title") or obj.get("name")
                        if t_val:
                            extra_info.append(str(t_val).lower())
                    elif isinstance(obj, str):
                        extra_info.append(obj.lower())

        if isinstance(item.get("fortnite_skins"), list):
            extra_info.extend([str(s).lower() for s in item.get("fortnite_skins")])
        if isinstance(item.get("item_attributes"), list):
            extra_info.extend([str(a).lower() for a in item.get("item_attributes")])
            
        full_text = search_corpus + " " + " ".join(extra_info)

        for target in target_items:
            clean_target = target.strip()
            if not clean_target:
                continue
            c_low = clean_target.lower()
            if c_low in full_text or any(c_low in item_name for item_name in extra_info):
                found.append(clean_target)
        return found

    @staticmethod
    def calculate_deal_score(
        item: Dict[str, Any],
        rare_keywords: List[str],
        target_items: Optional[List[str]] = None
    ) -> float:
        """
        Calculate Deal Score (Value for Money):
        Score based on:
        - Ratio of skins per dollar (or ruble)
        - Bonus for rare skins
        - Bonus for custom target items
        """
        price = float(item.get("price", 0))
        if price <= 0:
            price = 1.0  # avoid division by zero
        
        skin_count = LZTClient.extract_skin_count(item)
        rare_skins = LZTClient.detect_rare_skins(item.get("title", ""), rare_keywords)
        matched_targets = LZTClient.detect_target_items(item, target_items or [])
        
        # Base score: skins per currency unit
        base_score = (skin_count / price) * 10.0
        
        # Rare skin bonus: each rare skin adds significant value weight
        rare_bonus = len(rare_skins) * 15.0
        
        # Target items bonus: gives highest priority to user-requested items
        target_bonus = len(matched_targets) * 30.0
        if target_items and len(matched_targets) == len(target_items):
            target_bonus += 100.0  # Huge bonus for accounts matching ALL requested items!
        
        total_score = round(base_score + rare_bonus + target_bonus, 2)
        return total_score

    @staticmethod
    def extract_full_account_details(item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract all 14 requested Fortnite account attributes from LZT Market:
        1. STW edition
        2. Balance
        3. Social accounts
        4. Changeable email
        5. Last activity
        6. Account level
        7. V-Bucks
        8. Friends
        9. Register date
        10. Platform
        11. XBOX linkable
        12. PSN linkable
        13. Country
        14. Email domain
        """
        title = item.get("title", "")
        desc = item.get("description", "")
        full_text = f"{title} {desc}".lower()

        # Helper: format timestamp or relative date
        def format_timestamp(val: Any) -> str:
            if not val:
                return "Unknown"
            try:
                ts = float(val)
                if ts > 1e11:
                    ts /= 1000.0
                dt = datetime.datetime.fromtimestamp(ts)
                now = datetime.datetime.now()
                date_str = dt.strftime("%Y-%m-%d")

                if dt > now:
                    future_days = (dt - now).days
                    if future_days == 0:
                        return f"Later Today ({date_str})"
                    elif future_days == 1:
                        return f"Tomorrow ({date_str})"
                    elif future_days < 30:
                        return f"in {future_days} days ({date_str})"
                    elif future_days < 365:
                        return f"in {max(1, future_days // 30)} months ({date_str})"
                    else:
                        return f"in {max(1, future_days // 365)} years ({date_str})"

                # Past dates
                delta = now - dt
                days = delta.days
                if days == 0:
                    return f"Today ({date_str})"
                elif days == 1:
                    return f"Yesterday ({date_str})"
                elif days < 30:
                    return f"{days} days ago ({date_str})"
                elif days < 365:
                    return f"{days // 30} months ago ({date_str})"
                else:
                    return f"{days // 365} years ago ({date_str})"
            except Exception:
                return str(val)

        # 1. STW Edition (Save The World)
        stw_raw = (
            item.get("epicgames_fortnite_stw_edition")
            or item.get("stwEdition")
            or item.get("fortnite_pve_edition")
            or item.get("pve_edition")
            or item.get("stw_edition")
            or item.get("fortnite_stw")
            or item.get("fortnite_pve")
            or item.get("pve")
        )
        stw_edition = "Not Available ❌"
        if stw_raw:
            if isinstance(stw_raw, str) and stw_raw.lower() not in ["none", "no", "false", "0", "null"]:
                stw_edition = f"{stw_raw} ✅"
            elif stw_raw is True or stw_raw == 1 or str(stw_raw).lower() in ["true", "yes", "1"]:
                stw_edition = "Available (Save The World) ✅"
        if stw_edition == "Not Available ❌":
            if "ultimate" in full_text and ("stw" in full_text or "save the world" in full_text or "pve" in full_text):
                stw_edition = "Ultimate Edition 💎"
            elif "limited" in full_text and ("stw" in full_text or "save the world" in full_text or "pve" in full_text):
                stw_edition = "Limited Edition ⭐"
            elif "super deluxe" in full_text:
                stw_edition = "Super Deluxe Edition ✨"
            elif "deluxe" in full_text and ("stw" in full_text or "save the world" in full_text or "pve" in full_text):
                stw_edition = "Deluxe Edition ✅"
            elif "founder" in full_text:
                stw_edition = "Founder Edition 💎"
            elif "stw" in full_text or "save the world" in full_text or "pve" in full_text:
                stw_edition = "Available (STW) ✅"

        # 2. Balance
        balance_raw = (
            item.get("epicgames_balance")
            or item.get("balance")
            or item.get("epic_balance")
            or item.get("wallet_balance")
        )
        if balance_raw is not None and str(balance_raw).strip() != "":
            try:
                b_val = float(balance_raw)
                balance = f"{b_val:,.2f}$"
            except (ValueError, TypeError):
                balance = str(balance_raw)
        else:
            balance = "0.00$"

        # 3. Social Accounts
        social_raw = (
            item.get("fortniteLinkedAccountsString")
            or item.get("egLinkedAccountsString")
            or item.get("epicgames_external_accounts")
            or item.get("social_accounts")
            or item.get("connected_accounts")
            or item.get("linked_accounts")
            or item.get("external_accounts")
            or item.get("social")
        )
        if isinstance(social_raw, list) and social_raw:
            extracted_names = []
            for s in social_raw:
                if isinstance(s, dict):
                    name = s.get("type") or s.get("name") or s.get("service") or s.get("platform") or str(s)
                    extracted_names.append(str(name))
                else:
                    extracted_names.append(str(s))
            social_accounts = ", ".join(extracted_names)
        elif isinstance(social_raw, dict) and social_raw:
            social_accounts = ", ".join([f"{k}: {v}" for k, v in social_raw.items() if v])
        elif isinstance(social_raw, str) and social_raw.strip():
            social_accounts = social_raw.strip()
        else:
            social_accounts = "None (No external accounts)"

        # 4. Changeable Email
        can_change = item.get("epicgames_change_email") or item.get("can_change_email") or item.get("canChangeEmail") or item.get("email_can_change")
        email_date = item.get("epicgames_next_change_email_date") or item.get("email_change_date") or item.get("emailChangeDate") or item.get("email_date")
        if can_change is True or str(can_change).lower() in ["true", "yes", "1"]:
            changeable_email = "Immediately Changeable ✅"
        elif email_date:
            changeable_email = f"Changeable on {format_timestamp(email_date)} ⏳"
        elif can_change is False or str(can_change).lower() in ["false", "no", "0"]:
            changeable_email = "Not Changeable Currently ❌"
        else:
            em_type = item.get("email_type", "")
            if em_type == "native":
                changeable_email = "Native Email Included ✅"
            else:
                changeable_email = "Pending Epic Games cooldown ⏳"

        # 5. Last Activity
        last_act_raw = (
            item.get("account_last_activity")
            or item.get("epicgames_last_activity")
            or item.get("fortnite_last_activity")
            or item.get("last_activity")
            or item.get("last_activity_date")
            or item.get("last_seen")
            or item.get("pdate")
        )
        last_activity = format_timestamp(last_act_raw) if last_act_raw else "Unknown"

        # 6. Account Level
        level_raw = (
            item.get("epicgames_fortnite_level")
            or item.get("fortnite_account_level")
            or item.get("account_level")
            or item.get("fortnite_level")
            or item.get("level")
        )
        if level_raw:
            try:
                account_level = f"Level {int(level_raw)}"
            except (ValueError, TypeError):
                account_level = f"Level {level_raw}"
        else:
            lvl_match = re.search(r'(?:level|lvl)\s*[:#]?\s*(\d+)', full_text)
            account_level = f"Level {lvl_match.group(1)}" if lvl_match else "Unknown"

        # 7. V-Bucks
        vbucks_raw = (
            item.get("epicgames_fortnite_balance")
            or item.get("fortnite_vbucks")
            or item.get("vbucks")
            or item.get("vb")
            or item.get("epic_vbucks")
        )
        if vbucks_raw is not None and str(vbucks_raw).strip() != "":
            try:
                vb_int = int(vbucks_raw)
                vbucks = f"{vb_int:,} V-Bucks"
            except (ValueError, TypeError):
                vbucks = f"{vbucks_raw} V-Bucks"
        else:
            vb_match = re.search(r'(\d+)\s*(?:v-?bucks|vb)', full_text)
            vbucks = f"{int(vb_match.group(1)):,} V-Bucks" if vb_match else "0 V-Bucks"

        # 8. Friends
        friends_raw = (
            item.get("epicgames_fortnite_friends_count")
            or item.get("fortnite_friends")
            or item.get("friends")
            or item.get("friends_count")
        )
        if friends_raw is not None and str(friends_raw).strip() != "":
            try:
                friends = f"{int(friends_raw)} Friends"
            except (ValueError, TypeError):
                friends = f"{friends_raw} Friends"
        else:
            f_match = re.search(r'(\d+)\s*friends', full_text)
            friends = f"{f_match.group(1)} Friends" if f_match else "0 Friends"

        # 9. Register Date
        reg_raw = (
            item.get("epicgames_fortnite_register_date")
            or item.get("register_date")
            or item.get("registration_date")
            or item.get("account_creation_date")
            or item.get("creation_date")
        )
        register_date = format_timestamp(reg_raw) if reg_raw else "Unknown"

        # 10. Platform
        plat_raw = (
            item.get("epicgames_fortnite_platform")
            or item.get("fortnite_platforms")
            or item.get("platforms")
            or item.get("platform")
            or item.get("devices")
        )
        if isinstance(plat_raw, list) and plat_raw:
            platform = ", ".join([str(p).upper() for p in plat_raw])
        elif isinstance(plat_raw, str) and plat_raw.strip():
            platform = plat_raw.strip().upper()
        else:
            platform = "PC / All Platforms"

        # 11. XBOX Linkable & 12. PSN Linkable
        # Rule: If PSN / Xbox is in Linked Accounts, it cannot be newly linked -> "no".
        # If not present in Linked Accounts -> "yes".
        social_search_str = ""
        if social_accounts and social_accounts != "None (No external accounts)":
            social_search_str += " " + social_accounts.lower()
        if social_raw:
            social_search_str += " " + str(social_raw).lower()

        # Check Xbox
        has_xbox_linked = bool(re.search(r'\b(xbox|xbl|microsoft)\b', social_search_str, re.IGNORECASE))
        xbox_raw = (
            item.get("epicgames_fortnite_xbox_linkable")
            or item.get("xbox_linkable")
            or item.get("canLinkToXbox")
            or item.get("can_link_xbox")
        )
        if has_xbox_linked or str(xbox_raw).lower() in ["no", "false", "0"]:
            xbox_linkable = "no"
        else:
            xbox_linkable = "yes"

        # Check PSN
        has_psn_linked = bool(re.search(r'\b(psn|playstation|sony)\b', social_search_str, re.IGNORECASE))
        psn_raw = (
            item.get("epicgames_fortnite_psn_linkable")
            or item.get("psn_linkable")
            or item.get("canLinkToPsn")
            or item.get("can_link_psn")
        )
        if has_psn_linked or str(psn_raw).lower() in ["no", "false", "0"]:
            psn_linkable = "no"
        else:
            psn_linkable = "yes"

        # 13. Country
        country_raw = (
            item.get("epicgames_country")
            or item.get("country")
            or item.get("account_country")
            or item.get("geo")
            or item.get("country_code")
        )
        country_map = {
            "us": "United States 🇺🇸", "ru": "Russia 🇷🇺", "sa": "Saudi Arabia 🇸🇦",
            "ae": "UAE 🇦🇪", "tr": "Turkey 🇹🇷", "de": "Germany 🇩🇪",
            "gb": "United Kingdom 🇬🇧", "uk": "United Kingdom 🇬🇧", "fr": "France 🇫🇷",
            "br": "Brazil 🇧🇷", "eg": "Egypt 🇪🇬", "kw": "Kuwait 🇰🇼",
            "qa": "Qatar 🇶🇦", "ca": "Canada 🇨🇦", "es": "Spain 🇪🇸",
            "it": "Italy 🇮🇹", "pl": "Poland 🇵🇱", "ua": "Ukraine 🇺🇦",
            "nl": "Netherlands 🇳🇱", "se": "Sweden 🇸🇪", "ch": "Switzerland 🇨🇭"
        }
        if country_raw and str(country_raw).lower() in country_map:
            country = country_map[str(country_raw).lower()]
        elif country_raw:
            country = f"{str(country_raw).upper()} 🌐"
        else:
            country = "Unknown 🌐"

        # 14. Email Domain
        domain_raw = (
            item.get("email_domain")
            or item.get("email_provider")
            or item.get("email_provider_name")
        )
        if domain_raw:
            email_domain = f"@{str(domain_raw).lstrip('@')}"
        elif item.get("email") and "@" in str(item.get("email")):
            email_domain = f"@{str(item.get('email')).split('@')[-1]}"
        else:
            em_match = re.search(r'@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', full_text)
            email_domain = f"@{em_match.group(1)}" if em_match else "Unknown"

        return {
            "stw_edition": stw_edition,
            "balance": balance,
            "social_accounts": social_accounts,
            "changeable_email": changeable_email,
            "last_activity": last_activity,
            "account_level": account_level,
            "vbucks": vbucks,
            "friends": friends,
            "register_date": register_date,
            "platform": platform,
            "xbox_linkable": xbox_linkable,
            "psn_linkable": psn_linkable,
            "country": country,
            "email_domain": email_domain
        }
