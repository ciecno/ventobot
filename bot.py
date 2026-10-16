import os
import sys
import io
import gc
import asyncio
import datetime
from typing import Optional, List, Dict, Any

# Ensure UTF-8 output on Windows terminal with line-buffering
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    elif hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    elif hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

from config_manager import (
    load_config,
    save_config,
    load_seen_accounts,
    save_seen_accounts,
    load_seen_images,
    save_seen_images,
    get_dm_recipients,
    load_recipients_file,
    save_recipients_file
)
from lzt_client import LZTClient
from image_verifier import calculate_image_hashes, check_if_duplicate
from fortnite_cosmetics import FortniteCosmetics

# Load environment variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_FILE)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
LZT_API_TOKEN = os.getenv("LZT_API_TOKEN", "")

# Initialize Intents & Bot with low-memory profile for 256MB free hosts
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    max_messages=50,
    chunk_guilds_at_startup=False
)
lzt_client = LZTClient(api_token=LZT_API_TOKEN)
config = load_config()

# Known bot owner IDs for 0-latency instant authorization
OWNER_IDS = {407568388324589579, 1322676395893067859}

def is_bot_owner(user_id: int) -> bool:
    """Instant check if a Discord user ID is in the authorized bot owners list."""
    try:
        uid = int(user_id)
        if uid in OWNER_IDS:
            return True
        recipients = get_dm_recipients(config)
        return uid in recipients
    except Exception:
        return False

# Helper function to format timestamp
def get_current_time_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

def create_locker_collage(
    images_dict: Dict[str, bytes],
    store_name: str = "VENTO",
    skin_count: Optional[int] = None
) -> Optional[bytes]:
    """
    Transform raw supplier locker images into a custom-designed, branded
    showcase graphic so nobody can identify the original source.
    Features:
    - Glowing purple/cyan accent line
    - Store-branded header with account items summary
    - Individual rounded-corner cards for Skins, Pickaxes, Emotes with outer borders
    - Vibrant color & contrast grading
    - Official verification footer & watermark stamp
    """
    if not images_dict:
        return None

    order = [
        ("skins", "SKINS LOCKER", (147, 51, 234)),       # Purple accent
        ("pickaxes", "PICKAXES", (14, 165, 233)),         # Cyan accent
        ("dances", "EMOTES & DANCES", (34, 197, 94))      # Green accent
    ]

    available = []
    for key, label, color in order:
        if key in images_dict and images_dict[key]:
            try:
                im = Image.open(io.BytesIO(images_dict[key])).convert("RGB")
                available.append((key, label, color, im))
            except Exception:
                pass

    if not available:
        return None

    # Harmonize height across available panels
    target_h = max(im.height for _, _, _, im in available)
    target_h = max(550, min(target_h, 1100))

    # Safe font loader with fallbacks
    def get_font(size: int, bold: bool = False):
        font_file = "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"
        try:
            return ImageFont.truetype(font_file, size)
        except Exception:
            try:
                fallback = "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"
                return ImageFont.truetype(fallback, size)
            except Exception:
                return ImageFont.load_default()

    title_font = get_font(24, bold=True)
    sub_font = get_font(14, bold=False)
    badge_font = get_font(13, bold=True)
    footer_font = get_font(13, bold=False)

    cards = []
    for key, label, color, im in available:
        ratio = target_h / max(1, im.height)
        new_w = max(1, int(im.width * ratio))
        resized = im.resize((new_w, target_h), Image.Resampling.LANCZOS)

        # Subtle polish: boost contrast & saturation so colors pop
        enhanced = ImageEnhance.Contrast(resized).enhance(1.04)
        enhanced = ImageEnhance.Color(enhanced).enhance(1.06)

        # Smooth rounded corners on the image tile
        corner_r = 14
        mask = Image.new("L", (new_w, target_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, new_w, target_h], radius=corner_r, fill=255)

        # Card container with top padding for category badge
        card_pad_top = 44
        card_pad_side = 8
        card_pad_bottom = 8
        card_w = new_w + card_pad_side * 2
        card_h = target_h + card_pad_top + card_pad_bottom

        card = Image.new("RGB", (card_w, card_h), color=(20, 22, 32))
        card_draw = ImageDraw.Draw(card)

        # Outer card frame border
        card_draw.rounded_rectangle([1, 1, card_w - 2, card_h - 2], radius=corner_r + 4, outline=(42, 46, 68), width=2)

        # Category pill badge on top
        badge_w = min(170, max(120, int(card_w * 0.45)))
        badge_x = (card_w - badge_w) // 2
        card_draw.rounded_rectangle([badge_x, 10, badge_x + badge_w, 34], radius=12, fill=(28, 31, 46), outline=color, width=1)
        card_draw.text((badge_x + 16, 14), label, fill=(245, 245, 250), font=badge_font)

        # Paste rounded image
        card.paste(enhanced, (card_pad_side, card_pad_top), mask)

        # Subtle semi-transparent watermark on bottom-right of each card
        try:
            wm_layer = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
            wm_draw = ImageDraw.Draw(wm_layer)
            wm_text = f"• {store_name.upper()} •"
            wm_draw.text((card_w - 140, card_h - 26), wm_text, fill=(255, 255, 255, 60), font=footer_font)
            card = Image.alpha_composite(card.convert("RGBA"), wm_layer).convert("RGB")
        except Exception:
            pass

        cards.append(card)

    gap = 16
    total_cards_w = sum(c.width for c in cards) + gap * (len(cards) - 1)
    max_card_h = max(c.height for c in cards)

    header_h = 70
    footer_h = 42
    pad_canvas = 20

    canvas_w = max(700, total_cards_w + pad_canvas * 2)
    canvas_h = max_card_h + header_h + footer_h + pad_canvas * 2

    # Deep gaming background canvas
    canvas = Image.new("RGB", (canvas_w, canvas_h), color=(12, 13, 20))
    draw = ImageDraw.Draw(canvas)

    # Top glowing neon accent gradient line (Purple to Cyan)
    for x in range(canvas_w):
        t = x / max(1, canvas_w)
        r = int(147 * (1 - t) + 14 * t)
        g = int(51 * (1 - t) + 165 * t)
        b = int(234 * (1 - t) + 233 * t)
        draw.line([(x, 0), (x, 3)], fill=(r, g, b))

    # Header title & subtitle
    draw.text((pad_canvas, pad_canvas + 6), f"🔥 {store_name.upper()}  •  EXCLUSIVE LOCKER SHOWCASE", fill=(255, 255, 255), font=title_font)
    subtitle = "Verified In-Game Items  |  Full Locker Preview"
    if skin_count:
        subtitle = f"{skin_count} Skins Verified  |  Full In-Game Assets Preview"
    draw.text((pad_canvas, pad_canvas + 40), subtitle, fill=(140, 145, 170), font=sub_font)

    # Center-align cards on canvas
    cur_x = (canvas_w - total_cards_w) // 2
    cur_y = pad_canvas + header_h
    for c in cards:
        canvas.paste(c, (cur_x, cur_y))
        cur_x += c.width + gap

    # Footer divider & verification stamp
    footer_y = canvas_h - footer_h - pad_canvas // 2
    draw.line([(pad_canvas, footer_y), (canvas_w - pad_canvas, footer_y)], fill=(34, 38, 56), width=1)
    draw.text((pad_canvas, footer_y + 10), f"🛡️ Secured & Verified by {store_name}  •  Instant Delivery", fill=(120, 126, 150), font=footer_font)

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=92)
    return buf.getvalue()

def get_scalable_font(size: int = 24, bold: bool = True):
    """Load a scalable TrueType font with fallbacks for both Windows and Linux (Render)."""
    font_file = "font_bold.ttf" if bold else "font_regular.ttf"
    local_bundled = os.path.join(BASE_DIR, "assets", "fonts", font_file)
    if os.path.exists(local_bundled):
        try:
            return ImageFont.truetype(local_bundled, size)
        except Exception:
            pass

    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

def restyle_category_image(
    im_bytes: bytes,
    cat_type: str = "skins",
    total_cnt: int = 0,
    shop_cnt: int = 0
) -> bytes:
    """
    Restyles raw image into a high-definition, crystal-clear Fortnite locker layout:
    - Maintains crisp native HD resolution (no aggressive downscaling)
    - Solid black header with large, bold typography (Linux & Windows compatible)
    - Authentic white icon (shirt, pickaxe, dance) on top-left
    - Clean divider bar '|'
    - Covers bottom supplier watermark & timestamp completely with store branding
    """
    im = Image.open(io.BytesIO(im_bytes)).convert("RGB")
    
    # Cap max height at 1500px for sharp HD viewing without excessive memory
    if im.height > 1500:
        ratio = 1500.0 / im.height
        new_w = max(1, int(im.width * ratio))
        resized_im = im.resize((new_w, 1500), Image.Resampling.LANCZOS)
        im.close()
        im = resized_im

    draw = ImageDraw.Draw(im)

    # 1. Fill top header area with pure black (0, 0, 0)
    header_h = 76
    draw.rectangle([0, 0, im.width, header_h], fill=(0, 0, 0))

    # 2. Paste authentic category icon
    icon_path = os.path.join(BASE_DIR, f"assets/icons/{cat_type}.png")
    if os.path.exists(icon_path):
        try:
            with Image.open(icon_path) as icon:
                icon_h = min(48, icon.height)
                icon_w = int(icon.width * (icon_h / max(1, icon.height)))
                icon_resized = icon.resize((icon_w, icon_h), Image.Resampling.LANCZOS)
                im.paste(icon_resized, (16, (header_h - icon_h) // 2))
        except Exception:
            pass

    # Divider bar
    draw.line([(70, 12), (70, header_h - 12)], fill=(160, 160, 160), width=2)

    # 3. Typography (Scalable for both Linux & Windows)
    font_large = get_scalable_font(34, bold=True)
    font_sub = get_scalable_font(18, bold=False)

    title_str = f"{total_cnt}" if not shop_cnt else f"{total_cnt} ({shop_cnt})"
    cat_names = {"skins": "Skins", "pickaxes": "Pickaxes", "dances": "Dances"}
    sub_str = cat_names.get(cat_type, cat_type.capitalize())

    draw.text((84, 10), title_str, fill=(255, 255, 255), font=font_large)
    draw.text((84, 46), sub_str, fill=(210, 210, 220), font=font_sub)

    # 4. Cover bottom supplier timestamp / watermark with clean black bar and branding
    footer_h = 32
    draw.rectangle([0, im.height - footer_h, im.width, im.height], fill=(0, 0, 0))
    store_name = config.get("store_name", "VENTO").upper()
    footer_text = f"🛡️ {store_name} EXCLUSIVE LOCKER"
    font_foot = get_scalable_font(14, bold=True)
    draw.text((16, im.height - footer_h + 8), footer_text, fill=(150, 155, 175), font=font_foot)

    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95)
    out_val = buf.getvalue()
    im.close()
    buf.close()
    return out_val

def combine_styled_images_side_by_side(styled_images: Dict[str, bytes]) -> Optional[bytes]:
    """
    Combines restyled category images (skins, pickaxes, dances) side-by-side
    into a single high-definition horizontal showcase graphic.
    """
    order = ["skins", "pickaxes", "dances"]
    imgs = []
    for key in order:
        if key in styled_images and styled_images[key]:
            try:
                imgs.append(Image.open(io.BytesIO(styled_images[key])).convert("RGB"))
            except Exception:
                pass

    if not imgs:
        return None

    if len(imgs) == 1:
        buf = io.BytesIO()
        imgs[0].save(buf, format="JPEG", quality=92)
        out_b = buf.getvalue()
        imgs[0].close()
        buf.close()
        return out_b

    # Target height for crisp, readable Discord display (HD resolution, up to 1050px)
    max_orig_h = max(im.height for im in imgs)
    target_h = min(1050, max_orig_h)

    resized = []
    for im in imgs:
        ratio = target_h / max(1, im.height)
        new_w = max(1, int(im.width * ratio))
        resized.append(im.resize((new_w, target_h), Image.Resampling.LANCZOS))
        im.close()

    gap = 8
    total_w = sum(im.width for im in resized) + gap * (len(resized) - 1)
    canvas = Image.new("RGB", (total_w, target_h), (14, 14, 18))

    x = 0
    for im in resized:
        canvas.paste(im, (x, 0))
        x += im.width + gap
        im.close()

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=92, subsampling=0)
    out_val = buf.getvalue()
    canvas.close()
    buf.close()
    del imgs; del resized
    gc.collect()
    return out_val

# OCR Verification for subscription proof screenshots
def verify_proof_screenshot(image_bytes: bytes) -> Tuple[bool, str, str]:
    """
    Perform OCR on the image if possible to extract text tokens for anti-theft tracking.
    Never rejects genuine users; always allows the proof to proceed to anti-cheat verification.
    """
    try:
        from rapidocr_onnxruntime import RapidOCR
        import numpy as np
        
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_np = np.array(pil_img)
        
        ocr = RapidOCR()
        result, _ = ocr(img_np)
        if not result:
            return True, "No text detected", ""
            
        full_text = " ".join([line[1].lower() for line in result])
        return True, "OCR completed", full_text
    except Exception:
        return True, "OCR bypassed", ""

# Helper function to create listing Embed
def create_account_embed(
    item: Dict[str, Any],
    score: float,
    rare_skins: List[str],
    currency: str,
    is_dm: bool = False,
    matched_targets: Optional[List[str]] = None
) -> discord.Embed:
    item_id = item.get("item_id", 0)
    title = item.get("title", "Premium Fortnite Account")
    raw_price = float(item.get("price", 0))
    profit_amount = float(config.get("profit_amount", 10.0))
    resale_price = round(raw_price + profit_amount, 2)
    
    seller = item.get("seller", {}).get("username", "Unknown")
    skin_count = LZTClient.extract_skin_count(item)
    
    # Extract account attributes
    details = LZTClient.extract_full_account_details(item)
    currency_symbol = "$" if currency.lower() == "usd" else currency.upper()

    # Deal rating badge
    if matched_targets:
        rating_badge = f"🎯 Target Item Match! ({', '.join(matched_targets)})"
        color = 0x9B59B6 # Purple / Amethyst
    elif score >= 35:
        rating_badge = "🔥 Rare / Grail Account"
        color = 0xFF4500 # OrangeRed
    elif score >= 20:
        rating_badge = "⭐ High Value Deal"
        color = 0x00FF7F # SpringGreen
    else:
        rating_badge = "✅ Available for Purchase"
        color = 0x1E90FF # DodgerBlue

    if is_dm:
        # Private DM to Bot Owner / Admins (Contains Supplier buy link, profit stats, seller)
        embed = discord.Embed(
            title="🎯 New Account Alert (Supplier Buy Link)",
            url=f"https://lzt.market/{item_id}/",
            description=f"🔗 **[Click here to buy directly from the Supplier](https://lzt.market/{item_id}/)**",
            color=color if matched_targets else 0xFFD700,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="💵 Supplier Price", value=f"**{raw_price} {currency_symbol}**", inline=True)
        embed.add_field(name="📈 Server Resale Price", value=f"**{resale_price} {currency_symbol}**", inline=True)
        embed.add_field(name="💰 Net Profit", value=f"**+{profit_amount} {currency_symbol}**", inline=True)
        embed.add_field(name="👤 Supplier Seller", value=f"`{seller}`", inline=True)
        embed.add_field(name="👕 Total Skins", value=f"**{skin_count} Skins**", inline=True)
        embed.add_field(name="🪙 V-Bucks", value=f"`{details['vbucks']}`", inline=True)
        
        embed.add_field(name="💎 Save The World (STW)", value=f"`{details['stw_edition']}`", inline=True)
        embed.add_field(name="🎮 Platform", value=f"`{details['platform']}`", inline=True)
        embed.add_field(name="🟦 PlayStation (PSN)", value=f"`{details['psn_linkable']}`", inline=True)
        
        embed.add_field(name="🟩 Xbox Linkable", value=f"`{details['xbox_linkable']}`", inline=True)
        embed.add_field(name="✉️ Email Status", value=f"`{details['changeable_email']}`", inline=True)
        embed.add_field(name="📧 Email Domain", value=f"`{details['email_domain']}`", inline=True)
        
        embed.add_field(name="📅 Account Created", value=f"`{details['register_date']}`", inline=True)
        embed.add_field(name="🕒 Last Active", value=f"`{details['last_activity']}`", inline=True)
        embed.add_field(name="🔗 Linked Accounts", value=f"`{details['social_accounts']}`", inline=False)
        
        if matched_targets:
            embed.add_field(name="🎯 Target Items Detected", value=", ".join([f"`{t}`" for t in matched_targets]), inline=False)

        if rare_skins:
            embed.add_field(name="💎 Rare Items Detected", value=", ".join(rare_skins), inline=False)

        embed.set_footer(text=f"Admin Alert • Supplier Item ID: {item_id}")
        return embed

    else:
        # Public Channel Embed for Server Customers - Fixed static title for all accounts
        fixed_title = config.get("fixed_account_title", "🎮 Fortnite Special Account")
        embed = discord.Embed(
            title=fixed_title,
            description=f"**{rating_badge}**\nSpecial account available for instant purchase! To purchase or inquire, please open a ticket or contact staff.",
            color=color,
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="💰 Price", value=f"**{resale_price} {currency_symbol}**", inline=True)
        embed.add_field(name="👕 Total Skins", value=f"**{skin_count} Skins**", inline=True)
        embed.add_field(name="🪙 V-Bucks", value=f"`{details['vbucks']}`", inline=True)
        
        embed.add_field(name="💎 Save The World (STW)", value=f"`{details['stw_edition']}`", inline=True)
        embed.add_field(name="🎮 Platform", value=f"`{details['platform']}`", inline=True)
        embed.add_field(name="🟦 PlayStation (PSN)", value=f"`{details['psn_linkable']}`", inline=True)
        
        embed.add_field(name="🟩 Xbox Linkable", value=f"`{details['xbox_linkable']}`", inline=True)
        embed.add_field(name="✉️ Email Status", value=f"`{details['changeable_email']}`", inline=True)
        embed.add_field(name="📧 Email Domain", value=f"`{details['email_domain']}`", inline=True)
        
        embed.add_field(name="📅 Account Created", value=f"`{details['register_date']}`", inline=True)
        embed.add_field(name="🕒 Last Active", value=f"`{details['last_activity']}`", inline=True)
        embed.add_field(name="🔗 Linked Accounts", value=f"`{details['social_accounts']}`", inline=False)

        if matched_targets:
            embed.add_field(name="🎯 Featured Items", value=", ".join([f"`{t}`" for t in matched_targets]), inline=False)

        if rare_skins:
            embed.add_field(name="💎 Rare Items Detected", value=", ".join(rare_skins), inline=False)

        embed.set_footer(text="Account Store • To purchase, please open a ticket in the server")
        return embed

# Discord View with Direct Link Button (Sent in Owner's Private DM only)
class AccountLinkView(discord.ui.View):
    def __init__(self, item_id: int):
        super().__init__(timeout=None)
        url = f"https://lzt.market/{item_id}/"
        self.add_item(discord.ui.Button(label="🛒 Buy from Supplier", url=url, style=discord.ButtonStyle.link, emoji="🔗"))

# Informative Contact Button (Sent in Public Server Channel)
class CustomerContactView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="📩 Open Ticket to Purchase", style=discord.ButtonStyle.secondary, disabled=True, emoji="🛒"))

# Core function to scan and send accounts
async def check_and_alert_accounts(channel: discord.abc.Messageable, is_manual: bool = False) -> int:
    """
    Search LZT Market for Fortnite accounts, send locker images, and alert owner in DM.
    Returns number of alerts sent.
    """
    currency = config.get("currency", "usd")
    min_price = float(config.get("min_price", 1))
    max_price = float(config.get("max_price", 50))
    min_skins = int(config.get("min_skins", 20))
    max_skins = int(config.get("max_skins", 0))
    min_vbucks = int(config.get("min_vbucks", 0))
    order_by = config.get("order_by", "price_to_up")
    rare_keywords = config.get("rare_keywords", [])

    target_items = config.get("target_items", [])
    filter_by_target = config.get("filter_by_target", False)

    items = []
    error = None
    seen_ids = set(load_seen_accounts())
    seen_t_ids = set()

    # 1. If target items are specified, query LZT specifically for them
    if target_items:
        for target in target_items[:3]:
            t_items, t_err = await lzt_client.get_fortnite_accounts(
                min_price=min_price,
                max_price=max_price,
                min_skins=min_skins,
                max_skins=max_skins,
                min_vbucks=min_vbucks,
                psn_linkable="nomatter",
                xbox_linkable="nomatter",
                currency=currency,
                order_by=order_by,
                daybreak=int(config.get("daybreak", 0)),
                title=target
            )
            if t_err and not error:
                error = t_err
            if t_items:
                for it in t_items:
                    iid = it.get("item_id")
                    if iid and iid not in seen_ids and iid not in seen_t_ids:
                        seen_t_ids.add(iid)
                        items.append(it)
                del t_items
                gc.collect()

    # 2. General deals search (ONLY when user has NOT set any target items)
    if not target_items:
        g_items, g_err = await lzt_client.get_fortnite_accounts(
            min_price=min_price,
            max_price=max_price,
            min_skins=min_skins,
            max_skins=max_skins,
            min_vbucks=min_vbucks,
            psn_linkable="nomatter",
            xbox_linkable="nomatter",
            currency=currency,
            order_by=order_by,
            daybreak=int(config.get("daybreak", 0))
        )
        if g_items:
            for it in g_items:
                iid = it.get("item_id")
                if iid and iid not in seen_ids:
                    items.append(it)
            del g_items
            gc.collect()
        elif not error:
            error = g_err

    if error:
        if channel:
            try:
                await channel.send(f"⚠️ **Supplier Search Warning:**\n{error}")
            except Exception:
                pass
        return 0

    new_items = items

    if not new_items:
        if channel:
            try:
                if target_items:
                    targets_str = ", ".join([f"`{t}`" for t in target_items])
                    await channel.send(
                        f"ℹ️ **نتيجة فحص السوق:**\n"
                        f"لا توجد عروض جديدة غير منشورة تحتوي على جميع طلباتك بالضبط ({targets_str})."
                    )
                elif is_manual:
                    await channel.send("ℹ️ Market check complete: No new unposted deals found.")
            except Exception:
                pass
        return 0

    # Score and filter each account
    scored_items = []
    for it in new_items:
        matched_targets = LZTClient.detect_target_items(it, target_items)
        
        # When target items are set, the account MUST contain ALL requested items!
        if target_items:
            has_all_targets = (len(matched_targets) == len(target_items))
            if not has_all_targets:
                # Skip accounts that do not contain ALL requested target items (exact match required)
                continue

        score = LZTClient.calculate_deal_score(it, rare_keywords, target_items)
        rare_detected = LZTClient.detect_rare_skins(it.get("title", ""), rare_keywords)
        scored_items.append((it, score, rare_detected, matched_targets))

    if not scored_items:
        if channel:
            try:
                if target_items:
                    targets_str = ", ".join([f"`{t}`" for t in target_items])
                    await channel.send(
                        f"ℹ️ **نتيجة فحص السوق:**\n"
                        f"لا يوجد أي حساب متوفر حالياً يحتوي على جميع طلباتك بالضبط:\n"
                        f"🎯 **العناصر المطلوبة:** {targets_str}\n"
                        f"*(سيستمر البوت بالبحث التلقائي وسينبهك فور توفر حساب يطابق طلبك كاملاً)*"
                    )
                elif is_manual:
                    await channel.send("ℹ️ Market check complete: No new unposted deals found.")
            except Exception:
                pass
        return 0

    # Sort by score descending
    scored_items.sort(key=lambda x: x[1], reverse=True)

    # Pick top deals per cycle (top 1 on manual check for instant response, top 2 on automatic cycles)
    top_deals = scored_items[:1] if is_manual else scored_items[:2]
    sent_count = 0

    for item, score, rare_detected, matched_targets in top_deals:
        item_id = item.get("item_id", 0)

        # 1. Fetch locker images (skins, pickaxes, dances) using fast direct signed CDN links
        images_dict = await lzt_client.get_all_item_images(item_id, item_dict=item)

        # 2. Extract counts for authentic header styling
        skin_cnt = LZTClient.extract_skin_count(item)
        shop_skins = item.get("epicgames_fortnite_shop_skins_count") or 0
        pickaxe_cnt = item.get("epicgames_fortnite_pickaxe_count") or 0
        shop_pickaxes = item.get("epicgames_fortnite_shop_pickaxes_count") or 0
        dance_cnt = item.get("epicgames_fortnite_dance_count") or 0
        shop_dances = item.get("epicgames_fortnite_shop_dances_count") or 0

        # Restyle each category image to match the reference design exactly
        styled_images = {}
        if "skins" in images_dict and images_dict["skins"]:
            styled_images["skins"] = restyle_category_image(images_dict["skins"], "skins", skin_cnt, shop_skins)
        if "pickaxes" in images_dict and images_dict["pickaxes"]:
            styled_images["pickaxes"] = restyle_category_image(images_dict["pickaxes"], "pickaxes", pickaxe_cnt, shop_pickaxes)
        if "dances" in images_dict and images_dict["dances"]:
            styled_images["dances"] = restyle_category_image(images_dict["dances"], "dances", dance_cnt, shop_dances)

        # 3. Combine styled images side-by-side into a single showcase graphic
        combined_showcase_bytes = combine_styled_images_side_by_side(styled_images)

        # 4. Public server post with high-definition side-by-side locker showcase
        public_embed = create_account_embed(item, score, rare_detected, currency, is_dm=False, matched_targets=matched_targets)
        public_files = []

        if combined_showcase_bytes:
            public_files.append(discord.File(io.BytesIO(combined_showcase_bytes), filename="locker_showcase.jpg"))
            public_embed.set_image(url="attachment://locker_showcase.jpg")
        elif "skins" in styled_images and styled_images["skins"]:
            public_files.append(discord.File(io.BytesIO(styled_images["skins"]), filename="1_skins.jpg"))
            public_embed.set_image(url="attachment://1_skins.jpg")

        # Send to public server channel (without seller name, with increased price)
        if channel:
            try:
                if public_files:
                    await channel.send(embed=public_embed, files=public_files, view=CustomerContactView())
                else:
                    await channel.send(embed=public_embed, view=CustomerContactView())
            except Exception as e:
                print(f"[Market] Error posting to channel: {e}")

        # 5. Send private notification to Bot Owners / DM Recipients with secret buy link
        recipients = get_dm_recipients(config, bot)
        for recipient_id in recipients:
            try:
                recipient_user = bot.get_user(int(recipient_id)) or await bot.fetch_user(int(recipient_id))
                if recipient_user:
                    dm_embed = create_account_embed(item, score, rare_detected, currency, is_dm=True, matched_targets=matched_targets)
                    dm_files = []

                    if combined_showcase_bytes:
                        dm_files.append(discord.File(io.BytesIO(combined_showcase_bytes), filename="locker_showcase_dm.jpg"))
                        dm_embed.set_image(url="attachment://locker_showcase_dm.jpg")
                    elif "skins" in styled_images and styled_images["skins"]:
                        dm_files.append(discord.File(io.BytesIO(styled_images["skins"]), filename="1_skins_dm.jpg"))
                        dm_embed.set_image(url="attachment://1_skins_dm.jpg")

                    dm_view = AccountLinkView(item_id)
                    if dm_files:
                        await recipient_user.send(embed=dm_embed, files=dm_files, view=dm_view)
                    else:
                        await recipient_user.send(embed=dm_embed, view=dm_view)
            except Exception as e:
                print(f"[Owner DM] Failed to send private DM to user {recipient_id}: {e}")

        seen_ids.add(item_id)
        sent_count += 1
        del images_dict; del styled_images; del combined_showcase_bytes
        gc.collect()
        await asyncio.sleep(2) # Pause between posts

    # Save seen accounts
    save_seen_accounts(list(seen_ids))
    del items; del scored_items; del new_items
    gc.collect()
    return sent_count


# Background Loop Task
@tasks.loop(minutes=30)
async def tracker_task():
    global config
    config = load_config()
    
    if not config.get("is_running", True):
        return

    channel_id = config.get("channel_id")
    if not channel_id:
        print("[Tracker] Channel ID not set. Use /set_channel to set it.")
        return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except Exception as e:
            print(f"[Tracker] Could not find channel {channel_id}: {e}")
            return

    try:
        print(f"[Tracker] Starting scheduled check at {get_current_time_str()}...")
        sent = await check_and_alert_accounts(channel, is_manual=False)
        print(f"[Tracker] Check completed. Sent {sent} new deal alerts.")
    except Exception as e:
        print(f"[Tracker] Error in tracker loop: {e}")

@tracker_task.before_loop
async def before_tracker_task():
    await bot.wait_until_ready()

def update_tracker_interval(minutes: int):
    """Dynamically change tracker loop interval."""
    tracker_task.change_interval(minutes=minutes)
    if tracker_task.is_running():
        tracker_task.restart()


# Events
@bot.event
async def on_ready():
    global config
    print("=" * 50)
    print(f"Logged in as: {bot.user.name} (ID: {bot.user.id})")
    print(f"Connected to Discord successfully at {get_current_time_str()}!")
    
    # Register persistent view so buttons work across restarts
    try:
        bot.add_view(ControlPanelView())
    except Exception as e:
        print(f"Failed to register ControlPanelView: {e}")

    # Sync Slash Commands (once on startup) - instantly copy to all guilds for zero propagation delay
    if not getattr(bot, "_has_synced", False):
        try:
            for g in bot.guilds:
                try:
                    bot.tree.copy_global_to(guild=g)
                    await bot.tree.sync(guild=g)
                    print(f"Instantly synced slash commands to guild: {g.name} ({g.id})")
                except Exception as ge:
                    print(f"Guild sync notice for {g.id}: {ge}")
            synced = await bot.tree.sync()
            bot._has_synced = True
            print(f"Synced {len(synced)} global application (slash) commands.")
        except Exception as e:
            print(f"Failed to sync slash commands: {e}")

    # Set Activity
    interval = config.get("interval_minutes", 30)
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"Fortnite deals every {interval}m 🔍"
        )
    )

    # Start loop with saved interval
    tracker_task.change_interval(minutes=interval)
    if config.get("is_running", True) and not tracker_task.is_running():
        tracker_task.start()
        print(f"Background tracker started (every {interval} minutes).")

    # Start health check web server for Render / Cloud hosting
    port = os.getenv("PORT")
    if port:
        try:
            from aiohttp import web
            app = web.Application()
            async def health(request):
                return web.Response(text="VentoBot is running 24/7!")
            app.router.add_get("/", health)
            app.router.add_get("/health", health)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", int(port))
            await site.start()
            print(f"[Web] Health check server listening on port {port}")
        except Exception as we:
            print(f"[Web] Health check server notice: {we}")

    print("=" * 50)


@bot.event
async def on_message(message: discord.Message):
    # Ignore messages sent by bots
    if message.author.bot:
        return

    # Process normal bot commands first
    await bot.process_commands(message)

    # Check if the message was sent in the designated proof channel
    proof_chan_id = config.get("proof_channel_id")
    if not proof_chan_id or message.channel.id != int(proof_chan_id):
        return

    # Check if message contains an image attachment
    image_att = None
    if message.attachments:
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                image_att = att
                break
            ext = att.filename.lower().split(".")[-1] if "." in att.filename else ""
            if ext in ["png", "jpg", "jpeg", "webp", "gif"]:
                image_att = att
                break

    if image_att:
        try:
            image_bytes = await image_att.read()

            # 1. OCR text extraction (for fingerprints & anti-theft)
            _, _, detected_text = verify_proof_screenshot(image_bytes)

            # 2. Anti-Cheat: Check if the screenshot is a duplicate or cropped/stolen
            fingerprints = calculate_image_hashes(image_bytes, ocr_text=detected_text)
            seen_images = load_seen_images()
            is_dup, prev_entry, dup_reason = check_if_duplicate(fingerprints, seen_images, current_user_id=message.author.id)

            if is_dup:
                try:
                    await message.add_reaction("❌")
                except Exception:
                    pass
                
                prev_user_mention = f"<@{prev_entry['user_id']}>" if prev_entry and prev_entry.get("user_id") else "another member"
                reason_detail = f"\n*Detection Detail: {dup_reason}*" if dup_reason else ""
                await message.reply(
                    f"⚠️ **Duplicate/Stolen Screenshot!** {message.author.mention}\n"
                    f"This screenshot was already used or cropped from an existing upload by {prev_user_mention} 🚫"
                    f"{reason_detail}\n"
                    "Please upload your own original, uncropped screenshot to claim the role.",
                    delete_after=15
                )
                return

            # 3. Save verified image fingerprints to database
            entry = {
                "user_id": message.author.id,
                "user_name": str(message.author),
                "timestamp": datetime.datetime.now().isoformat(),
                "filename": image_att.filename,
                **fingerprints
            }
            seen_images.append(entry)
            save_seen_images(seen_images)

            # 4. Add checkmark reaction (✅)
            try:
                await message.add_reaction("✅")
            except Exception as e:
                print(f"[Proof] Failed to add reaction: {e}")

            # 5. Grant role to member if proof role is configured
            proof_role_id = config.get("proof_role_id")
            if proof_role_id and message.guild:
                role = message.guild.get_role(int(proof_role_id))
                if role:
                    try:
                        member = message.author
                        if not isinstance(member, discord.Member):
                            member = message.guild.get_member(message.author.id) or await message.guild.fetch_member(message.author.id)
                        if member and role not in member.roles:
                            await member.add_roles(role, reason="Automatic subscription verification")
                        
                        await message.reply(
                            f"🎉 **Congratulations {message.author.mention}!**\n"
                            f"Your subscription has been verified successfully and you have been granted the **{role.name}** role! ✅",
                            delete_after=12
                        )
                    except discord.Forbidden:
                        await message.channel.send(
                            f"⚠️ **Staff Warning:** The bot does not have sufficient permissions to grant the role `{role.name}`. "
                            "Please ensure the bot's role is positioned above `{role.name}` in Server Settings and has `Manage Roles` enabled.",
                            delete_after=15
                        )
                    except Exception as e:
                        print(f"[Proof] Error assigning role: {e}")
                else:
                    print(f"[Proof] Role ID {proof_role_id} not found in guild.")

        except Exception as e:
            print(f"[Proof] Error during image verification: {e}")


# ==========================================
# Control Panel UI & Modals
# ==========================================

def build_panel_embed() -> discord.Embed:
    """Build the rich status embed for the control panel."""
    channel_mention = f"<#{config['channel_id']}>" if config.get("channel_id") else "❌ Not configured"
    proof_channel_mention = f"<#{config['proof_channel_id']}>" if config.get("proof_channel_id") else "❌ Not configured"
    proof_role_mention = f"<@&{config['proof_role_id']}>" if config.get("proof_role_id") else "❌ Not configured"
    status_str = "🟢 Active (Running)" if config.get("is_running") and tracker_task.is_running() else "🔴 Stopped"
    has_token = "✅ Connected" if lzt_client.api_token else "❌ Not configured (/set_token)"
    seen_count = len(load_seen_accounts())
    seen_images_count = len(load_seen_images())
    curr_symbol = "$" if config.get("currency") == "usd" else config.get("currency").upper()
    profit_amt = config.get("profit_amount", 10.0)

    psn_text = "All (No restriction)"
    if config.get("psn_linkable") == "yes":
        psn_text = "PSN Linkable Only ✅"
    elif config.get("psn_linkable") == "no":
        psn_text = "Not PSN Linkable ❌"

    embed = discord.Embed(
        title="🎛️ Fortnite Bot Control Panel",
        description="Private control panel for managing deals, filters, and automation.",
        color=0x5865F2,
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="Supplier Tracker Status", value=status_str, inline=True)
    embed.add_field(name="Check Interval", value=f"Every **{config.get('interval_minutes', 30)}** mins", inline=True)
    embed.add_field(name="Deals Channel", value=channel_mention, inline=True)
    
    embed.add_field(name="💰 Added Server Profit", value=f"**+{profit_amt} {curr_symbol}**", inline=True)
    embed.add_field(name="🔒 Private DMs Delivery", value="Authorized Owners Only (`recipients.txt`)", inline=True)
    embed.add_field(name="Supplier API Token", value=has_token, inline=True)
    
    embed.add_field(name="Price Range", value=f"{config.get('min_price')}{curr_symbol} - {config.get('max_price')}{curr_symbol}", inline=True)
    embed.add_field(name="Min Skins", value=f"{config.get('min_skins')} Skins", inline=True)
    embed.add_field(name="🎮 PlayStation (PSN)", value=psn_text, inline=True)
    
    daybreak_val = config.get("daybreak", 0)
    daybreak_str = f"Inactive for **{daybreak_val}+ days** ⏳" if daybreak_val > 0 else "All (No minimum) 🌐"
    embed.add_field(name="⏳ Inactivity Filter", value=daybreak_str, inline=True)
    embed.add_field(name="📸 Proof Channel", value=proof_channel_mention, inline=True)
    embed.add_field(name="🎖️ Subscriber Role", value=proof_role_mention, inline=True)
    embed.add_field(name="🛡️ Verified Proofs", value=f"{seen_images_count} images", inline=True)

    target_items = config.get("target_items", [])
    filter_by_target = config.get("filter_by_target", False)
    target_str = ", ".join(target_items) if target_items else "None (General search)"
    target_mode_str = "Strict Target Match Only 🎯" if filter_by_target else "General (Highlight matches) 🌐"

    embed.add_field(name="🎯 Target Items", value=f"`{target_str[:80]}`", inline=True)
    embed.add_field(name="⚙️ Target Filter Mode", value=target_mode_str, inline=True)
    embed.add_field(name="🎨 Graphics Branding", value=f"**{config.get('store_name', 'VENTO')}**", inline=True)

    embed.set_footer(text="Private Control Panel • Authorized Owners Only")
    return embed


class IntervalModal(discord.ui.Modal, title="⏱️ Change Scan Interval"):
    minutes_input = discord.ui.TextInput(
        label="Interval in minutes (min 5, e.g. 30)",
        placeholder="Enter number of minutes...",
        default="30",
        min_length=1,
        max_length=4
    )

    def __init__(self, current_val: int):
        super().__init__()
        self.minutes_input.default = str(current_val)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can modify settings.", ephemeral=True)
            return
        try:
            mins = int(self.minutes_input.value.strip())
            if mins < 5:
                await interaction.response.send_message("⚠️ Minimum allowed interval is 5 minutes to avoid rate limits.", ephemeral=True)
                return
            global config
            config["interval_minutes"] = mins
            save_config(config)
            update_tracker_interval(mins)
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"Fortnite deals every {mins}m 🔍"
                )
            )
            await interaction.response.send_message(f"✅ Scan interval updated to every **{mins} minutes**!", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("⚠️ Please enter a valid number.", ephemeral=True)


class FiltersModal(discord.ui.Modal, title="⚙️ Edit Account Filters & Profit"):
    min_skins_input = discord.ui.TextInput(label="Minimum Skins Count", placeholder="20", default="20")
    max_price_input = discord.ui.TextInput(label="Maximum Supplier Price ($)", placeholder="50", default="50")
    daybreak_input = discord.ui.TextInput(label="Inactivity Days (0 = All / Any)", placeholder="30", default="0")
    profit_input = discord.ui.TextInput(label="Server Profit Added ($)", placeholder="10", default="10")

    def __init__(self, cur_skins: int, cur_price: float, cur_profit: float, cur_daybreak: int = 0):
        super().__init__()
        self.min_skins_input.default = str(cur_skins)
        self.max_price_input.default = str(cur_price)
        self.daybreak_input.default = str(cur_daybreak)
        self.profit_input.default = str(cur_profit)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can modify filters.", ephemeral=True)
            return
        global config
        try:
            config["min_skins"] = max(0, int(self.min_skins_input.value.strip()))
            config["max_price"] = max(1.0, float(self.max_price_input.value.strip()))
            config["daybreak"] = max(0, int(self.daybreak_input.value.strip()))
            config["profit_amount"] = max(0.0, float(self.profit_input.value.strip()))
            save_config(config)
            daybreak_text = f"{config['daybreak']}+ days inactive" if config['daybreak'] > 0 else "All (Any activity)"
            await interaction.response.send_message(
                f"✅ **Filters and Profit updated successfully!**\n"
                f"• Minimum Skins: {config['min_skins']}\n"
                f"• Maximum Price: {config['max_price']}$\n"
                f"• Inactivity Filter: {daybreak_text}\n"
                f"• Added Profit Margin: +{config['profit_amount']}$",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Input error: {e}", ephemeral=True)


class TargetItemsModal(discord.ui.Modal, title="🎯 Set Target Skins / Items"):
    items_input = discord.ui.TextInput(
        label="Skins or Keywords (separated by comma)",
        placeholder="e.g. Travis Scott, Black Knight, Minty, Leviathan",
        default="",
        required=False,
        style=discord.TextStyle.paragraph
    )

    def __init__(self, current_items: List[str]):
        super().__init__()
        self.items_input.default = ", ".join(current_items)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can modify target items.", ephemeral=True)
            return
        global config
        raw_val = self.items_input.value.strip()
        if raw_val:
            items_list = [i.strip() for i in raw_val.split(",") if i.strip()]
        else:
            items_list = []
        config["target_items"] = items_list
        save_config(config)
        items_str = ", ".join(items_list) if items_list else "None (Cleared)"
        mode_text = "Strict Target Match Only 🎯" if config.get("filter_by_target") else "General Search with Highlights 🌐"
        await interaction.response.send_message(
            f"✅ **Target items list updated!**\n"
            f"• Target Items: `{items_str}`\n"
            f"• Current Mode: **{mode_text}**\n\n"
            f"💡 *Tip: You can use `/add_target` for live suggestions and autocomplete for Skins, Pickaxes, and Dances!*",
            ephemeral=True
        )


POPULAR_SKINS = [
    {"label": "Travis Scott", "desc": "Icon Series Outfit", "emoji": "👕"},
    {"label": "Black Knight", "desc": "Season 2 Legendary Knight", "emoji": "🛡️"},
    {"label": "Renegade Raider", "desc": "Season 1 OG Grail", "emoji": "🔥"},
    {"label": "Ikonik", "desc": "Exclusive Samsung Outfit", "emoji": "📱"},
    {"label": "Galaxy", "desc": "Exclusive Galaxy Outfit", "emoji": "🌌"},
    {"label": "Wonder", "desc": "Exclusive Honor Outfit", "emoji": "💎"},
    {"label": "Honor Guard", "desc": "Exclusive Honor View 20", "emoji": "🏍️"},
    {"label": "Wildcat", "desc": "Exclusive Nintendo Switch Outfit", "emoji": "🐱"},
    {"label": "OG Ghoul Trooper", "desc": "Halloween Classic", "emoji": "🧟"},
    {"label": "OG Skull Trooper", "desc": "Halloween Classic", "emoji": "💀"},
    {"label": "Aerial Assault Trooper", "desc": "Season 1 OG Grail", "emoji": "🪖"},
    {"label": "Glow", "desc": "Exclusive Samsung Outfit", "emoji": "✨"},
    {"label": "Stealth Reflex", "desc": "Exclusive GeForce Outfit", "emoji": "🥷"},
    {"label": "Psycho Bandit", "desc": "Borderlands Collab", "emoji": "🎭"},
    {"label": "Dark Skully", "desc": "Exclusive Xbox Bundle", "emoji": "🖤"},
    {"label": "Omega", "desc": "Season 4 Level 80 Lights", "emoji": "⚡"},
    {"label": "The Reaper", "desc": "Season 3 John Wick", "emoji": "🕶️"},
    {"label": "Leviathan", "desc": "Space Suit Fishbowl", "emoji": "🐟"},
    {"label": "Astro Jack", "desc": "Travis Scott Astronomical", "emoji": "🚀"},
    {"label": "Chun-Li", "desc": "Street Fighter Series", "emoji": "🥋"},
    {"label": "Kratos", "desc": "Gaming Legends Series", "emoji": "🪓"},
    {"label": "Master Chief", "desc": "Gaming Legends Series", "emoji": "🛡️"},
    {"label": "Spider-Man", "desc": "Marvel Series", "emoji": "🕷️"},
    {"label": "Deadpool", "desc": "Marvel Series Chapter 2 Season 2", "emoji": "⚔️"},
    {"label": "Travis Scott (T-3000)", "desc": "Travis Scott Style", "emoji": "🔥"}
]

POPULAR_PICKAXES = [
    {"label": "Candy Axe", "desc": "Festive lights pickaxe", "emoji": "🍬"},
    {"label": "Merry Mint Axe", "desc": "Exclusive Minty Pickaxe", "emoji": "🍃"},
    {"label": "Leviathan Axe", "desc": "Kratos Leviathan Pickaxe", "emoji": "🪓"},
    {"label": "Reaper", "desc": "Original Scythe Pickaxe", "emoji": "⛏️"},
    {"label": "Star Wand", "desc": "Sweaty wand pickaxe", "emoji": "⭐"},
    {"label": "Raider's Revenge", "desc": "Season 1 OG Pickaxe", "emoji": "🔥"},
    {"label": "Harley Hitter", "desc": "DC Series baseball bat", "emoji": "⚾"},
    {"label": "Driver", "desc": "Golf club pickaxe", "emoji": "🏌️"},
    {"label": "Ice Breaker", "desc": "Shovel pickaxe", "emoji": "❄️"},
    {"label": "Studded Axe", "desc": "Sweat quiet pickaxe", "emoji": "⛏️"},
    {"label": "Crowbar", "desc": "High Stakes pickaxe", "emoji": "🔧"},
    {"label": "Vision", "desc": "Eye pickaxe", "emoji": "👁️"},
    {"label": "Trusty No. 2", "desc": "Season 3 pencil pickaxe", "emoji": "✏️"},
    {"label": "AC/DC", "desc": "Season 2 electric pickaxe", "emoji": "⚡"},
    {"label": "Catwoman's Grappling Claw", "desc": "DC Series claw", "emoji": "🐾"}
]

POPULAR_DANCES = [
    {"label": "Floss", "desc": "Season 2 OG Dance", "emoji": "💃"},
    {"label": "Take The L", "desc": "Season 3 Classic", "emoji": "👆"},
    {"label": "Scenario", "desc": "Exclusive Ikonik Emote", "emoji": "🎵"},
    {"label": "Fresh", "desc": "Carlton Dance Chapter 1", "emoji": "🕺"},
    {"label": "Tidestorm", "desc": "Rare icon dance", "emoji": "🌊"},
    {"label": "Boogie Down", "desc": "2FA Exclusive Emote", "emoji": "🪩"},
    {"label": "Rambunctious", "desc": "Rare Chapter 1 Emote", "emoji": "🕺"},
    {"label": "Zany", "desc": "Rare Chapter 1 Emote", "emoji": "🤪"},
    {"label": "Pure Salt", "desc": "Salt sprinkle emote", "emoji": "🧂"},
    {"label": "The Worm", "desc": "Season 2 Battle Pass", "emoji": "🐛"},
    {"label": "Electro Shuffle", "desc": "Classic electronic dance", "emoji": "⚡"},
    {"label": "Orange Justice", "desc": "Season 4 Battle Pass", "emoji": "🍊"},
    {"label": "Ride The Pony", "desc": "Season 2 OG Emote", "emoji": "🐴"},
    {"label": "Laugh It Up", "desc": "Donkey laugh emote", "emoji": "😂"},
    {"label": "Tidy", "desc": "Snoop Dogg dance Chapter 1", "emoji": "🧹"}
]

def build_target_items_embed() -> discord.Embed:
    targets = config.get("target_items", [])
    filter_mode = config.get("filter_by_target", False)
    mode_text = "🟢 مفعل (حصر البحث بالسكنات المطلوبة فقط)" if filter_mode else "⚪ معطل (بحث عام مع تمييز السكنات المطلوبة)"
    
    if targets:
        target_list_str = "\n".join([f"• `{t}`" for t in targets])
    else:
        target_list_str = "*لا توجد عناصر مضافة حالياً*"
    
    embed = discord.Embed(
        title="🎯 تحديد واختيار السكنات والأكسات والرقصات",
        description=(
            f"**اختر مباشرة من القوائم المنسدلة بالأسفل لإضافة أو إزالة أي عنصر بضغطة زر واحدة:**\n\n"
            f"• **وضع الحصر:** {mode_text}\n"
            f"• **العناصر المحددة حالياً ({len(targets)}):**\n{target_list_str}\n\n"
            f"💡 **للبحث المباشر بالكتابة في أكثر من 6,500 عنصر:**\n"
            f"اكتب في الشات الأمر `/add_target` ثم اكتب أحرف السكن (مثل `trav` أو `black`) وستظهر لك الخيارات فوراً!"
        ),
        color=0x9B59B6
    )
    return embed


class TargetItemSelectComponent(discord.ui.Select):
    def __init__(self, placeholder: str, items: List[Dict[str, str]], action_type: str, row: int):
        options = []
        for it in items[:25]:
            options.append(discord.SelectOption(
                label=it["label"][:100],
                value=it["label"][:100],
                description=it.get("desc", "")[:100],
                emoji=it.get("emoji")
            ))
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=row,
            custom_id=f"target_sel_{action_type}"
        )
        self.action_type = action_type

    async def callback(self, interaction: discord.Interaction):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can modify targets.", ephemeral=True)
            return

        selected_val = self.values[0]
        targets = list(config.get("target_items", []))
        
        if self.action_type == "remove":
            if selected_val in targets:
                targets.remove(selected_val)
                config["target_items"] = targets
                save_config(config)
                msg = f"🗑️ تم حذف: **{selected_val}** من القائمة!"
            else:
                msg = f"⚠️ العنصر **{selected_val}** غير موجود بالقائمة."
        else:
            if selected_val not in targets:
                targets.append(selected_val)
                config["target_items"] = targets
                config["filter_by_target"] = True
                save_config(config)
                msg = f"✅ تم إضافة: **{selected_val}** وتفعيل البحث المخصص عنه فوراً!"
            else:
                config["filter_by_target"] = True
                save_config(config)
                msg = f"ℹ️ العنصر **{selected_val}** موجود بالفعل (تم تفعيل البحث المخصص عنه)."

        view = TargetItemsView()
        embed = build_target_items_embed()
        await interaction.response.edit_message(content=msg, embed=embed, view=view)


class TargetItemsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        
        # Row 0: Skins Dropdown
        self.add_item(TargetItemSelectComponent(
            placeholder="👕 اختر سكن من السكنات النادرة (Select Skin)",
            items=POPULAR_SKINS,
            action_type="add_skin",
            row=0
        ))
        
        # Row 1: Pickaxes Dropdown
        self.add_item(TargetItemSelectComponent(
            placeholder="⛏️ اختر فأس / أكس (Select Pickaxe)",
            items=POPULAR_PICKAXES,
            action_type="add_pickaxe",
            row=1
        ))
        
        # Row 2: Dances Dropdown
        self.add_item(TargetItemSelectComponent(
            placeholder="💃 اختر رقصة (Select Dance / Emote)",
            items=POPULAR_DANCES,
            action_type="add_dance",
            row=2
        ))
        
        # Row 3: Remove dropdown if targets exist
        targets = config.get("target_items", [])
        if targets:
            remove_items = [{"label": t, "desc": "اضغط لحذفه من القائمة", "emoji": "🗑️"} for t in targets[:25]]
            self.add_item(TargetItemSelectComponent(
                placeholder="🗑️ اختر عنصراً لحذفه من القائمة (Remove Item)",
                items=remove_items,
                action_type="remove",
                row=3
            ))

    @discord.ui.button(label="Toggle Strict Mode 🎯", style=discord.ButtonStyle.primary, row=4, custom_id="tgt_btn_toggle")
    async def btn_toggle_filter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can modify targets.", ephemeral=True)
            return

        config["filter_by_target"] = not config.get("filter_by_target", False)
        save_config(config)
        status = "مفعل 🟢" if config["filter_by_target"] else "معطل ⚪"
        view = TargetItemsView()
        embed = build_target_items_embed()
        await interaction.response.edit_message(content=f"⚙️ وضع الحصر بالسكنات المطلوبة أصبح: **{status}**", embed=embed, view=view)

    @discord.ui.button(label="Clear All 🗑️", style=discord.ButtonStyle.danger, row=4, custom_id="tgt_btn_clear")
    async def btn_clear_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can modify targets.", ephemeral=True)
            return

        config["target_items"] = []
        config["filter_by_target"] = False
        save_config(config)
        view = TargetItemsView()
        embed = build_target_items_embed()
        await interaction.response.edit_message(content="🗑️ تم مسح جميع العناصر والعودة للبحث العام.", embed=embed, view=view)

    @discord.ui.button(label="كتابة يدوية ✍️", style=discord.ButtonStyle.secondary, row=4, custom_id="tgt_btn_manual")
    async def btn_manual_input(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can modify targets.", ephemeral=True)
            return
        modal = TargetItemsModal(config.get("target_items", []))
        await interaction.response.send_modal(modal)


async def perform_mass_verification(guild: discord.Guild) -> Tuple[int, int, int, Optional[str]]:
    """
    Mass verifies all past image uploaders in the proof channel:
    - Adds ✅ reaction to proof messages
    - Grants subscriber role to users who uploaded images
    Returns (checked_msgs, reactions_added, roles_granted, error_message)
    """
    proof_chan_id = config.get("proof_channel_id")
    proof_role_id = config.get("proof_role_id")

    if not proof_chan_id:
        return 0, 0, 0, "Proof channel is not configured! Use `!proof_channel` first."
    if not proof_role_id:
        return 0, 0, 0, "Subscriber role is not configured! Use `!proof_role @role` first."

    role = guild.get_role(int(proof_role_id))
    if not role:
        return 0, 0, 0, f"Subscriber role ID `{proof_role_id}` not found on this server."

    channel = guild.get_channel(int(proof_chan_id))
    if not channel:
        try:
            channel = await bot.fetch_channel(int(proof_chan_id))
        except Exception:
            channel = None
    if not channel:
        return 0, 0, 0, f"Proof channel ID `{proof_chan_id}` could not be found."

    checked_msgs = 0
    reactions_added = 0
    roles_granted = 0
    processed_users = set()

    # 1. Scan channel history
    seen_images = load_seen_images()
    seen_hashes = {x.get("sha256") for x in seen_images if x.get("sha256")}

    try:
        async for msg in channel.history(limit=500):
            if msg.author.bot:
                continue
            has_image = bool(
                msg.attachments and any(
                    (a.content_type and a.content_type.startswith("image/")) or
                    a.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
                    for a in msg.attachments
                )
            )
            if has_image:
                checked_msgs += 1
                # React with ✅ if not already reacted
                has_check = any(r.emoji == "✅" and r.me for r in msg.reactions)
                if not has_check:
                    try:
                        await msg.add_reaction("✅")
                        reactions_added += 1
                    except Exception:
                        pass

                # Index image fingerprint if not in database
                for att in msg.attachments:
                    if att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        try:
                            att_data = await att.read()
                            _, _, att_text = verify_proof_screenshot(att_data)
                            att_fp = calculate_image_hashes(att_data, ocr_text=att_text)
                            if att_fp.get("sha256") and att_fp["sha256"] not in seen_hashes:
                                seen_hashes.add(att_fp["sha256"])
                                seen_images.append({
                                    "user_id": msg.author.id,
                                    "user_name": str(msg.author),
                                    "timestamp": msg.created_at.isoformat(),
                                    "filename": att.filename,
                                    **att_fp
                                })
                        except Exception:
                            pass

                # Grant role to author if missing
                if msg.author.id not in processed_users:
                    processed_users.add(msg.author.id)
                    member = guild.get_member(msg.author.id)
                    if not member:
                        try:
                            member = await guild.fetch_member(msg.author.id)
                        except Exception:
                            member = None
                    if member and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Mass verification of past proofs")
                            roles_granted += 1
                        except Exception as e:
                            print(f"[MassVerify] Error adding role to {member}: {e}")
    except Exception as e:
        print(f"[MassVerify] Error reading channel history: {e}")

    save_seen_images(seen_images)

    # 2. Also ensure all members already in seen_images.json have the role
    seen_images = load_seen_images()
    for entry in seen_images:
        uid = entry.get("user_id")
        if uid and uid not in processed_users:
            processed_users.add(uid)
            member = guild.get_member(uid)
            if not member:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None
            if member and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Mass verification from verified database")
                    roles_granted += 1
                except Exception as e:
                    print(f"[MassVerify] Error adding role to {member}: {e}")

    return checked_msgs, reactions_added, roles_granted, None


class ControlPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.sync_button_styles()

    def sync_button_styles(self):
        is_running = config.get("is_running", True)
        if is_running:
            self.btn_toggle.label = "Stop Tracker 🛑"
            self.btn_toggle.style = discord.ButtonStyle.danger
        else:
            self.btn_toggle.label = "Start Tracker 🟢"
            self.btn_toggle.style = discord.ButtonStyle.success

        if config.get("filter_by_target", False):
            self.btn_toggle_target.label = "Target Only: ON 🎯"
            self.btn_toggle_target.style = discord.ButtonStyle.success
        else:
            self.btn_toggle_target.label = "Target Only: OFF ⚪"
            self.btn_toggle_target.style = discord.ButtonStyle.secondary

    @discord.ui.button(label="Start Tracker 🟢", style=discord.ButtonStyle.success, row=0, custom_id="panel_btn_toggle")
    async def btn_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** This bot is private and restricted to authorized bot owners only.", ephemeral=True)
            return

        global config
        new_state = not config.get("is_running", True)
        config["is_running"] = new_state
        save_config(config)

        if new_state:
            if not tracker_task.is_running():
                tracker_task.start()
        else:
            if tracker_task.is_running():
                tracker_task.stop()

        self.sync_button_styles()
        embed = build_panel_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Scan Market Now 🔍", style=discord.ButtonStyle.primary, row=0, custom_id="panel_btn_check")
    async def btn_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not is_bot_owner(interaction.user.id):
            await interaction.followup.send("⛔ **Access Denied:** This bot is private and restricted to authorized bot owners only.", ephemeral=True)
            return

        try:
            channel = interaction.channel
            sent = await check_and_alert_accounts(channel, is_manual=True)
            if sent > 0:
                await interaction.followup.send(f"✅ Scan completed! Sent {sent} deals in the channel.", ephemeral=True)
            else:
                await interaction.followup.send("ℹ️ Scan completed. No new deals currently match your filters.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Scan error: {e}", ephemeral=True)

    @discord.ui.button(label="Refresh Panel 🔄", style=discord.ButtonStyle.secondary, row=0, custom_id="panel_btn_refresh")
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** This bot is private and restricted to authorized bot owners only.", ephemeral=True)
            return

        self.sync_button_styles()
        embed = build_panel_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Set Interval ⏱️", style=discord.ButtonStyle.secondary, row=1, custom_id="panel_btn_interval")
    async def btn_interval(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** This bot is private and restricted to authorized bot owners only.", ephemeral=True)
            return
        modal = IntervalModal(config.get("interval_minutes", 30))
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Filters ⚙️", style=discord.ButtonStyle.secondary, row=1, custom_id="panel_btn_filters")
    async def btn_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** This bot is private and restricted to authorized bot owners only.", ephemeral=True)
            return
        modal = FiltersModal(
            config.get("min_skins", 20),
            config.get("max_price", 50),
            config.get("profit_amount", 10.0),
            config.get("daybreak", 0)
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Target Items 🎯", style=discord.ButtonStyle.primary, row=1, custom_id="panel_btn_target_items")
    async def btn_target_items(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** This bot is private and restricted to authorized bot owners only.", ephemeral=True)
            return
        view = TargetItemsView()
        embed = build_target_items_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Target Only: OFF ⚪", style=discord.ButtonStyle.secondary, row=1, custom_id="panel_btn_toggle_target")
    async def btn_toggle_target(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bot_owner(interaction.user.id):
            await interaction.response.send_message("⛔ **Access Denied:** This bot is private and restricted to authorized bot owners only.", ephemeral=True)
            return

        global config
        new_filter_state = not config.get("filter_by_target", False)
        if new_filter_state and not config.get("target_items"):
            await interaction.response.send_message(
                "⚠️ You haven't set any target items yet! Please click 'Target Items 🎯' first.",
                ephemeral=True
            )
            return

        config["filter_by_target"] = new_filter_state
        save_config(config)
        self.sync_button_styles()
        embed = build_panel_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Verify Past Uploaders 🎖️", style=discord.ButtonStyle.success, row=2, custom_id="panel_btn_verify_past")
    async def btn_verify_past(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not is_bot_owner(interaction.user.id):
            await interaction.followup.send("⛔ **Access Denied:** This bot is private and restricted to authorized bot owners only.", ephemeral=True)
            return

        try:
            checked, reacted, roles, err = await perform_mass_verification(interaction.guild)
            if err:
                await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
                return

            role = interaction.guild.get_role(int(config.get("proof_role_id")))
            role_name = role.name if role else "Subscriber"
            await interaction.followup.send(
                f"✅ **Mass Proof Verification Complete!**\n\n"
                f"• 📸 Proof messages found: **{checked}**\n"
                f"• ✔️ Checkmarks (`✅`) added: **{reacted}**\n"
                f"• 🎖️ **@{role_name}** granted to: **{roles} members**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"⚠️ Verification error: {e}", ephemeral=True)


# ==========================================
# Slash Commands
# ==========================================

@bot.tree.command(name="start", description="Start automated Fortnite account tracking from Supplier")
@app_commands.default_permissions(administrator=True)
async def slash_start(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    config["is_running"] = True
    save_config(config)
    
    if not tracker_task.is_running():
        tracker_task.start()
    
    channel_mention = f"<#{config['channel_id']}>" if config.get("channel_id") else "No channel configured yet (use /set_channel)"
    interval = config.get("interval_minutes", 30)
    
    embed = discord.Embed(
        title="✅ Automated Tracking Started",
        description=f"The bot will now scan the Supplier for top Fortnite deals every **{interval} minutes**.\n\n📍 **Target Channel:** {channel_mention}",
        color=0x00FF7F
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="stop", description="Pause automated tracking")
@app_commands.default_permissions(administrator=True)
async def slash_stop(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    config["is_running"] = False
    save_config(config)
    
    if tracker_task.is_running():
        tracker_task.stop()

    embed = discord.Embed(
        title="🛑 Automated Tracking Paused",
        description="Market scanning has been paused. You can resume anytime using `/start`.",
        color=0xFF6347
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="check_now", description="Scan the market immediately and send the best deals")
@app_commands.default_permissions(administrator=True)
async def slash_check_now(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    channel = interaction.channel
    
    sent = await check_and_alert_accounts(channel, is_manual=True)
    if sent > 0:
        await interaction.followup.send(f"✅ Scan complete! Sent **{sent}** deals.")
    else:
        await interaction.followup.send("✅ Scan complete. No new deals currently match your filters.")


@bot.tree.command(name="set_interval", description="Set scan interval in minutes (5 or more)")
@app_commands.describe(minutes="Duration in minutes (e.g. 15, 30, 60)")
@app_commands.default_permissions(administrator=True)
async def slash_set_interval(interaction: discord.Interaction, minutes: int):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    if minutes < 5:
        await interaction.response.send_message("⚠️ Minimum allowed interval is 5 minutes to avoid rate limits.", ephemeral=True)
        return

    config["interval_minutes"] = minutes
    save_config(config)
    update_tracker_interval(minutes)

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"Fortnite deals every {minutes}m 🔍"
        )
    )

    embed = discord.Embed(
        title="⏱️ Scan Interval Updated",
        description=f"The bot will now scan for Fortnite deals every **{minutes} minutes**.",
        color=0x1E90FF
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="set_channel", description="Set channel where deals are posted")
@app_commands.describe(channel="Channel for deal alerts (leave blank for current channel)")
@app_commands.default_permissions(administrator=True)
async def slash_set_channel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    target_channel = channel or interaction.channel
    config["channel_id"] = target_channel.id
    save_config(config)

    embed = discord.Embed(
        title="📍 Deals Channel Configured",
        description=f"All Fortnite deals will now be posted in: {target_channel.mention}",
        color=0x00FF7F
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="set_filters", description="Configure account search filters (Price, Skins, Currency, PSN, Inactivity)")
@app_commands.describe(
    min_skins="Minimum skins count (default: 20)",
    max_price="Maximum account price (default: 50)",
    min_price="Minimum account price (default: 1)",
    currency="Currency: usd, rub, or eur",
    psn_linkable="PlayStation (PSN) linkable requirement",
    inactivity_days="Minimum days since last activity (e.g. 30, 0 = All)"
)
@app_commands.choices(psn_linkable=[
    app_commands.Choice(name="Yes (PSN Linkable Only ✅)", value="yes"),
    app_commands.Choice(name="No (Not PSN Linkable ❌)", value="no"),
    app_commands.Choice(name="All (No restriction 🌐)", value="nomatter")
])
@app_commands.default_permissions(administrator=True)
async def slash_set_filters(
    interaction: discord.Interaction,
    min_skins: Optional[int] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    currency: Optional[str] = None,
    psn_linkable: Optional[app_commands.Choice[str]] = None,
    inactivity_days: Optional[int] = None
):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    if min_skins is not None:
        config["min_skins"] = max(0, min_skins)
    if max_price is not None:
        config["max_price"] = max(1.0, max_price)
    if min_price is not None:
        config["min_price"] = max(0.0, min_price)
    if inactivity_days is not None:
        config["daybreak"] = max(0, inactivity_days)
    if currency is not None:
        curr = currency.lower().strip()
        if curr in ["usd", "rub", "eur"]:
            config["currency"] = curr
        else:
            await interaction.response.send_message("⚠️ Currency must be usd, rub, or eur.", ephemeral=True)
            return
    if psn_linkable is not None:
        config["psn_linkable"] = psn_linkable.value

    save_config(config)

    curr_symbol = "$" if config.get("currency") == "usd" else config.get("currency").upper()
    psn_display = "PSN Linkable Only ✅" if config.get("psn_linkable") == "yes" else ("Not PSN Linkable ❌" if config.get("psn_linkable") == "no" else "All 🌐")
    daybreak_val = config.get("daybreak", 0)
    daybreak_display = f"{daybreak_val}+ days inactive ⏳" if daybreak_val > 0 else "All (Any activity)"
    embed = discord.Embed(
        title="⚙️ Search Filters Updated",
        description=(
            f"• **Min Skins:** {config['min_skins']} Skins\n"
            f"• **Price Range:** {config['min_price']}{curr_symbol} - {config['max_price']}{curr_symbol}\n"
            f"• **PlayStation (PSN):** {psn_display}\n"
            f"• **Inactivity Filter:** {daybreak_display}\n"
            f"• **Currency:** {config['currency'].upper()}"
        ),
        color=0xFFD700
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="set_token", description="Update the Supplier API token")
@app_commands.describe(token="Supplier API token")
@app_commands.default_permissions(administrator=True)
async def slash_set_token(interaction: discord.Interaction, token: str):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    clean_token = token.strip()
    lzt_client.set_token(clean_token)
    
    # Update .env file
    try:
        env_lines = []
        token_found = False
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                env_lines = f.readlines()
        
        new_lines = []
        for line in env_lines:
            if line.startswith("LZT_API_TOKEN="):
                new_lines.append(f"LZT_API_TOKEN={clean_token}\n")
                token_found = True
            else:
                new_lines.append(line)
        if not token_found:
            new_lines.append(f"LZT_API_TOKEN={clean_token}\n")
        
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        await interaction.response.send_message("🔑 **Supplier API token saved successfully!**", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"⚠️ Token updated in memory, but error saving to .env: {e}", ephemeral=True)


@bot.tree.command(name="set_proof_channel", description="Set the subscription proof verification channel")
@app_commands.describe(channel="Channel for screenshots (leave blank for current channel)")
@app_commands.default_permissions(administrator=True)
async def slash_set_proof_channel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    target_channel = channel or interaction.channel
    config["proof_channel_id"] = target_channel.id
    save_config(config)

    embed = discord.Embed(
        title="📸 Proof Channel Configured",
        description=(
            f"Proof channel set to: {target_channel.mention}\n\n"
            "✨ When members upload a screenshot here:\n"
            "1. OCR will verify that it shows genuine subscription/like status.\n"
            "2. Duplicate screenshots will be detected and rejected.\n"
            "3. Verified members automatically receive the subscriber role!"
        ),
        color=0x00FF7F
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="set_proof_role", description="Set the subscriber role automatically granted upon proof verification")
@app_commands.describe(role="Role to grant verified subscribers")
@app_commands.default_permissions(administrator=True)
async def slash_set_proof_role(interaction: discord.Interaction, role: discord.Role):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    config["proof_role_id"] = role.id
    save_config(config)

    embed = discord.Embed(
        title="🎖️ Subscriber Role Configured",
        description=f"Verified members will now automatically receive: {role.mention}",
        color=0xFFD700
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="set_profit", description="Set the profit added on top of Supplier price for server listings")
@app_commands.describe(amount="Profit amount in dollars or store currency (e.g. 10 or 15)")
@app_commands.default_permissions(administrator=True)
async def slash_set_profit(interaction: discord.Interaction, amount: float):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    if amount < 0:
        await interaction.response.send_message("⚠️ Profit amount cannot be negative.", ephemeral=True)
        return
    config["profit_amount"] = round(amount, 2)
    save_config(config)
    curr_symbol = "$" if config.get("currency") == "usd" else config.get("currency").upper()
    embed = discord.Embed(
        title="💰 Profit Margin Configured",
        description=f"**+{config['profit_amount']} {curr_symbol}** will automatically be added to the account's original price.\n(Public Customer Price = Supplier Price + Added Profit)",
        color=0x00FF7F
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="set_inactivity", description="Set minimum inactivity days for accounts (Last Activity / Inactive)")
@app_commands.describe(days="Minimum inactivity days (e.g. 30, 60, or 0 for All)")
@app_commands.default_permissions(administrator=True)
async def slash_set_inactivity(interaction: discord.Interaction, days: int):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can control this bot.", ephemeral=True)
        return
    global config
    config["daybreak"] = max(0, days)
    save_config(config)
    txt = "All accounts (Any activity) 🌐" if days <= 0 else f"Accounts inactive for **{days}+ days** ⏳"
    embed = discord.Embed(
        title="⏳ Inactivity Filter Updated",
        description=f"Scanning will now target: **{txt}**",
        color=0x00CED1
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="panel", description="Open the interactive Control Panel")
@app_commands.default_permissions(administrator=True)
async def slash_panel(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can open the control panel.", ephemeral=True)
        return
    embed = build_panel_embed()
    view = ControlPanelView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="verify_past_proofs", description="Verify all past proof uploaders, add checkmark reaction, and grant role")
@app_commands.default_permissions(administrator=True)
async def slash_verify_past_proofs(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can use this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    checked, reacted, roles, err = await perform_mass_verification(interaction.guild)
    if err:
        await interaction.followup.send(f"⚠️ {err}", ephemeral=True)
        return
    role = interaction.guild.get_role(int(config.get("proof_role_id")))
    role_name = role.name if role else "Subscriber"
    await interaction.followup.send(
        f"✅ **Mass Proof Verification Complete!**\n\n"
        f"• 📸 Proof messages found: **{checked}**\n"
        f"• ✔️ Checkmarks (`✅`) added: **{reacted}**\n"
        f"• 🎖️ **@{role_name}** granted to: **{roles} members**",
        ephemeral=True
    )


async def cosmetic_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    cat = None
    if hasattr(interaction, "namespace") and hasattr(interaction.namespace, "category"):
        raw_cat = interaction.namespace.category
        if raw_cat in ["skin", "pickaxe", "dance"]:
            cat = raw_cat
    matches = FortniteCosmetics.search(current, category=cat, limit=25)
    return [
        app_commands.Choice(name=m.get("label", m["name"])[:100], value=m["name"][:100])
        for m in matches
    ]

async def current_targets_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    targets = config.get("target_items", [])
    q = current.lower().strip()
    filtered = [t for t in targets if q in t.lower()] if q else targets
    return [
        app_commands.Choice(name=f"🎯 {t}"[:100], value=t[:100])
        for t in filtered[:25]
    ]


@bot.tree.command(name="add_target", description="Add a skin, pickaxe, or dance/emote to your target items list (Live Search)")
@app_commands.describe(
    item="Type name to search (e.g. trav, black, axe, floss)",
    category="Filter by type (optional)"
)
@app_commands.choices(category=[
    app_commands.Choice(name="All Types 🌐", value="all"),
    app_commands.Choice(name="Skins / Characters 👕", value="skin"),
    app_commands.Choice(name="Pickaxes ⛏️", value="pickaxe"),
    app_commands.Choice(name="Dances & Emotes 💃", value="dance"),
])
@app_commands.autocomplete(item=cosmetic_autocomplete)
@app_commands.default_permissions(administrator=True)
async def slash_add_target(
    interaction: discord.Interaction,
    item: str,
    category: Optional[app_commands.Choice[str]] = None
):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can use this command.", ephemeral=True)
        return

    global config
    targets = list(config.get("target_items", []))
    clean_item = item.strip()
    if clean_item not in targets:
        targets.append(clean_item)
        config["target_items"] = targets
        save_config(config)

    mode_text = "Strict Target Only 🎯 (Only accounts with these items)" if config.get("filter_by_target") else "General Search 🌐 (Use `/toggle_target_filter` to strictly require targets)"
    embed = discord.Embed(
        title="🎯 Target Item Added!",
        description=(
            f"Added item: **`{clean_item}`**\n\n"
            f"• **Active Target Items ({len(targets)}):**\n{', '.join([f'`{t}`' for t in targets])}\n\n"
            f"• **Search Mode:** {mode_text}"
        ),
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="remove_target", description="Remove a cosmetic item from your target items list")
@app_commands.describe(item="Choose target item to remove")
@app_commands.autocomplete(item=current_targets_autocomplete)
@app_commands.default_permissions(administrator=True)
async def slash_remove_target(interaction: discord.Interaction, item: str):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can use this command.", ephemeral=True)
        return

    global config
    targets = list(config.get("target_items", []))
    clean_item = item.strip()
    if clean_item in targets:
        targets.remove(clean_item)
        config["target_items"] = targets
        save_config(config)
        embed = discord.Embed(
            title="🗑️ Target Item Removed",
            description=f"Removed: **`{clean_item}`**\n\nRemaining ({len(targets)}): {', '.join([f'`{t}`' for t in targets]) if targets else 'None (Empty)'}",
            color=0xE74C3C
        )
    else:
        embed = discord.Embed(
            title="⚠️ Item Not Found",
            description=f"`{clean_item}` was not found in your target items list.",
            color=0xF39C12
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="list_targets", description="View all currently active target items and filter status")
@app_commands.default_permissions(administrator=True)
async def slash_list_targets(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can use this command.", ephemeral=True)
        return

    targets = config.get("target_items", [])
    filter_mode = config.get("filter_by_target", False)
    embed = discord.Embed(
        title="🎯 Active Target Items",
        description=(
            f"• **Total Configured:** `{len(targets)}` items\n"
            f"• **Filter Mode:** `{'Strict Target Only 🎯' if filter_mode else 'General Search with Highlights 🌐'}`\n\n"
            f"**Items List:**\n{', '.join([f'`{t}`' for t in targets]) if targets else '*No targets configured yet. Use `/add_target` to add items.*'}"
        ),
        color=0x9B59B6
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="set_target_items", description="Set custom skins or items to highlight (side option)")
@app_commands.describe(items="Skins or items separated by comma (e.g. Travis Scott, Black Knight, Minty)")
@app_commands.autocomplete(items=cosmetic_autocomplete)
@app_commands.default_permissions(administrator=True)
async def slash_set_target_items(interaction: discord.Interaction, items: str):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can use this command.", ephemeral=True)
        return
    global config
    items_list = [i.strip() for i in items.split(",") if i.strip()]
    config["target_items"] = items_list
    save_config(config)
    embed = discord.Embed(
        title="🎯 Target Items Saved",
        description=(
            f"Saved target items:\n**{', '.join(items_list)}**\n\n"
            f"• **Filter Mode:** {'Strict Target Only 🎯' if config.get('filter_by_target') else 'General Search with Highlights 🌐'}"
        ),
        color=0x9B59B6
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="toggle_target_filter", description="Toggle between strict target-only mode and general search mode")
@app_commands.default_permissions(administrator=True)
async def slash_toggle_target_filter(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can use this command.", ephemeral=True)
        return
    global config
    if not config.get("target_items") and not config.get("filter_by_target"):
        await interaction.response.send_message("⚠️ No target items set yet! Use `/set_target_items` first.", ephemeral=True)
        return
    
    config["filter_by_target"] = not config.get("filter_by_target", False)
    save_config(config)
    
    if config["filter_by_target"]:
        embed = discord.Embed(
            title="🎯 Strict Target Match Enabled",
            description=f"The bot will only alert on accounts that contain your target items:\n**{', '.join(config.get('target_items', []))}**",
            color=0x00FF7F
        )
    else:
        embed = discord.Embed(
            title="🌐 General Search Mode Enabled",
            description="The bot will search all top Fortnite deals generally and highlight your target items if found.",
            color=0x1E90FF
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="clear_target_items", description="Clear all custom target items and return to general search")
@app_commands.default_permissions(administrator=True)
async def slash_clear_target_items(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can use this command.", ephemeral=True)
        return
    global config
    config["target_items"] = []
    config["filter_by_target"] = False
    save_config(config)
    embed = discord.Embed(
        title="🗑️ Target Items Cleared",
        description="Custom target items cleared. Bot returned to general search mode.",
        color=0x7289DA
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="status", description="Display current bot configuration and status")
@app_commands.default_permissions(administrator=True)
async def slash_status(interaction: discord.Interaction):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can view bot status.", ephemeral=True)
        return
    channel_mention = f"<#{config['channel_id']}>" if config.get("channel_id") else "❌ Not configured"
    proof_channel_mention = f"<#{config['proof_channel_id']}>" if config.get("proof_channel_id") else "❌ Not configured"
    proof_role_mention = f"<@&{config['proof_role_id']}>" if config.get("proof_role_id") else "❌ Not configured"
    status_str = "🟢 Active" if config.get("is_running") and tracker_task.is_running() else "🔴 Stopped"
    has_token = "✅ Connected" if lzt_client.api_token else "❌ Not configured (/set_token)"
    seen_count = len(load_seen_accounts())
    seen_images_count = len(load_seen_images())
    curr_symbol = "$" if config.get("currency") == "usd" else config.get("currency").upper()
    profit_amt = config.get("profit_amount", 10.0)

    target_items = config.get("target_items", [])
    filter_by_target = config.get("filter_by_target", False)
    target_str = ", ".join(target_items) if target_items else "None (General search)"
    target_mode_str = "Strict Target Only 🎯" if filter_by_target else "General Search 🌐"

    psn_text = "All (No restriction)"
    if config.get("psn_linkable") == "yes":
        psn_text = "PSN Linkable Only ✅"
    elif config.get("psn_linkable") == "no":
        psn_text = "Not PSN Linkable ❌"

    daybreak_val = config.get("daybreak", 0)
    daybreak_str = f"**{daybreak_val}+ days** (Inactive)" if daybreak_val > 0 else "All (Any activity)"

    embed = discord.Embed(
        title="📊 Fortnite Bot Status & Settings",
        color=0x7289DA,
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="Supplier Tracker Status", value=status_str, inline=True)
    embed.add_field(name="Scan Interval", value=f"Every **{config.get('interval_minutes', 30)}** mins", inline=True)
    embed.add_field(name="Deals Channel", value=channel_mention, inline=True)
    embed.add_field(name="💰 Added Profit", value=f"**+{profit_amt} {curr_symbol}**", inline=True)
    embed.add_field(name="🔒 Private DMs Delivery", value="Authorized Owners Only (`recipients.txt`)", inline=True)
    embed.add_field(name="Supplier API Token", value=has_token, inline=True)
    embed.add_field(name="Price Range", value=f"{config.get('min_price')}{curr_symbol} - {config.get('max_price')}{curr_symbol}", inline=True)
    embed.add_field(name="Min Skins", value=f"{config.get('min_skins')} Skins", inline=True)
    embed.add_field(name="⏳ Inactivity Filter", value=daybreak_str, inline=True)
    embed.add_field(name="🎮 PlayStation (PSN)", value=psn_text, inline=True)
    embed.add_field(name="🎯 Target Items", value=f"`{target_str[:80]}`", inline=True)
    embed.add_field(name="⚙️ Target Filter Mode", value=target_mode_str, inline=True)
    embed.add_field(name="📸 Proof Channel", value=proof_channel_mention, inline=True)
    embed.add_field(name="🎖️ Subscriber Role", value=proof_role_mention, inline=True)
    embed.add_field(name="🛡️ Verified Proofs", value=f"{seen_images_count} images", inline=True)
    embed.add_field(name="🎨 Graphics Branding", value=f"**{config.get('store_name', 'VENTO')}**", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="set_branding", description="Set custom store / brand name for locker showcase graphics")
@app_commands.describe(name="Your store or brand name (e.g. VENTO, Apex Store)")
@commands.has_permissions(administrator=True)
async def slash_set_branding(interaction: discord.Interaction, name: str):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can change branding.", ephemeral=True)
        return
    clean_name = name.strip()
    if not clean_name:
        await interaction.response.send_message("⚠️ Please provide a valid brand name.", ephemeral=True)
        return
    config["store_name"] = clean_name
    save_config(config)
    await interaction.response.send_message(f"🎨 Showcase graphics branding updated to: **{clean_name}**!", ephemeral=True)



@bot.tree.command(name="help", description="Commands guide and instructions")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Fortnite Deals & Verification Bot - Command Guide",
        description=(
            "**🎛️ Interactive Control Panel:**\n"
            "• `/panel` : Open the interactive control panel (Authorized Owners Only).\n\n"
            "**🔒 Private Deals Delivery:**\n"
            "• Direct purchase links are sent in private DM strictly to authorized owners (`recipients.txt`).\n"
            "• `/set_profit [amount]` : Set profit amount added to account price (e.g. $10).\n\n"
            "**🎯 Target Skins / Items (Optional):**\n"
            "• `/set_target_items [items]` : Specify skins to search for (e.g. `Travis Scott, Minty`).\n"
            "• `/toggle_target_filter` : Toggle between strict target-only mode and general search.\n"
            "• `/clear_target_items` : Clear target items and return to general search.\n\n"
            "**🔍 Market Automation (Supplier):**\n"
            "• `/set_channel` : Set the channel where deals are posted.\n"
            "• `/set_interval [minutes]` : Set scan interval (e.g. 15, 30, 60 mins).\n"
            "• `/check_now` : Immediate manual market scan.\n"
            "• `/set_inactivity [days]` : Filter by inactivity (e.g. 30 days inactive).\n"
            "• `/set_filters` : Configure all account filters.\n"
            "• `/start` / `/stop` : Start or pause automatic scanning.\n"
            "• `/status` : View detailed bot configuration.\n"
            "• `/set_token` : Update Supplier API token.\n\n"
            "**📸 Proof & Subscriber Verification:**\n"
            "• `/set_proof_channel` : Set the channel where members upload subscription screenshots.\n"
            "• `/set_proof_role` : Set the role automatically awarded upon OCR verification.\n\n"
            "💡 Prefix commands (`!panel`, `!inactivity 30`, `!check`, `!status`, etc.) are also available."
        ),
        color=0x00CED1
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
# Prefix Commands Fallback (!)
# ==========================================

@bot.check
async def globally_restrict_to_owners(ctx: commands.Context):
    """Enforce that only authorized bot owners (from recipients.txt) can execute any prefix command."""
    return is_bot_owner(ctx.author.id)

@bot.command(name="check")
@commands.has_permissions(administrator=True)
async def cmd_check(ctx: commands.Context):
    """Immediate manual check."""
    msg = await ctx.send("🔍 Checking Fortnite accounts from Supplier...")
    sent = await check_and_alert_accounts(ctx.channel, is_manual=True)
    if sent > 0:
        await msg.edit(content=f"✅ Scan completed! Sent **{sent}** deals above.")
    else:
        await msg.edit(content="✅ Scan completed. No new accounts currently match your filters.")

@bot.command(name="start")
@commands.has_permissions(administrator=True)
async def cmd_start(ctx: commands.Context):
    global config
    config["is_running"] = True
    save_config(config)
    if not tracker_task.is_running():
        tracker_task.start()
    await ctx.send(f"✅ Automatic tracker started! Scanning every **{config.get('interval_minutes', 30)} minutes**.")

@bot.command(name="stop")
@commands.has_permissions(administrator=True)
async def cmd_stop(ctx: commands.Context):
    global config
    config["is_running"] = False
    save_config(config)
    if tracker_task.is_running():
        tracker_task.stop()
    await ctx.send("🛑 Automatic tracker has been paused.")

@bot.command(name="interval")
@commands.has_permissions(administrator=True)
async def cmd_interval(ctx: commands.Context, minutes: int):
    global config
    if minutes < 5:
        await ctx.send("⚠️ Minimum allowed interval is 5 minutes.")
        return
    config["interval_minutes"] = minutes
    save_config(config)
    update_tracker_interval(minutes)
    await ctx.send(f"⏱️ Scan interval updated to every **{minutes} minutes**!")

@bot.command(name="channel")
@commands.has_permissions(administrator=True)
async def cmd_channel(ctx: commands.Context):
    global config
    config["channel_id"] = ctx.channel.id
    save_config(config)
    await ctx.send(f"📍 Channel {ctx.channel.mention} set for deals alerts!")

@bot.command(name="proof_channel")
@commands.has_permissions(administrator=True)
async def cmd_proof_channel(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    global config
    target_channel = channel or ctx.channel
    config["proof_channel_id"] = target_channel.id
    save_config(config)
    await ctx.send(f"📸 Channel {target_channel.mention} set for subscriber proof verification!")

@bot.command(name="proof_role")
@commands.has_permissions(administrator=True)
async def cmd_proof_role(ctx: commands.Context, role: discord.Role):
    global config
    config["proof_role_id"] = role.id
    save_config(config)
    await ctx.send(f"🎖️ Role {role.mention} set to be awarded automatically upon verification!")

@bot.command(name="profit")
@commands.has_permissions(administrator=True)
async def cmd_profit(ctx: commands.Context, amount: float):
    global config
    if amount < 0:
        await ctx.send("⚠️ Profit amount cannot be negative.")
        return
    config["profit_amount"] = round(amount, 2)
    save_config(config)
    curr_symbol = "$" if config.get("currency") == "usd" else config.get("currency", "usd").upper()
    await ctx.send(f"💰 Added profit margin set to **+{config['profit_amount']} {curr_symbol}**!")

@bot.command(name="add_target")
@commands.has_permissions(administrator=True)
async def cmd_add_target(ctx: commands.Context, *, item: str):
    if not is_bot_owner(ctx.author.id):
        await ctx.send("⛔ **Access Denied:** Only authorized bot owners can use this command.")
        return
    global config
    targets = list(config.get("target_items", []))
    clean_item = item.strip()
    if clean_item not in targets:
        targets.append(clean_item)
        config["target_items"] = targets
        save_config(config)
    await ctx.send(f"🎯 Added **{clean_item}** to target items!\nTotal targets ({len(targets)}): `{', '.join(targets)}`")

@bot.tree.command(name="set_account_title", description="Set the fixed static title for all posted Fortnite accounts")
@app_commands.describe(title="Fixed title for all accounts (e.g. 🎮 Fortnite Special Account)")
@app_commands.default_permissions(administrator=True)
async def slash_set_account_title(interaction: discord.Interaction, title: str):
    if not is_bot_owner(interaction.user.id):
        await interaction.response.send_message("⛔ **Access Denied:** Only authorized bot owners can use this command.", ephemeral=True)
        return
    global config
    config["fixed_account_title"] = title.strip()
    save_config(config)
    await interaction.response.send_message(f"🏷️ تم تعيين العنوان الثابت لجميع الحسابات إلى:\n**{config['fixed_account_title']}**", ephemeral=True)

@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def cmd_sync(ctx: commands.Context):
    if not is_bot_owner(ctx.author.id):
        await ctx.send("⛔ **Access Denied:** Only authorized bot owners can use this command.")
        return
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"⚡ تم تحديث ومزامنة **{len(synced)}** أمر سلاش فورياً مع هذا السيرفر!")
    except Exception as e:
        await ctx.send(f"⚠️ خطأ أثناء المزامنة: {e}")

@bot.command(name="set_title")
@commands.has_permissions(administrator=True)
async def cmd_set_title(ctx: commands.Context, *, new_title: str):
    if not is_bot_owner(ctx.author.id):
        await ctx.send("⛔ **Access Denied:** Only authorized bot owners can use this command.")
        return
    global config
    config["fixed_account_title"] = new_title.strip()
    save_config(config)
    await ctx.send(f"🏷️ تم تعيين العنوان الثابت لجميع الحسابات إلى:\n**{config['fixed_account_title']}**")

@bot.command(name="remove_target")
@commands.has_permissions(administrator=True)
async def cmd_remove_target(ctx: commands.Context, *, item: str):
    if not is_bot_owner(ctx.author.id):
        await ctx.send("⛔ **Access Denied:** Only authorized bot owners can use this command.")
        return
    global config
    targets = list(config.get("target_items", []))
    clean_item = item.strip()
    if clean_item in targets:
        targets.remove(clean_item)
        config["target_items"] = targets
        save_config(config)
        await ctx.send(f"🗑️ Removed **{clean_item}** from target items!\nRemaining: `{', '.join(targets)}`")
    else:
        await ctx.send(f"⚠️ `{clean_item}` was not found in target items.")

@bot.command(name="targets")
@commands.has_permissions(administrator=True)
async def cmd_targets(ctx: commands.Context, *, items: str):
    if not is_bot_owner(ctx.author.id):
        await ctx.send("⛔ **Access Denied:** Only authorized bot owners can use this command.")
        return
    global config
    items_list = [i.strip() for i in items.split(",") if i.strip()]
    config["target_items"] = items_list
    save_config(config)
    await ctx.send(f"🎯 Target items set to: **{', '.join(items_list)}**\n(Use `!toggle_targets` to switch between target-only filtering and general search)")

@bot.command(name="toggle_targets")
@commands.has_permissions(administrator=True)
async def cmd_toggle_targets(ctx: commands.Context):
    global config
    if not config.get("target_items") and not config.get("filter_by_target"):
        await ctx.send("⚠️ No target items configured! Use `!targets Item1, Item2` first.")
        return
    config["filter_by_target"] = not config.get("filter_by_target", False)
    save_config(config)
    mode_text = "Target Items Only 🎯" if config["filter_by_target"] else "General Search with Highlights 🌐"
    await ctx.send(f"⚙️ Target filter mode changed to: **{mode_text}**")

@bot.command(name="clear_targets")
@commands.has_permissions(administrator=True)
async def cmd_clear_targets(ctx: commands.Context):
    global config
    config["target_items"] = []
    config["filter_by_target"] = False
    save_config(config)
    await ctx.send("🗑️ Target items cleared. Returning to default search.")

@bot.command(name="inactivity")
@commands.has_permissions(administrator=True)
async def cmd_inactivity(ctx: commands.Context, days: int):
    global config
    if days < 0:
        await ctx.send("⚠️ Days cannot be negative.")
        return
    config["daybreak"] = days
    save_config(config)
    daybreak_str = f"**{days}+ days inactive**" if days > 0 else "**Any activity** (no inactivity filter)"
    await ctx.send(f"⏳ Inactivity filter set to: {daybreak_str}!")

@bot.command(name="branding", aliases=["store_name"])
@commands.has_permissions(administrator=True)
async def cmd_branding(ctx: commands.Context, *, name: str):
    clean_name = name.strip()
    if not clean_name:
        await ctx.send("⚠️ Please provide a valid brand name.")
        return
    config["store_name"] = clean_name
    save_config(config)
    await ctx.send(f"🎨 Showcase graphics branding updated to: **{clean_name}**!")

@bot.command(name="status")
@commands.has_permissions(administrator=True)
async def cmd_status(ctx: commands.Context):
    status_str = "🟢 Active" if config.get("is_running") and tracker_task.is_running() else "🔴 Stopped"
    curr_symbol = "$" if config.get("currency") == "usd" else config.get("currency", "usd").upper()
    proof_chan = f"<#{config['proof_channel_id']}>" if config.get("proof_channel_id") else "Not set"
    proof_role = f"<@&{config['proof_role_id']}>" if config.get("proof_role_id") else "Not set"
    profit_str = f"+{config.get('profit_amount', 10.0)} {curr_symbol}"

    daybreak_val = config.get("daybreak", 0)
    daybreak_str = f"{daybreak_val}+ days inactive" if daybreak_val > 0 else "Any activity"

    target_items = config.get("target_items", [])
    filter_by_target = config.get("filter_by_target", False)
    target_str = ", ".join(target_items) if target_items else "None (General Search)"
    target_mode_str = "Target items only 🎯" if filter_by_target else "General 🌐"
    store_branding = config.get("store_name", "VENTO")

    await ctx.send(
        f"📊 **Bot Status:** {status_str} | Interval: **Every {config.get('interval_minutes', 30)}m** | "
        f"Price: Up to **{config.get('max_price')}{curr_symbol}** | Added Profit: **{profit_str}** | Inactivity: **{daybreak_str}**\n"
        f"🎯 **Target Items:** `{target_str}` (Mode: **{target_mode_str}**) | 🎨 **Branding:** `{store_branding}`\n"
        f"🔒 **Private Deals Delivery:** Authorized Owners Only (`recipients.txt`)\n"
        f"📸 **Proof Channel:** {proof_chan} | 🎖️ **Role:** {proof_role}"
    )

@bot.command(name="panel")
@commands.has_permissions(administrator=True)
async def cmd_panel(ctx: commands.Context):
    """Open Interactive Control Panel."""
    try:
        await ctx.message.delete()
    except Exception:
        pass
    embed = build_panel_embed()
    view = ControlPanelView()
    await ctx.send(embed=embed, view=view)

@bot.command(name="verify_all", aliases=["verify_past", "verify_proofs"])
@commands.has_permissions(administrator=True)
async def cmd_verify_all(ctx: commands.Context):
    """Verify all past proof uploaders, add checkmark reaction, and grant role."""
    msg = await ctx.send("⏳ **Scanning proof channel and verifying past uploads...**")
    checked, reacted, roles, err = await perform_mass_verification(ctx.guild)
    if err:
        await msg.edit(content=f"⚠️ {err}")
        return
    role = ctx.guild.get_role(int(config.get("proof_role_id")))
    role_name = role.name if role else "Subscriber"
    await msg.edit(
        content=(
            f"✅ **Mass Proof Verification Complete!**\n\n"
            f"• 📸 Proof messages found: **{checked}**\n"
            f"• ✔️ Checkmarks (`✅`) added: **{reacted}**\n"
            f"• 🎖️ **@{role_name}** granted to: **{roles} members**"
        )
    )

@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    await ctx.send(
        "📖 **Fortnite Bot Commands Guide:**\n"
        "• `!panel` : Open interactive control panel (Owners Only).\n"
        "• `!inactivity <days>` : Filter by account inactivity in days (e.g. `!inactivity 30`).\n"
        "• `!targets <skins>` : Set target items/skins (e.g. `!targets Travis Scott, Minty`).\n"
        "• `!toggle_targets` : Switch between target-only filter and general search.\n"
        "• `!clear_targets` : Clear target items.\n"
        "• `!check` : Immediate market scan.\n"
        "• `!profit <amount>` : Set added profit margin.\n"
        "• `!channel` : Set current channel for deals announcements.\n"
        "• `!interval <minutes>` : Set scan interval (e.g. 15, 30, 60 mins).\n"
        "• `!start` / `!stop` : Start or pause automatic scanner.\n"
        "• `!proof_channel` : Set proof verification channel.\n"
        "• `!proof_role @role` : Set automatic subscriber role.\n"
        "• `!status` : View current configuration.\n"
        "• Or use slash commands: `/panel`, `/set_inactivity`, `/status`, `/help`, etc."
    )

@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CheckFailure):
        return  # Silently ignore commands from unauthorized users across all servers
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ This command is restricted to administrators only!", delete_after=10)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ Missing required argument: `{error.param.name}`. Use `!help` for guidance.", delete_after=10)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"[Command Error] {error}")


def kill_other_bot_instances():
    """Ensure only ONE instance of bot.py runs at any time by terminating older instances."""
    try:
        import psutil
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] != current_pid and proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline') or []
                    if any('bot.py' in str(arg).lower() for arg in cmdline):
                        print(f"[Cleanup] Terminating previous bot instance (PID: {proc.info['pid']})...")
                        proc.terminate()
                        try:
                            proc.wait(timeout=2)
                        except Exception:
                            proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        print(f"[Cleanup] Instance check error: {e}")

# Main Entry Point
def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("\n" + "!" * 60)
        print("WARNING: DISCORD_TOKEN is missing or not set in .env file!")
        print("Please open the .env file, paste your Discord Bot Token, and restart.")
        print("!" * 60 + "\n")
        return

    # Automatically terminate duplicate instances to avoid double responses
    kill_other_bot_instances()

    print("Starting Discord Bot...")
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
