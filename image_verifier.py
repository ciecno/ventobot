import io
import re
import hashlib
from typing import Tuple, Optional, List, Dict, Any
from PIL import Image
import imagehash

def extract_ocr_tokens(text: str) -> List[str]:
    """Extract distinctive text tokens from OCR output to catch stolen screenshots."""
    if not text:
        return []
    words = re.findall(r'[a-zA-Z0-9_\u0600-\u06FF]{3,}', text.lower())
    ignore = {
        'the', 'and', 'for', 'you', 'sub', 'subs', 'subscribed', 'subscribe',
        'subscriber', 'subscribers', 'subscription', 'like', 'liked', 'likes',
        'video', 'channel', 'watch', 'share', 'view', 'views', 'youtube', 'tiktok',
        'instagram', 'twitter', 'posts', 'notifications', 'bell', 'following',
        'followers', 'comment', 'comments', 'مشترك', 'اشتراك', 'مشتركين', 'لايك', 'اعجاب', 'إعجاب'
    }
    return [w for w in set(words) if w not in ignore]

def calculate_image_hashes(image_bytes: bytes, ocr_text: str = "") -> Dict[str, Any]:
    """
    Calculate comprehensive anti-theft fingerprints:
    - sha256 (exact hash)
    - phash, dhash, whash (full perceptual)
    - flip_phash, flip_whash (mirrored)
    - center_whash, center_dhash, center_phash (middle 70% to detect cropped edges/status bars)
    - top_whash, bottom_whash (sub-regions)
    - ocr_tokens (distinctive text tokens)
    """
    try:
        sha256_val = hashlib.sha256(image_bytes).hexdigest()
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size

        phash_val = str(imagehash.phash(img))
        dhash_val = str(imagehash.dhash(img))
        whash_val = str(imagehash.whash(img))

        # Mirrored hashes
        flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
        flip_phash = str(imagehash.phash(flipped))
        flip_whash = str(imagehash.whash(flipped))

        # Center region (catches screenshots where borders/status bars were cropped)
        cw1, ch1 = int(w * 0.15), int(h * 0.15)
        cw2, ch2 = max(cw1 + 10, int(w * 0.85)), max(ch1 + 10, int(h * 0.85))
        center_img = img.crop((cw1, ch1, cw2, ch2))
        center_whash = str(imagehash.whash(center_img))
        center_dhash = str(imagehash.dhash(center_img))
        center_phash = str(imagehash.phash(center_img))

        # Top 60% and Bottom 60%
        top_img = img.crop((0, 0, w, max(10, int(h * 0.6))))
        bottom_img = img.crop((0, max(0, int(h * 0.4)), w, h))
        top_whash = str(imagehash.whash(top_img))
        bottom_whash = str(imagehash.whash(bottom_img))

        ocr_tokens = extract_ocr_tokens(ocr_text)

        return {
            "sha256": sha256_val,
            "phash": phash_val,
            "dhash": dhash_val,
            "whash": whash_val,
            "flip_phash": flip_phash,
            "flip_whash": flip_whash,
            "center_whash": center_whash,
            "center_dhash": center_dhash,
            "center_phash": center_phash,
            "top_whash": top_whash,
            "bottom_whash": bottom_whash,
            "ocr_tokens": ocr_tokens
        }
    except Exception as e:
        print(f"[ImageVerifier] Error computing image fingerprints: {e}")
        return {
            "sha256": hashlib.sha256(image_bytes).hexdigest() if image_bytes else "",
            "phash": "",
            "dhash": "",
            "whash": "",
            "ocr_tokens": []
        }

def check_if_duplicate(
    fp: Dict[str, Any],
    seen_images: List[Dict[str, Any]],
    hamming_threshold: int = 4,
    current_user_id: Optional[int] = None
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Check if the image is a duplicate or stolen version of an existing screenshot.
    Returns (is_duplicate, previous_entry, reason)
    """
    if not fp:
        return False, None, ""

    sha256_val = fp.get("sha256")

    # Pre-parse hash objects for fast comparison
    def safe_hash(h_str):
        if not h_str or h_str in ["0000000000000000", "ffffffffffffffff"]:
            return None
        try:
            return imagehash.hex_to_hash(h_str)
        except Exception:
            return None

    h_phash = safe_hash(fp.get("phash"))
    h_dhash = safe_hash(fp.get("dhash"))
    h_whash = safe_hash(fp.get("whash"))
    h_flip_p = safe_hash(fp.get("flip_phash"))
    h_flip_w = safe_hash(fp.get("flip_whash"))
    h_center_w = safe_hash(fp.get("center_whash"))

    for item in seen_images:
        # Ignore uploads from the same user so a user cannot be accused of stealing their own screenshot
        if current_user_id is not None:
            prev_uid = item.get("user_id")
            if prev_uid and str(prev_uid) == str(current_user_id):
                continue

        # 1. Exact byte SHA-256 match
        if sha256_val and item.get("sha256") == sha256_val:
            return True, item, "Exact image file duplicate"

        # 2. Wavelet / Perceptual full image match (handles compression & minor edits)
        s_whash = safe_hash(item.get("whash"))
        if h_whash and s_whash and (h_whash - s_whash) <= 3:
            return True, item, f"Visual pattern match (Wavelet dist: {h_whash - s_whash})"

        s_phash = safe_hash(item.get("phash"))
        if h_phash and s_phash and (h_phash - s_phash) <= hamming_threshold:
            return True, item, f"Visual appearance match (pHash dist: {h_phash - s_phash})"

        s_dhash = safe_hash(item.get("dhash"))
        if h_dhash and s_dhash and (h_dhash - s_dhash) <= hamming_threshold:
            return True, item, f"Visual appearance match (dHash dist: {h_dhash - s_dhash})"

        # 3. Center region match (Catches screenshots where borders/status bars were slightly cropped)
        s_center_w = safe_hash(item.get("center_whash"))
        if h_center_w and s_center_w and (h_center_w - s_center_w) <= 3:
            return True, item, f"Cropped image match (Center content dist: {h_center_w - s_center_w})"

        # 4. Mirrored / Flipped match
        if h_flip_p and s_phash and (h_flip_p - s_phash) <= 3:
            return True, item, "Mirrored / flipped image duplicate"
        if h_flip_w and s_whash and (h_flip_w - s_whash) <= 3:
            return True, item, "Mirrored / flipped image duplicate"

    return False, None, ""
