import io
import re
import hashlib
from typing import Tuple, Optional, List, Dict, Any
from PIL import Image

# Try importing imagehash if available, otherwise use fast built-in pure-Pillow algorithms
try:
    import imagehash
    HAS_IMAGEHASH = True
except ImportError:
    HAS_IMAGEHASH = False

def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
    """Fast difference hash (dHash) using pure Pillow."""
    try:
        resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(resized.getdata())
        diff = []
        for row in range(hash_size):
            for col in range(hash_size):
                p_left = pixels[row * (hash_size + 1) + col]
                p_right = pixels[row * (hash_size + 1) + col + 1]
                diff.append(p_left > p_right)
        val = 0
        for idx, v in enumerate(diff):
            if v:
                val += 1 << idx
        return f"{val:016x}"
    except Exception:
        return ""

def compute_ahash(img: Image.Image, hash_size: int = 8) -> str:
    """Fast average hash (aHash) using pure Pillow."""
    try:
        resized = img.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        pixels = list(resized.getdata())
        avg = sum(pixels) / max(1, len(pixels))
        val = 0
        for idx, p in enumerate(pixels):
            if p > avg:
                val += 1 << idx
        return f"{val:016x}"
    except Exception:
        return ""

def hamming_dist(h1: str, h2: str) -> int:
    """Calculate hamming distance between two hex hash strings."""
    if not h1 or not h2 or len(h1) != len(h2):
        return 999
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except Exception:
        return 999

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

        if HAS_IMAGEHASH:
            phash_val = str(imagehash.phash(img))
            dhash_val = str(imagehash.dhash(img))
            whash_val = str(imagehash.whash(img))

            flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
            flip_phash = str(imagehash.phash(flipped))
            flip_whash = str(imagehash.whash(flipped))

            cw1, ch1 = int(w * 0.15), int(h * 0.15)
            cw2, ch2 = max(cw1 + 10, int(w * 0.85)), max(ch1 + 10, int(h * 0.85))
            center_img = img.crop((cw1, ch1, cw2, ch2))
            center_whash = str(imagehash.whash(center_img))
            center_dhash = str(imagehash.dhash(center_img))
            center_phash = str(imagehash.phash(center_img))

            top_img = img.crop((0, 0, w, max(10, int(h * 0.6))))
            bottom_img = img.crop((0, max(0, int(h * 0.4)), w, h))
            top_whash = str(imagehash.whash(top_img))
            bottom_whash = str(imagehash.whash(bottom_img))
        else:
            dhash_val = compute_dhash(img)
            phash_val = compute_ahash(img)
            whash_val = dhash_val

            flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
            flip_phash = compute_ahash(flipped)
            flip_whash = compute_dhash(flipped)

            cw1, ch1 = int(w * 0.15), int(h * 0.15)
            cw2, ch2 = max(cw1 + 10, int(w * 0.85)), max(ch1 + 10, int(h * 0.85))
            center_img = img.crop((cw1, ch1, cw2, ch2))
            center_dhash = compute_dhash(center_img)
            center_phash = compute_ahash(center_img)
            center_whash = center_dhash

            top_img = img.crop((0, 0, w, max(10, int(h * 0.6))))
            bottom_img = img.crop((0, max(0, int(h * 0.4)), w, h))
            top_whash = compute_dhash(top_img)
            bottom_whash = compute_dhash(bottom_img)

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
    h_phash = fp.get("phash", "")
    h_dhash = fp.get("dhash", "")
    h_whash = fp.get("whash", "")
    h_flip_p = fp.get("flip_phash", "")
    h_flip_w = fp.get("flip_whash", "")
    h_center_w = fp.get("center_whash", "")

    for item in seen_images:
        if current_user_id is not None:
            prev_uid = item.get("user_id")
            if prev_uid and str(prev_uid) == str(current_user_id):
                continue

        # 1. Exact byte SHA-256 match
        if sha256_val and item.get("sha256") == sha256_val:
            return True, item, "Exact image file duplicate"

        # 2. Visual pattern / Wavelet / dHash match
        s_whash = item.get("whash", "")
        if h_whash and s_whash:
            dist = hamming_dist(h_whash, s_whash)
            if dist <= 3:
                return True, item, f"Visual pattern match (dist: {dist})"

        s_phash = item.get("phash", "")
        if h_phash and s_phash:
            dist = hamming_dist(h_phash, s_phash)
            if dist <= hamming_threshold:
                return True, item, f"Visual appearance match (dist: {dist})"

        s_dhash = item.get("dhash", "")
        if h_dhash and s_dhash:
            dist = hamming_dist(h_dhash, s_dhash)
            if dist <= hamming_threshold:
                return True, item, f"Visual appearance match (dist: {dist})"

        # 3. Center region match
        s_center_w = item.get("center_whash", "")
        if h_center_w and s_center_w:
            dist = hamming_dist(h_center_w, s_center_w)
            if dist <= 3:
                return True, item, f"Cropped image match (dist: {dist})"

        # 4. Mirrored / Flipped match
        if h_flip_p and s_phash and hamming_dist(h_flip_p, s_phash) <= 3:
            return True, item, "Mirrored / flipped image duplicate"
        if h_flip_w and s_whash and hamming_dist(h_flip_w, s_whash) <= 3:
            return True, item, "Mirrored / flipped image duplicate"

    return False, None, ""
