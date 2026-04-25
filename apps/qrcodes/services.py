"""
QR Code Services — Generation (PNG / SVG / PDF), Branding, Frames, Redirect Engine
====================================================================================

Handles:
  • Static QR (raw content) & Dynamic QR (redirect short-URL)
  • Module styles  — square, rounded, circle, gapped, vertical/horizontal bars
  • Gradient fills — radial, square, horizontal-linear, vertical-linear
  • Logo overlay   — centre-pasted with background pad for readability
  • Frame / CTA    — banner-top / banner-bottom / rounded-box / ticket
  • Export formats  — PNG, SVG (vector), PDF (A4 embedded)
  • Bulk generation — Excel upload → async Celery task
"""
import io
import os
import uuid
import math
import re
import hashlib
import logging
from typing import Tuple

import qrcode

# Styled QR support — available in qrcode>=7.0 (qrcode[pil])
# Fall back gracefully if the server has an older package version.
try:
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import (
        SquareModuleDrawer,
        RoundedModuleDrawer,
        CircleModuleDrawer,
        GappedSquareModuleDrawer,
        VerticalBarsDrawer,
        HorizontalBarsDrawer,
    )
    from qrcode.image.styles.colormasks import (
        SolidFillColorMask,
        RadialGradiantColorMask,
        SquareGradiantColorMask,
        HorizontalGradiantColorMask,
        VerticalGradiantColorMask,
    )
    _STYLED_AVAILABLE = True
except ImportError:
    _STYLED_AVAILABLE = False
    logger_init = logging.getLogger('apps.qrcodes')
    logger_init.warning('qrcode styled modules not available — falling back to basic QR generation.')
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger('apps.qrcodes')

_EC_MAP = {
    'L': qrcode.constants.ERROR_CORRECT_L,
    'M': qrcode.constants.ERROR_CORRECT_M,
    'Q': qrcode.constants.ERROR_CORRECT_Q,
    'H': qrcode.constants.ERROR_CORRECT_H,
}


# ════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert ``#RRGGBB`` → ``(r, g, b)``."""
    h = (hex_color or '#000000').lstrip('#')
    if len(h) != 6:
        return (0, 0, 0)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.1 relative luminance of a hex colour (0.0 – 1.0)."""
    r, g, b = _hex_to_rgb(hex_color)

    def _lin(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    """WCAG contrast ratio between two hex colours (1.0 – 21.0)."""
    L1 = _relative_luminance(hex1)
    L2 = _relative_luminance(hex2)
    lighter, darker = max(L1, L2), min(L1, L2)
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_contrast(
    fg: str, bg: str, min_ratio: float = 3.0
) -> Tuple[str, str]:
    """
    Guarantee at least *min_ratio* contrast between *fg* and *bg*.

    If the pair fails the threshold the foreground is progressively darkened
    toward black (or lightened toward white, whichever direction yields the
    greater gain) until the QR code will remain scannable.  Logs a debug
    message when an adjustment is made.
    Returns the adjusted ``(fg, bg)`` tuple unchanged when no fix is needed.
    """
    if _contrast_ratio(fg, bg) >= min_ratio:
        return fg, bg

    r, g, b = _hex_to_rgb(fg)
    # Try darkening
    for _ in range(25):
        r = max(0, int(r * 0.80))
        g = max(0, int(g * 0.80))
        b = max(0, int(b * 0.80))
        candidate = '#{:02X}{:02X}{:02X}'.format(r, g, b)
        if _contrast_ratio(candidate, bg) >= min_ratio:
            logger.debug('Contrast auto-adjusted: %s -> %s (bg=%s)', fg, candidate, bg)
            return candidate, bg

    # Ultimate fallback: pick black or white
    if _contrast_ratio('#000000', bg) >= _contrast_ratio('#FFFFFF', bg):
        return '#000000', bg
    return '#FFFFFF', bg


def _dpi_to_box_size(dpi: int) -> int:
    """
    Map a print DPI value to a qrcode box_size so the rendered image has
    enough pixels for crisp printing.

    A typical QR code with version 3 has 29 modules + 8 quiet-zone = 37 total.
    At 300 DPI for a 3 × 3 inch print we need ~900 px  →  box_size ≈ 24.
    We round up to the nearest multiple of 5 for clean numbers.

    Scale table (approximate):
      72  DPI →  8  (screen / web)
     150  DPI → 15  (standard digital)
     300  DPI → 30  (standard print)
     600  DPI → 60  (high-quality print)
    1200  DPI → 120 (professional / large-format print)
    """
    # box_size = dpi / 10,  clamped 8–120
    return max(8, min(120, dpi // 10))


def _safe_logo_px(qr_width: int, max_area_fraction: float = 0.09, padding: int = 6) -> int:
    """
    Maximum logo *side length* in pixels so that the total pasted box
    (logo + padding on all sides) covers ≤ *max_area_fraction* of the QR area.

    The function accounts for the white padding border placed around the logo
    before pasting — it is that larger box (logo_sz + 2*padding) that actually
    occludes QR modules, not the logo itself.

    Default 9% keeps well under 30% EC-H limit.  Industry-standard logo QRs
    use 7–12% to guarantee scannability across all phone cameras.

    History:
      0.28  → 35.6% actual (broke scanning — padding not accounted for)
      0.28  → 28.0% actual (still too tight — timing/alignment modules lost)
      0.09  → ~9%   actual (safe — leaves >90% of modules intact)
    """
    max_bg_side = int(qr_width * math.sqrt(max_area_fraction))
    return max(10, max_bg_side - 2 * padding)


def _get_module_drawer(style: str):
    """Return a *qrcode* module-drawer instance for the requested style."""
    return {
        'square':          SquareModuleDrawer(),
        'rounded':         RoundedModuleDrawer(radius_ratio=0.8),
        'circle':          CircleModuleDrawer(),
        'gapped':          GappedSquareModuleDrawer(size_ratio=0.8),
        'vertical_bars':   VerticalBarsDrawer(),
        'horizontal_bars': HorizontalBarsDrawer(),
    }.get(style, SquareModuleDrawer())


def _get_color_mask(qr):
    """Build a colour-mask (solid or gradient) from QR branding fields."""
    fg = _hex_to_rgb(qr.foreground_color or '#000000')
    bg = _hex_to_rgb(qr.background_color or '#FFFFFF')
    grad = getattr(qr, 'gradient_type', 'none') or 'none'
    if grad == 'none':
        return SolidFillColorMask(back_color=bg, front_color=fg)
    start = _hex_to_rgb(getattr(qr, 'gradient_start_color', '') or qr.foreground_color or '#000000')
    end   = _hex_to_rgb(getattr(qr, 'gradient_end_color', '')   or '#666666')
    return {
        'radial':   RadialGradiantColorMask(back_color=bg, center_color=start, edge_color=end),
        'square':   SquareGradiantColorMask(back_color=bg, center_color=start, edge_color=end),
        'linear_h': HorizontalGradiantColorMask(back_color=bg, left_color=start, right_color=end),
        'linear_v': VerticalGradiantColorMask(back_color=bg, top_color=start, bottom_color=end),
    }.get(grad, SolidFillColorMask(back_color=bg, front_color=fg))


def _get_qr_data(qr) -> str:
    """Return the payload to encode — short-URL for dynamic, raw content for static."""
    is_dynamic = getattr(qr, 'is_dynamic', True)
    if not is_dynamic:
        content = getattr(qr, 'static_content', '') or ''
        if content:
            return content
    return qr.short_url


def _get_font(size: int = 24) -> ImageFont.FreeTypeFont:
    """Load a TrueType font; fall back to PIL default bitmap font."""
    for path in (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
        'C:/Windows/Fonts/segoeui.ttf',
    ):
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    try:
        return ImageFont.truetype('arial', size)
    except Exception:
        return ImageFont.load_default()


# ════════════════════════════════════════════════════════
# CORE QR IMAGE GENERATION (PIL)
# ════════════════════════════════════════════════════════

def _generate_base_qr_pil(qr, box_size: int = 10) -> Image.Image:
    """
    Produce a branded QR PIL image with:
      • Custom module style (rounded, circle, gapped, bars …)
      • Solid or gradient colour fill
      • Centre logo overlay
    Falls back to plain qrcode.make() when styled modules are not installed.
    """
    data = _get_qr_data(qr)
    module_style = getattr(qr, 'module_style', 'square') or 'square'
    grad = getattr(qr, 'gradient_type', 'none') or 'none'
    has_logo = bool(getattr(qr, 'logo_url', '') or '')

    # ── Contrast safety check ────────────────────────────────────────────────
    raw_fg = qr.foreground_color or '#000000'
    raw_bg = qr.background_color or '#FFFFFF'
    safe_fg, safe_bg = _ensure_contrast(raw_fg, raw_bg, min_ratio=3.0)

    # ── Force H error correction when logo is present ────────────────────────
    # A logo covers ~28% of the QR area. Error correction must be H (30%
    # recoverable) so every module that the logo obscures can be reconstructed.
    # Lower EC levels will produce a QR that scans as blank or fails entirely.
    ec_key = qr.error_correction or 'M'
    if has_logo and ec_key != 'H':
        logger.debug(
            'Logo present on QR %s — upgrading error correction %s -> H',
            getattr(qr, 'slug', '?'), ec_key,
        )
        ec_key = 'H'

    qr_gen = qrcode.QRCode(
        version=None,
        error_correction=_EC_MAP.get(ec_key, qrcode.constants.ERROR_CORRECT_M),
        box_size=box_size,
        border=4,
    )
    qr_gen.add_data(data)
    qr_gen.make(fit=True)

    # Use StyledPilImage when available *and* a non-default style is requested
    if _STYLED_AVAILABLE and (module_style != 'square' or grad != 'none'):
        img = qr_gen.make_image(
            image_factory=StyledPilImage,
            module_drawer=_get_module_drawer(module_style),
            color_mask=_get_color_mask(qr),
        )
    else:
        img = qr_gen.make_image(
            fill_color=safe_fg,
            back_color=safe_bg,
        )

    img = img.convert('RGBA')

    # ── Logo overlay ──────────────────
    logo_url = qr.logo_url or ''
    if logo_url:
        try:
            logo_img = None
            # Try to resolve as a local media file first (avoids HTTP round-trip)
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            if logo_url.startswith(('http://', 'https://')):
                from urllib.parse import urlparse
                parsed_path = urlparse(logo_url).path
                if parsed_path.startswith(media_url):
                    rel = parsed_path[len(media_url):]
                    local = os.path.join(settings.MEDIA_ROOT, rel)
                    if os.path.isfile(local):
                        logo_img = Image.open(local).convert('RGBA')
            if logo_img is None:
                # HTTP fetch as fallback
                try:
                    import requests as req_lib
                    resp = req_lib.get(logo_url, timeout=5)
                    if resp.status_code == 200:
                        logo_img = Image.open(io.BytesIO(resp.content)).convert('RGBA')
                except ImportError:
                    pass

            if logo_img:
                qr_w, qr_h = img.size
                # Enforce ≤ 9% area so the QR stays scannable across all cameras
                logo_sz = _safe_logo_px(qr_w)
                logo_img = logo_img.resize((logo_sz, logo_sz), Image.LANCZOS)
                pad = 6
                bg_sz = logo_sz + pad * 2
                bg_rgb = _hex_to_rgb(qr.background_color or '#FFFFFF')
                bg_box = Image.new('RGBA', (bg_sz, bg_sz), bg_rgb + (255,))
                bg_box.paste(logo_img, (pad, pad), logo_img)
                pos = ((qr_w - bg_sz) // 2, (qr_h - bg_sz) // 2)
                img.paste(bg_box, pos, bg_box)
        except Exception as exc:
            logger.warning("Logo overlay failed for QR %s: %s", qr.slug, exc)

    return img


# ════════════════════════════════════════════════════════
# FRAME / CTA RENDERING
# ════════════════════════════════════════════════════════

def _apply_frame(img: Image.Image, qr) -> Image.Image:
    """Decorate the QR image with a branded CTA frame."""
    frame_style = getattr(qr, 'frame_style', 'none') or 'none'
    if frame_style == 'none':
        return img

    text = getattr(qr, 'frame_text', '') or 'SCAN ME'
    fc   = _hex_to_rgb(getattr(qr, 'frame_color', '#000000') or '#000000')
    tc   = _hex_to_rgb(getattr(qr, 'frame_text_color', '#FFFFFF') or '#FFFFFF')
    qr_w, qr_h = img.size
    pad      = 40
    banner_h = 64
    font     = _get_font(28)

    if frame_style == 'banner_bottom':
        cw, ch = qr_w + pad * 2, qr_h + pad * 2 + banner_h
        canvas = Image.new('RGBA', (cw, ch), fc + (255,))
        draw   = ImageDraw.Draw(canvas)
        draw.rounded_rectangle(
            [pad - 8, pad - 8, pad + qr_w + 8, pad + qr_h + 8],
            radius=8, fill=(255, 255, 255, 255),
        )
        canvas.paste(img, (pad, pad), img)
        bb     = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        ty     = qr_h + pad * 2 - 6
        draw.text(((cw - tw) // 2, ty + (banner_h - th) // 2), text, fill=tc + (255,), font=font)
        return canvas

    if frame_style == 'banner_top':
        cw, ch = qr_w + pad * 2, qr_h + pad * 2 + banner_h
        canvas = Image.new('RGBA', (cw, ch), fc + (255,))
        draw   = ImageDraw.Draw(canvas)
        bb     = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        draw.text(((cw - tw) // 2, (banner_h - th) // 2), text, fill=tc + (255,), font=font)
        draw.rounded_rectangle(
            [pad - 8, banner_h + pad // 2 - 8, pad + qr_w + 8, banner_h + pad // 2 + qr_h + 8],
            radius=8, fill=(255, 255, 255, 255),
        )
        canvas.paste(img, (pad, banner_h + pad // 2), img)
        return canvas

    if frame_style == 'rounded_box':
        cw, ch = qr_w + pad * 2, qr_h + pad * 2 + banner_h + 10
        canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        draw   = ImageDraw.Draw(canvas)
        draw.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=24, fill=fc + (255,))
        draw.rounded_rectangle(
            [pad - 10, pad - 10, pad + qr_w + 10, pad + qr_h + 10],
            radius=12, fill=(255, 255, 255, 255),
        )
        canvas.paste(img, (pad, pad), img)
        bb     = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        draw.text(((cw - tw) // 2, qr_h + pad + 20), text, fill=tc + (255,), font=font)
        return canvas

    if frame_style == 'ticket':
        cw, ch = qr_w + pad * 2, qr_h + pad * 3 + banner_h
        canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
        draw   = ImageDraw.Draw(canvas)
        draw.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=20, fill=fc + (255,))
        nr = 16
        ny = qr_h + pad + 10
        draw.ellipse([-nr, ny - nr, nr, ny + nr], fill=(0, 0, 0, 0))
        draw.ellipse([cw - nr, ny - nr, cw + nr, ny + nr], fill=(0, 0, 0, 0))
        for x in range(nr + 8, cw - nr - 8, 12):
            draw.line([(x, ny), (x + 6, ny)], fill=tc + (100,), width=1)
        draw.rounded_rectangle(
            [pad - 6, pad - 6, pad + qr_w + 6, pad + qr_h + 6],
            radius=8, fill=(255, 255, 255, 255),
        )
        canvas.paste(img, (pad, pad), img)
        bb     = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        draw.text(((cw - tw) // 2, ny + 20), text, fill=tc + (255,), font=font)
        return canvas

    return img


# ════════════════════════════════════════════════════════
# PUBLIC — PNG GENERATION
# ════════════════════════════════════════════════════════

def generate_qr_image(qr, return_image=False, box_size=10):
    """
    Generate a branded QR code PNG with module-style, gradient, logo and frame.
    Returns media URL (saved to disk) or PIL Image when ``return_image=True``.
    """
    img = _generate_base_qr_pil(qr, box_size=box_size)
    img = _apply_frame(img, qr)

    if return_image:
        return img

    save_dir = os.path.join(settings.MEDIA_ROOT, 'qr_images')
    os.makedirs(save_dir, exist_ok=True)
    filename = f"{qr.slug}.png"
    filepath = os.path.join(save_dir, filename)
    img.save(filepath, format='PNG')
    return f"{settings.MEDIA_URL}qr_images/{filename}"


# ════════════════════════════════════════════════════════
# PUBLIC — JPG GENERATION
# ════════════════════════════════════════════════════════

def generate_qr_jpg(qr, dpi: int = 150, quality: int = 92) -> bytes:
    """
    Generate a branded QR code as a JPEG image.

    JPEG does not support transparency — the image is composited onto a white
    (or QR background-colour) canvas before encoding, so no black artefacts
    appear at transparent-edge boundaries.

    Args:
        dpi:     Target print resolution.  Controls render size via box_size.
                 Typical values: 72 (screen), 150 (default), 300, 600, 1200.
        quality: JPEG quality 1-95.  92 is visually lossless for QR codes.

    Returns raw JPEG bytes.
    """
    box_size = _dpi_to_box_size(dpi)
    img = _generate_base_qr_pil(qr, box_size=box_size)
    img = _apply_frame(img, qr)

    # Flatten RGBA → RGB on the QR background colour
    bg_rgb = _hex_to_rgb(qr.background_color or '#FFFFFF')
    rgb = Image.new('RGB', img.size, bg_rgb)
    if img.mode == 'RGBA':
        rgb.paste(img, mask=img.split()[3])
    else:
        rgb.paste(img)

    buf = io.BytesIO()
    rgb.save(buf, format='JPEG', quality=quality, dpi=(dpi, dpi), optimize=True)
    return buf.getvalue()


# ════════════════════════════════════════════════════════
# SVG GRADIENT INJECTION HELPER
# ════════════════════════════════════════════════════════

def _inject_svg_gradient(svg_text: str, qr, fg: str) -> str:
    """
    Post-process a segno-generated SVG to replace the solid dark-module fill
    with a linear or radial gradient defined in ``<defs>``.

    Supports gradient_type values:
      radial, square (diagonal linear), linear_h, linear_v
    """
    grad_type = getattr(qr, 'gradient_type', 'none') or 'none'
    if grad_type == 'none':
        return svg_text

    start = getattr(qr, 'gradient_start_color', '') or fg
    end   = getattr(qr, 'gradient_end_color',   '') or '#666666'

    if grad_type == 'radial':
        grad_xml = (
            '<radialGradient id="qrGrad" cx="50%" cy="50%" r="50%" '
            'gradientUnits="objectBoundingBox">'
            f'<stop offset="0%" stop-color="{start}"/>'
            f'<stop offset="100%" stop-color="{end}"/>'
            '</radialGradient>'
        )
    elif grad_type == 'linear_h':
        grad_xml = (
            '<linearGradient id="qrGrad" x1="0%" y1="0%" x2="100%" y2="0%">'
            f'<stop offset="0%" stop-color="{start}"/>'
            f'<stop offset="100%" stop-color="{end}"/>'
            '</linearGradient>'
        )
    elif grad_type == 'linear_v':
        grad_xml = (
            '<linearGradient id="qrGrad" x1="0%" y1="0%" x2="0%" y2="100%">'
            f'<stop offset="0%" stop-color="{start}"/>'
            f'<stop offset="100%" stop-color="{end}"/>'
            '</linearGradient>'
        )
    else:  # square → diagonal linear
        grad_xml = (
            '<linearGradient id="qrGrad" x1="0%" y1="0%" x2="100%" y2="100%">'
            f'<stop offset="0%" stop-color="{start}"/>'
            f'<stop offset="100%" stop-color="{end}"/>'
            '</linearGradient>'
        )

    defs_block = f'<defs>{grad_xml}</defs>'

    # Insert <defs> right after the opening <svg ...> tag
    svg_text = re.sub(
        r'(<svg\b[^>]*>)',
        r'\1' + defs_block,
        svg_text,
        count=1,
    )

    # segno renders QR modules as *stroked* paths (stroke="colour").
    # We must replace both fill and stroke attributes that carry the dark colour.
    # Build short 3-char hex variant (e.g. '#cc0000' → '#c00') that segno emits.
    def _try_short(h: str):
        h = h.lstrip('#').lower()
        if len(h) == 6 and h[0] == h[1] and h[2] == h[3] and h[4] == h[5]:
            return '#' + h[0] + h[2] + h[4]
        return None

    targets = {fg, fg.lower(), fg.upper(), '#000000', 'black'}
    short = _try_short(fg)
    if short:
        targets.update({short, short.upper()})

    for t in targets:
        svg_text = svg_text.replace(f'fill="{t}"',   'fill="url(#qrGrad)"')
        svg_text = svg_text.replace(f'stroke="{t}"', 'stroke="url(#qrGrad)"')

    return svg_text


# ════════════════════════════════════════════════════════
# SVG GENERATION  (segno — pure-Python, clean SVG output)
# ════════════════════════════════════════════════════════

def generate_qr_svg(qr) -> bytes:
    """
    Generate a branded QR code as clean SVG vector output using *segno*.

    Features:
      • Custom foreground / background colours with WCAG contrast enforcement
      • Radial, diagonal-square, horizontal-linear, vertical-linear gradients
        injected via ``<defs>`` post-processing
      • Correct error-correction level forwarded from the QR record
    Returns raw UTF-8 SVG bytes.
    """
    try:
        import segno
    except ImportError:
        # Graceful fallback to qrcode SVG if segno not installed yet
        from qrcode.image.svg import SvgPathImage
        data = _get_qr_data(qr)
        qr_gen = qrcode.QRCode(
            version=None,
            error_correction=_EC_MAP.get(qr.error_correction, qrcode.constants.ERROR_CORRECT_M),
            box_size=10,
            border=4,
        )
        qr_gen.add_data(data)
        qr_gen.make(fit=True)
        svg_img = qr_gen.make_image(image_factory=SvgPathImage)
        buf = io.BytesIO()
        svg_img.save(buf)
        return buf.getvalue()

    data = _get_qr_data(qr)
    raw_fg = qr.foreground_color or '#000000'
    raw_bg = qr.background_color or '#FFFFFF'

    # ── Contrast safety check ────────────────────────────────────────────────
    safe_fg, safe_bg = _ensure_contrast(raw_fg, raw_bg, min_ratio=3.0)

    ec_map = {'L': 'L', 'M': 'M', 'Q': 'Q', 'H': 'H'}
    ec = ec_map.get((qr.error_correction or 'M').upper(), 'M')

    qr_code = segno.make_qr(data, error=ec)

    buf = io.BytesIO()
    # scale=10 → each module is 10 SVG units; border=4 (quiet zone)
    qr_code.save(
        buf,
        kind='svg',
        dark=safe_fg,
        light=safe_bg,
        scale=10,
        border=4,
    )
    svg_text = buf.getvalue().decode('utf-8')

    # ── Gradient injection ───────────────────────────────────────────────────
    grad = getattr(qr, 'gradient_type', 'none') or 'none'
    if grad != 'none':
        svg_text = _inject_svg_gradient(svg_text, qr, safe_fg)

    return svg_text.encode('utf-8')


# ════════════════════════════════════════════════════════
# PDF GENERATION
# ════════════════════════════════════════════════════════

def generate_qr_pdf(qr, box_size: int = 10, dpi: int = 150) -> bytes:
    """
    Embed the branded QR image (with frame) into a single-page A4 PDF.

    Args:
        box_size: Pixel size per QR module (overridden when dpi is supplied
                  via the download view).
        dpi:      Target print DPI embedded in PDF metadata (72–1200).

    Returns raw PDF bytes.
    """    
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.lib.colors import HexColor
    except ImportError:
        raise ImportError(
            "reportlab is required for PDF export. Install with: pip install reportlab"
        )

    img = _generate_base_qr_pil(qr, box_size=box_size)
    img = _apply_frame(img, qr)

    # Convert RGBA → RGB (PDF doesn't support alpha well)
    if img.mode == 'RGBA':
        rgb = Image.new('RGB', img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[3])
        img = rgb

    buf = io.BytesIO()
    c   = pdf_canvas.Canvas(buf, pagesize=A4)
    pw, ph = A4

    # Scale QR to max 150 mm, centred
    max_dim = 150 * mm
    iw, ih  = img.size
    scale   = min(max_dim / iw, max_dim / ih)
    dw, dh  = iw * scale, ih * scale
    x = (pw - dw) / 2
    y = (ph - dh) / 2 + 30 * mm

    c.drawImage(ImageReader(img), x, y, width=dw, height=dh)

    # Title
    c.setFont('Helvetica-Bold', 18)
    c.drawCentredString(pw / 2, y + dh + 16 * mm, qr.title or 'QR Code')

    # Encoded data
    c.setFont('Helvetica', 11)
    c.setFillColor(HexColor('#666666'))
    c.drawCentredString(pw / 2, y - 10 * mm, _get_qr_data(qr))

    # Footer
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#999999'))
    c.drawCentredString(pw / 2, 18 * mm, f'Generated by QRGenie \u00b7 {qr.slug}')

    c.save()
    return buf.getvalue()


# ════════════════════════════════════════════════════════
# REDIRECT ENGINE — RULES EVALUATION
# ════════════════════════════════════════════════════════

def evaluate_rules(qr, scan_context: dict) -> str:
    """
    Evaluate routing rules for a QR code and return the final destination URL.

    scan_context contains:
        - ip: client IP
        - country: geo country code
        - city: geo city
        - device_type: mobile/desktop/tablet
        - os: android/ios/windows/mac/linux
        - browser: chrome/safari/firefox/edge
        - language: browser language code
        - lat/lon: GPS coordinates (optional)
        - url_params: dict of URL query params
        - user_agent: full user agent string
    """
    from .models import RoutingRule

    rules = RoutingRule.objects.filter(
        qr_code=qr, is_active=True
    ).order_by('-priority')

    for rule in rules:
        if _rule_matches(rule, scan_context):
            logger.info(f"Rule matched: {rule.rule_type} → {rule.destination_url} for QR {qr.slug}")
            return rule.destination_url

    # No rule matched → use primary destination or fallback
    return qr.destination_url or qr.fallback_url or ''


def _rule_matches(rule, ctx: dict) -> bool:
    """Check if a single routing rule matches the scan context."""
    conditions = rule.conditions or {}

    if rule.rule_type == 'device':
        return _match_device(conditions, ctx)
    elif rule.rule_type == 'geo':
        return _match_geo(conditions, ctx)
    elif rule.rule_type == 'time':
        return _match_time(conditions)
    elif rule.rule_type == 'language':
        return _match_language(conditions, ctx)
    elif rule.rule_type == 'gps_radius':
        return _match_gps_radius(conditions, ctx)
    elif rule.rule_type == 'ab_test':
        return _match_ab_test(conditions, ctx)
    elif rule.rule_type == 'url_param':
        return _match_url_param(conditions, ctx)

    return False


def _match_device(conditions: dict, ctx: dict) -> bool:
    """Match device type (mobile/desktop) and OS."""
    device_type = conditions.get('device_type', '').lower()
    os_name = conditions.get('os', '').lower()

    if device_type and ctx.get('device_type', '').lower() != device_type:
        return False
    if os_name and ctx.get('os', '').lower() != os_name:
        return False
    return True


def _match_geo(conditions: dict, ctx: dict) -> bool:
    """Match country and/or city."""
    country = conditions.get('country', '').upper()
    city = conditions.get('city', '').lower()

    if country and ctx.get('country', '').upper() != country:
        return False
    if city and ctx.get('city', '').lower() != city:
        return False
    return True


def _match_time(conditions: dict) -> bool:
    """Match current time against schedule."""
    from django.utils import timezone
    import pytz
    from datetime import datetime

    tz_name = conditions.get('timezone', 'UTC')
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.UTC

    now = timezone.now().astimezone(tz)

    # Check day of week
    days = conditions.get('days', [])
    if days:
        day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        current_day = now.weekday()
        allowed_days = [day_map.get(d.lower(), -1) for d in days]
        if current_day not in allowed_days:
            return False

    # Check time range
    start = conditions.get('start')
    end = conditions.get('end')
    if start and end:
        current_time = now.strftime('%H:%M')
        if not (start <= current_time <= end):
            return False

    return True


def _match_language(conditions: dict, ctx: dict) -> bool:
    """Match browser language."""
    languages = conditions.get('languages', [])
    user_lang = ctx.get('language', '').lower()[:2]
    return user_lang in [l.lower()[:2] for l in languages]


def _match_gps_radius(conditions: dict, ctx: dict) -> bool:
    """Match GPS coordinates within radius using Haversine formula."""
    import math

    target_lat = conditions.get('lat')
    target_lon = conditions.get('lon')
    radius_meters = conditions.get('radius_meters', 500)

    user_lat = ctx.get('lat')
    user_lon = ctx.get('lon')

    if not all([target_lat, target_lon, user_lat, user_lon]):
        return False

    # Haversine formula
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(float(target_lat))
    phi2 = math.radians(float(user_lat))
    dphi = math.radians(float(user_lat) - float(target_lat))
    dlambda = math.radians(float(user_lon) - float(target_lon))

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c

    return distance <= radius_meters


def _match_ab_test(conditions: dict, ctx: dict) -> bool:
    """A/B test matching based on a hash of the scan IP for consistent bucketing."""
    weight = conditions.get('weight', 50)  # Percentage (0–100)
    variant = conditions.get('variant', 'A')

    # Use IP as a consistent hashing key
    ip = ctx.get('ip', '')
    hash_val = int(hashlib.md5(ip.encode()).hexdigest(), 16) % 100

    if variant == 'A':
        return hash_val < weight
    else:
        return hash_val >= weight


def _match_url_param(conditions: dict, ctx: dict) -> bool:
    """Match URL query parameter."""
    key = conditions.get('key', '')
    value = conditions.get('value', '')
    params = ctx.get('url_params', {})

    if key in params:
        if value:
            return params[key] == value
        return True  # Key exists, no value check required
    return False


# ════════════════════════════════════════════════════════
# LANGUAGE ROUTE DETECTION (Feature 8)
# ════════════════════════════════════════════════════════

def parse_accept_language(header: str) -> list[tuple[str, float]]:
    """
    Parse Accept-Language header per RFC 2616 §14.4.
    Returns list of (language_tag, quality) sorted by quality descending.

    Examples:
      "en-US,en;q=0.9,hi;q=0.8,fr;q=0.7" → [("en-US",1.0), ("en",0.9), ("hi",0.8), ("fr",0.7)]
      "de"                                  → [("de",1.0)]
      "*;q=0.5, en;q=1"                     → [("en",1.0), ("*",0.5)]
    """
    if not header or not header.strip():
        return []

    result = []
    for part in header.split(','):
        part = part.strip()
        if not part:
            continue
        # Split off ;q= portion
        segments = part.split(';')
        lang = segments[0].strip()
        quality = 1.0
        for seg in segments[1:]:
            seg = seg.strip()
            if seg.lower().startswith('q='):
                try:
                    quality = float(seg[2:])
                    quality = max(0.0, min(1.0, quality))
                except (ValueError, IndexError):
                    quality = 0.0
        if lang:
            result.append((lang, quality))

    # Stable sort by quality descending
    result.sort(key=lambda x: -x[1])
    return result


def _lang_matches(candidate: str, route_lang: str) -> bool:
    """
    Check if an Accept-Language candidate matches a configured route language.
    Supports exact match and base-language fallback.

    _lang_matches('en-US', 'en')    → True   (base match)
    _lang_matches('en', 'en-US')    → True   (reverse base match)
    _lang_matches('en-US', 'en-US') → True   (exact)
    _lang_matches('fr', 'en')       → False
    """
    c = candidate.lower().strip()
    r = route_lang.lower().strip()
    if c == r:
        return True
    # Base language match: en-US matches en, en matches en-US
    c_base = c.split('-')[0]
    r_base = r.split('-')[0]
    return c_base == r_base


def get_language_destination(qr, accept_language: str = '', country: str = '', region: str = '', city: str = '') -> str | None:
    """
    Determine redirect URL based on browser language / geo for a QR code.

    Priority (designed for multilingual countries like India where browsers
    send English even though the user speaks Telugu/Tamil/etc.):

      0. GEO-DIRECT district (e.g. IN + AP + Visakhapatnam → specific URL) — highest
      0b.GEO-DIRECT state   (e.g. IN + AP → state URL, if no district match)
      1. GEO-REGION → language (e.g. "IN-AP" → te → Telugu URL)
      2. Accept-Language negotiation with quality weights (RFC 2616)
      3. GEO-COUNTRY → language (e.g. "IN" → hi → Hindi URL)
      4. default_url or None (fall through to QR destination).

    Returns URL string or None.
    """
    slug = getattr(qr, 'slug', '?')

    try:
        lang_route = qr.language_route
    except Exception:
        logger.info(f"[LangRoute] slug={slug} no language_route configured")
        return None

    if not lang_route.is_active:
        logger.info(f"[LangRoute] slug={slug} language_route is inactive")
        return None

    routes = lang_route.routes or []
    geo_direct = lang_route.geo_direct if hasattr(lang_route, 'geo_direct') else []
    geo_direct = geo_direct or []

    if not routes and not geo_direct:
        logger.info(f"[LangRoute] slug={slug} no routes or geo_direct configured, default_url={lang_route.default_url or '(none)'}")
        return lang_route.default_url or None

    logger.info(
        f"[LangRoute] slug={slug} routes={[r.get('lang') for r in routes]} "
        f"geo_direct={len(geo_direct)} entries, geo_fallback={lang_route.geo_fallback} "
        f"accept_lang={accept_language[:40]} country={country} region={region} city={city}"
    )

    # Build a quick lookup: base_lang → url
    def find_route_url(lang_code: str) -> str | None:
        """Find the first route matching the given language code."""
        for route in routes:
            if _lang_matches(lang_code, route.get('lang', '')):
                return route.get('url', '')
        return None

    # ── Step 0: Geo-DIRECT district match (highest priority) ──
    # e.g. scan from Visakhapatnam + geo_direct has {country:IN, state:AP, district:Visakhapatnam} → URL
    if geo_direct and country:
        country_u = country.upper()
        region_u = region.upper() if region else ''
        city_lower = city.lower().strip() if city else ''

        # First pass: match with district (most specific)
        if city_lower:
            for entry in geo_direct:
                e_country = (entry.get('country', '') or '').upper()
                e_state = (entry.get('state', '') or '').upper()
                e_district_raw = (entry.get('district', '') or '').lower().strip()
                if not (e_country == country_u and e_state == region_u and e_district_raw):
                    continue
                # Support comma-separated aliases e.g. "Vizianagaram,Vizianagaram District"
                aliases = [a.strip() for a in e_district_raw.split(',') if a.strip()]
                # Fuzzy match any alias: exact, or one contains the other
                district_match = any(
                    alias == city_lower or alias in city_lower or city_lower in alias
                    for alias in aliases
                )
                if district_match:
                    url = entry.get('url', '')
                    if url:
                        logger.info(f"[LangRoute] slug={slug} ✓ STEP 0a geo-direct district: {country_u}-{region_u}-{city} (matched aliases={aliases}) → {url[:80]}")
                        return url

        # Second pass: match without district (state-level geo_direct)
        if region_u:
            for entry in geo_direct:
                e_country = (entry.get('country', '') or '').upper()
                e_state = (entry.get('state', '') or '').upper()
                e_district = (entry.get('district', '') or '').strip()
                if e_country == country_u and e_state == region_u and not e_district:
                    url = entry.get('url', '')
                    if url:
                        logger.info(f"[LangRoute] slug={slug} ✓ STEP 0b geo-direct state: {country_u}-{region_u} → {url[:80]}")
                        return url

        logger.info(f"[LangRoute] slug={slug} step 0: no geo_direct match for {country_u}-{region_u}-{city_lower}")
    elif geo_direct:
        logger.info(f"[LangRoute] slug={slug} step 0 skipped: country is empty")

    geo_map = lang_route.geo_fallback or {}

    # ── Step 1: Geo-REGION match (highest priority) ──
    # e.g. scan from Andhra Pradesh + "IN-AP":"te" configured → Telugu URL
    # This overrides Accept-Language because Indian phones typically send
    # "en-US" even when the user speaks Telugu/Tamil/Kannada/etc.
    if geo_map and country and region:
        region_key = f"{country.upper()}-{region.upper()}"
        mapped_lang = geo_map.get(region_key, '')
        if mapped_lang:
            url = find_route_url(mapped_lang)
            if url:
                logger.info(f"[LangRoute] slug={slug} ✓ STEP 1 geo-region: {region_key} → lang={mapped_lang} → {url[:80]}")
                return url
            else:
                logger.info(f"[LangRoute] slug={slug} step 1: {region_key} → lang={mapped_lang} but no route for that lang")
        else:
            logger.info(f"[LangRoute] slug={slug} step 1: geo_fallback has no key '{region_key}'")
    else:
        reasons = []
        if not geo_map: reasons.append('no geo_fallback configured')
        if not country: reasons.append('country is empty')
        if not region: reasons.append('region is empty')
        logger.info(f"[LangRoute] slug={slug} step 1 skipped: {', '.join(reasons)}")

    # ── Step 2: Accept-Language negotiation ──
    if accept_language and lang_route.use_quality_weights:
        parsed = parse_accept_language(accept_language)
        logger.info(f"[LangRoute] slug={slug} step 2: parsed Accept-Language → {parsed[:5]}")
        for lang_tag, _quality in parsed:
            if lang_tag == '*':
                url = routes[0].get('url', '') or None if routes else None
                logger.info(f"[LangRoute] slug={slug} ✓ STEP 2 wildcard → {url}")
                return url
            url = find_route_url(lang_tag)
            if url:
                logger.info(f"[LangRoute] slug={slug} ✓ STEP 2 accept-lang: {lang_tag} → {url[:80]}")
                return url
        logger.info(f"[LangRoute] slug={slug} step 2: no Accept-Language match found")
    elif accept_language:
        first_lang = accept_language.split(',')[0].split(';')[0].strip()
        if first_lang:
            url = find_route_url(first_lang)
            if url:
                logger.info(f"[LangRoute] slug={slug} ✓ STEP 2 raw first-lang: {first_lang} → {url[:80]}")
                return url
        logger.info(f"[LangRoute] slug={slug} step 2 (no q-weights): no match for {first_lang}")

    # ── Step 3: Geo-COUNTRY fallback (broad) ──
    # e.g. scan from Delhi (no IN-DL configured) → "IN":"hi" → Hindi
    if geo_map and country:
        mapped_lang = geo_map.get(country.upper(), '')
        if mapped_lang:
            url = find_route_url(mapped_lang)
            if url:
                logger.info(f"[LangRoute] slug={slug} ✓ STEP 3 geo-country: {country} → lang={mapped_lang} → {url[:80]}")
                return url
            else:
                logger.info(f"[LangRoute] slug={slug} step 3: {country} → lang={mapped_lang} but no route for that lang")
        else:
            logger.info(f"[LangRoute] slug={slug} step 3: geo_fallback has no key '{country}'")

    # ── Step 4: Default URL or None ──
    default = lang_route.default_url or None
    logger.info(f"[LangRoute] slug={slug} step 4: default_url={default or '(none, fall through)'}")
    return default


# ════════════════════════════════════════════════════════
# CACHE HELPERS
# ════════════════════════════════════════════════════════

def get_qr_from_cache(slug: str):
    """
    Get QR code from cache, fallback to DB.

    Performance: caches the FULL model instance (with related objects
    pre-loaded via select_related/prefetch_related) so a cache hit
    requires ZERO database queries — target <1ms on hit.
    """
    cache_key = f"qr:obj:{slug}"
    qr = cache.get(cache_key)
    if qr is not None:
        # Cache stores False for known-missing slugs (negative cache)
        return qr if qr is not False else None

    # Cache miss → DB lookup
    from .models import QRCode
    try:
        qr = QRCode.objects.select_related(
            'organization', 'language_route',
        ).prefetch_related('rules').get(slug=slug)
        cache.set(cache_key, qr, timeout=300)  # 5 min cache
        return qr
    except QRCode.DoesNotExist:
        cache.set(cache_key, False, timeout=60)  # Negative cache 1 min
        return None


def invalidate_qr_cache(slug: str):
    """Invalidate cached QR data."""
    cache.delete(f"qr:obj:{slug}")


# ════════════════════════════════════════════════════════
# BULK UPLOAD PROCESSING
# ════════════════════════════════════════════════════════

def process_bulk_upload(job_id: str):
    """Process a bulk Excel or CSV upload to create QR codes."""
    import openpyxl
    import csv as csv_module
    from .models import QRCode, BulkUploadJob

    try:
        job = BulkUploadJob.objects.get(id=job_id)
    except BulkUploadJob.DoesNotExist:
        return

    job.status = 'processing'
    job.started_at = __import__('django').utils.timezone.now()
    job.save()

    try:
        file_path = job.file_url
        if file_path.endswith('.csv'):
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv_module.reader(f)
                next(reader, None)  # Skip header
                rows = [tuple(r) for r in reader]
        else:
            wb = openpyxl.load_workbook(file_path)
            ws = wb.active
            rows = list(ws.iter_rows(min_row=2, values_only=True))
        job.total_rows = len(rows)
        job.save()

        VALID_QR_TYPES = {c[0] for c in QRCode.QRType.choices}

        for i, row in enumerate(rows):
            try:
                if not row or not row[0]:
                    continue

                title = str(row[0]).strip() if row[0] else f'QR_{i+1}'
                qr_type = str(row[1]).strip().lower() if len(row) > 1 and row[1] else 'url'
                destination_url = str(row[2]).strip() if len(row) > 2 and row[2] else ''
                tags_str = str(row[3]).strip() if len(row) > 3 and row[3] else ''

                qr = QRCode.objects.create(
                    organization=job.organization,
                    created_by=job.created_by,
                    title=title,
                    destination_url=destination_url,
                    qr_type=qr_type if qr_type in VALID_QR_TYPES else 'url',
                    tags=[t.strip() for t in tags_str.split(',') if t.strip()],
                )

                # Generate image
                img_url = generate_qr_image(qr)
                qr.qr_image_url = img_url
                qr.save(update_fields=['qr_image_url'])

                job.success_count += 1
            except Exception as e:
                job.error_count += 1
                job.errors.append({'row': i + 2, 'error': str(e)})

            job.processed_rows = i + 1
            job.save()

        job.status = 'completed'
        job.completed_at = __import__('django').utils.timezone.now()
        job.save()

        # Fire automation trigger: bulk_upload_completed
        try:
            from apps.automation.tasks import fire_automation_trigger
            fire_automation_trigger(
                trigger_type='bulk_upload_completed',
                context={
                    'job_id': str(job.id),
                    'total_rows': job.total_rows,
                    'success_count': job.success_count,
                    'error_count': job.error_count,
                },
                org_id=str(job.organization_id),
            )
        except Exception:
            pass

    except Exception as e:
        job.status = 'failed'
        job.errors.append({'error': str(e)})
        job.save()
        logger.error(f"Bulk upload job {job_id} failed: {e}")


# ════════════════════════════════════════════════════════
# FEATURE 6 — AUTO-ROTATING LANDING PAGES
# ════════════════════════════════════════════════════════

def get_rotation_destination(qr) -> str | None:
    """
    Return the URL the QR should redirect to based on its active rotation schedule.
    Returns None if no active schedule is configured so the caller falls back normally.

    Rotation types:
      daily  — cycles through the pages list one entry per calendar day
               (uses days elapsed since 2000-01-01 mod len(pages))
      weekly — one entry per ISO day-of-week (0=Mon … 6=Sun)
               entry must have  "day_of_week": <int 0-6>
      custom — each entry has "start_date"/"end_date" (ISO YYYY-MM-DD)
               first matching range wins
    """
    try:
        from .models import RotationSchedule
        import zoneinfo
        from datetime import date, datetime

        try:
            sched = qr.rotation_schedule
        except RotationSchedule.DoesNotExist:
            return None

        if not sched.is_active:
            return None

        pages = sched.pages or []
        if not pages:
            return None

        # Resolve timezone
        try:
            tz = zoneinfo.ZoneInfo(sched.tz or 'UTC')
        except Exception:
            tz = zoneinfo.ZoneInfo('UTC')

        today = datetime.now(tz=tz).date()

        if sched.rotation_type == 'daily':
            epoch = date(2000, 1, 1)
            idx = (today - epoch).days % len(pages)
            return pages[idx].get('page_url') or None

        elif sched.rotation_type == 'weekly':
            weekday = today.weekday()   # 0=Mon … 6=Sun
            for page in pages:
                if page.get('day_of_week') == weekday:
                    return page.get('page_url') or None
            # Fallback: first page with a URL if no match for today's weekday
            for page in pages:
                url = page.get('page_url')
                if url:
                    return url
            return None

        elif sched.rotation_type == 'custom':
            for page in pages:
                try:
                    start = date.fromisoformat(page['start_date'])
                    end   = date.fromisoformat(page['end_date'])
                    if start <= today <= end:
                        return page.get('page_url') or None
                except (KeyError, ValueError):
                    continue
            return None

    except Exception as exc:
        logger.warning('get_rotation_destination error for %s: %s', getattr(qr, 'slug', '?'), exc)
        return None


def get_time_destination(qr) -> str | None:
    """
    Return the URL the QR should redirect to based on the current time of day.
    Returns None if no active time schedule is configured.

    Rules are evaluated in order; first matching time window wins.
    Each rule has start_time, end_time (HH:MM), optional days list.
    Supports overnight windows (e.g. 22:00 → 06:00).
    """
    try:
        from .models import TimeSchedule
        import zoneinfo
        from datetime import datetime

        try:
            sched = qr.time_schedule
        except TimeSchedule.DoesNotExist:
            return None

        if not sched.is_active:
            return None

        rules = sched.rules or []
        if not rules:
            return sched.default_url or None

        # Resolve timezone
        try:
            tz = zoneinfo.ZoneInfo(sched.tz or 'UTC')
        except Exception:
            tz = zoneinfo.ZoneInfo('UTC')

        now = datetime.now(tz=tz)
        current_time = now.strftime('%H:%M')
        current_weekday = now.weekday()  # 0=Mon … 6=Sun

        day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}

        for rule in rules:
            url = rule.get('url', '')
            start = rule.get('start_time', '')
            end = rule.get('end_time', '')
            days = rule.get('days', [])

            if not url or not start or not end:
                continue

            # Check day filter
            if days:
                allowed = [day_map.get(d.lower(), -1) for d in days]
                if current_weekday not in allowed:
                    continue

            # Check time window (supports overnight spans like 22:00 → 06:00)
            if start <= end:
                # Normal window: e.g. 06:00 → 11:00
                if start <= current_time <= end:
                    logger.info(f"[TimeSchedule] matched rule '{rule.get('label', '?')}' "
                                f"({start}-{end}) for QR {getattr(qr, 'slug', '?')}")
                    return url
            else:
                # Overnight window: e.g. 22:00 → 06:00
                if current_time >= start or current_time <= end:
                    logger.info(f"[TimeSchedule] matched overnight rule '{rule.get('label', '?')}' "
                                f"({start}-{end}) for QR {getattr(qr, 'slug', '?')}")
                    return url

        # No rule matched → use default URL
        return sched.default_url or None

    except Exception as exc:
        logger.warning('get_time_destination error for %s: %s', getattr(qr, 'slug', '?'), exc)
        return None


def get_pdf_destination(qr) -> str | None:
    """
    If the QR has an active PDFDocument, return the viewer URL.
    The redirect engine will send scanners to the inline PDF viewer page.
    Returns None if no active PDF document is attached.
    """
    try:
        from .models import PDFDocument
        try:
            pdf_doc = qr.pdf_document
        except PDFDocument.DoesNotExist:
            return None

        if not pdf_doc.is_active:
            return None

        return pdf_doc.viewer_url or None

    except Exception as exc:
        logger.warning('get_pdf_destination error for %s: %s', getattr(qr, 'slug', '?'), exc)
        return None


def get_video_destination(qr) -> str | None:
    """
    If the QR has an active VideoDocument, return the player URL.
    The redirect engine will send scanners to the inline video player page.
    Returns None if no active video document is attached.
    """
    try:
        from .models import VideoDocument
        try:
            video_doc = qr.video_document
        except VideoDocument.DoesNotExist:
            return None

        if not video_doc.is_active:
            return None

        return video_doc.player_url or None

    except Exception as exc:
        logger.warning('get_video_destination error for %s: %s', getattr(qr, 'slug', '?'), exc)
        return None


# ════════════════════════════════════════════════════════
# DEVICE-BASED REDIRECT  (Feature 15)
# ════════════════════════════════════════════════════════

def get_device_destination(qr, user_agent: str) -> str | None:
    """
    Return the URL the QR should redirect to based on the scanner's device/OS.

    Detection priority:
      1. Tablet  (iPad, Android tablet — large screen mobile)
      2. iOS     (iPhone, iPod)
      3. Android (non-tablet)
      4. Windows
      5. macOS
      6. Linux
      7. default_url  (fallback)

    Uses ua-parser for reliable parsing.
    Returns None when no DeviceRoute is configured or active.
    """
    try:
        from .models import DeviceRoute

        try:
            route = qr.device_route
        except DeviceRoute.DoesNotExist:
            return None

        if not route.is_active:
            return None

        # Parse user-agent
        try:
            from ua_parser import user_agent_parser
            parsed = user_agent_parser.Parse(user_agent or '')
        except Exception:
            logger.warning('ua-parser failed for QR %s, falling back to basic detection',
                           getattr(qr, 'slug', '?'))
            parsed = None

        ua_lower = (user_agent or '').lower()

        if parsed:
            os_family = (parsed.get('os', {}).get('family', '') or '').lower()
            device_family = (parsed.get('device', {}).get('family', '') or '').lower()

            is_tablet = (
                'ipad' in device_family
                or ('android' in os_family and 'mobile' not in ua_lower)
                or 'tablet' in device_family
            )
            is_ios = os_family in ('ios', 'iphone os') or 'ipod' in device_family
            is_android = 'android' in os_family
            is_windows = 'windows' in os_family
            is_mac = os_family in ('mac os x', 'macos', 'mac os')
            is_linux = 'linux' in os_family and not is_android
        else:
            # Basic fallback if ua-parser import fails
            is_tablet = 'ipad' in ua_lower or ('android' in ua_lower and 'mobile' not in ua_lower)
            is_ios = 'iphone' in ua_lower or 'ipod' in ua_lower
            is_android = 'android' in ua_lower and not is_tablet
            is_windows = 'windows' in ua_lower
            is_mac = 'macintosh' in ua_lower or 'mac os' in ua_lower
            is_linux = 'linux' in ua_lower and not is_android

        # Priority order: tablet → iOS → Android → Windows → Mac → Linux → default
        if is_tablet and route.tablet_url:
            logger.info('[DeviceRoute] tablet → %s for QR %s', route.tablet_url, getattr(qr, 'slug', '?'))
            return route.tablet_url
        if is_ios and route.ios_url:
            logger.info('[DeviceRoute] iOS → %s for QR %s', route.ios_url, getattr(qr, 'slug', '?'))
            return route.ios_url
        if is_android and route.android_url:
            logger.info('[DeviceRoute] Android → %s for QR %s', route.android_url, getattr(qr, 'slug', '?'))
            return route.android_url
        if is_windows and route.windows_url:
            logger.info('[DeviceRoute] Windows → %s for QR %s', route.windows_url, getattr(qr, 'slug', '?'))
            return route.windows_url
        if is_mac and route.mac_url:
            logger.info('[DeviceRoute] Mac → %s for QR %s', route.mac_url, getattr(qr, 'slug', '?'))
            return route.mac_url
        if is_linux and route.linux_url:
            logger.info('[DeviceRoute] Linux → %s for QR %s', route.linux_url, getattr(qr, 'slug', '?'))
            return route.linux_url

        # Fallback
        if route.default_url:
            logger.info('[DeviceRoute] default → %s for QR %s', route.default_url, getattr(qr, 'slug', '?'))
            return route.default_url

        return None

    except Exception as exc:
        logger.warning('get_device_destination error for %s: %s', getattr(qr, 'slug', '?'), exc)
        return None


# ════════════════════════════════════════════════════════
# GPS-RADIUS GEO-FENCE  (Feature 17)
# ════════════════════════════════════════════════════════

def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in meters between two lat/lng points using Haversine."""
    import math
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_geofence_destination(qr, lat: float, lng: float) -> str | None:
    """
    Check if (lat, lng) falls inside any of the QR's geo-fence zones.
    Zones are evaluated in order; first match wins.
    Returns the matching zone URL, or default_url, or None.
    """
    try:
        from .models import GeoFenceRule

        try:
            fence = qr.geo_fence
        except GeoFenceRule.DoesNotExist:
            return None

        if not fence.is_active:
            return None

        zones = fence.zones or []
        if not zones:
            return fence.default_url or None

        for zone in zones:
            try:
                z_lat = float(zone.get('lat', 0))
                z_lng = float(zone.get('lng', 0))
                z_radius = float(zone.get('radius_meters', 200))
                z_url = zone.get('url', '')

                if not z_url or (z_lat == 0 and z_lng == 0):
                    continue

                distance = _haversine_meters(lat, lng, z_lat, z_lng)
                if distance <= z_radius:
                    logger.info(
                        '[GeoFence] User at (%.4f,%.4f) is %.0fm from "%s" (radius=%dm) → %s for QR %s',
                        lat, lng, distance, zone.get('label', '?'), int(z_radius),
                        z_url[:80], getattr(qr, 'slug', '?'),
                    )
                    return z_url
            except (ValueError, TypeError):
                continue

        # No zone matched → default
        if fence.default_url:
            logger.info('[GeoFence] No zone matched → default %s for QR %s',
                        fence.default_url[:80], getattr(qr, 'slug', '?'))
            return fence.default_url

        return None

    except Exception as exc:
        logger.warning('get_geofence_destination error for %s: %s', getattr(qr, 'slug', '?'), exc)
        return None


def has_active_geofence(qr) -> bool:
    """Return True if QR has an active GeoFenceRule with at least one zone."""
    try:
        from .models import GeoFenceRule
        fence = qr.geo_fence
        return fence.is_active and bool(fence.zones)
    except Exception:
        return False


# ════════════════════════════════════════════════════════
# A/B SPLIT TESTING  (Feature 18)
# ════════════════════════════════════════════════════════

def get_ab_test_destination(qr, sticky_variant_idx: int | None = None) -> tuple[str | None, int | None]:
    """
    Pick a variant URL for A/B split testing.

    If sticky_variant_idx is provided (from cookie), return that variant directly.
    Otherwise pick randomly based on configured weights.

    Returns (url, chosen_variant_index) or (None, None) if no active test.
    """
    try:
        from .models import ABTest
        import random as _rand

        try:
            ab = qr.ab_test
        except ABTest.DoesNotExist:
            return (None, None)

        if not ab.is_active:
            return (None, None)

        variants = ab.variants or []
        if not variants:
            return (None, None)

        # Filter valid variants (must have url and weight > 0)
        valid = []
        for i, v in enumerate(variants):
            url = v.get('url', '').strip()
            weight = float(v.get('weight', 0))
            if url and weight > 0:
                valid.append((i, url, weight))

        if not valid:
            return (None, None)

        # Sticky: return the previously assigned variant if it's still valid
        if sticky_variant_idx is not None:
            for (i, url, _w) in valid:
                if i == sticky_variant_idx:
                    logger.info(
                        '[ABTest] Sticky variant idx=%d → %s for QR %s',
                        i, url[:80], getattr(qr, 'slug', '?'),
                    )
                    return (url, i)
            # Sticky index no longer valid (variant removed) → fall through to random

        # Random weighted selection
        total_weight = sum(w for (_, _, w) in valid)
        roll = _rand.uniform(0, total_weight)
        cumulative = 0.0
        for (i, url, weight) in valid:
            cumulative += weight
            if roll <= cumulative:
                logger.info(
                    '[ABTest] Random variant idx=%d weight=%.1f → %s for QR %s',
                    i, weight, url[:80], getattr(qr, 'slug', '?'),
                )
                return (url, i)

        # Edge case: return last valid
        i, url, _ = valid[-1]
        return (url, i)

    except Exception as exc:
        logger.warning('get_ab_test_destination error for %s: %s', getattr(qr, 'slug', '?'), exc)
        return (None, None)


def has_active_ab_test(qr) -> bool:
    """Return True if QR has an active ABTest with at least one variant."""
    try:
        from .models import ABTest
        ab = qr.ab_test
        return ab.is_active and bool(ab.variants)
    except Exception:
        return False


# ════════════════════════════════════════════════════════
# APP DEEP LINKING  (Feature 19)
# ════════════════════════════════════════════════════════

def get_deep_link_config(qr, user_agent: str) -> dict | None:
    """
    Return deep link config dict for the given QR + user agent, or None.

    Returns: {
        'deep_link': 'myapp://path' or 'https://app.example.com/path',
        'fallback_url': 'https://...',
        'platform': 'ios' | 'android' | 'other',
    }
    """
    try:
        from .models import DeepLink

        try:
            dl = qr.deep_link
        except DeepLink.DoesNotExist:
            return None

        if not dl.is_active:
            return None

        ua = user_agent.lower()

        # Detect platform
        is_ios = any(k in ua for k in ('iphone', 'ipad', 'ipod'))
        is_android = 'android' in ua

        if is_ios:
            link = dl.ios_deep_link or dl.custom_uri
            fallback = dl.ios_fallback_url or dl.fallback_url
            if link:
                logger.info('[DeepLink] iOS detected → %s (fallback=%s) for QR %s',
                            link[:80], (fallback or '(none)')[:60], getattr(qr, 'slug', '?'))
                return {'deep_link': link, 'fallback_url': fallback or '', 'platform': 'ios'}

        elif is_android:
            link = dl.android_deep_link or dl.custom_uri
            fallback = dl.android_fallback_url or dl.fallback_url
            if link:
                logger.info('[DeepLink] Android detected → %s (fallback=%s) for QR %s',
                            link[:80], (fallback or '(none)')[:60], getattr(qr, 'slug', '?'))
                return {'deep_link': link, 'fallback_url': fallback or '', 'platform': 'android'}

        # Desktop / other — try custom_uri, then just fallback
        if dl.custom_uri:
            logger.info('[DeepLink] Other platform → custom_uri %s for QR %s',
                        dl.custom_uri[:80], getattr(qr, 'slug', '?'))
            return {'deep_link': dl.custom_uri, 'fallback_url': dl.fallback_url or '', 'platform': 'other'}

        # No deep link applicable — return None so normal routing continues
        if dl.fallback_url:
            logger.info('[DeepLink] No deep link for UA, using fallback %s for QR %s',
                        dl.fallback_url[:80], getattr(qr, 'slug', '?'))
            return {'deep_link': '', 'fallback_url': dl.fallback_url, 'platform': 'other'}

        return None

    except Exception as exc:
        logger.warning('get_deep_link_config error for %s: %s', getattr(qr, 'slug', '?'), exc)
        return None


def has_active_deep_link(qr) -> bool:
    """Return True if QR has an active DeepLink with at least one configured link."""
    try:
        from .models import DeepLink
        dl = qr.deep_link
        return dl.is_active and bool(
            dl.ios_deep_link or dl.android_deep_link or dl.custom_uri
        )
    except Exception:
        return False


# ── Expiry-Based QR (Feature 21) ─────────────────────

def has_active_expiry(qr) -> bool:
    """Return True if QR has an active QRExpiry config."""
    try:
        exp = qr.expiry
        return exp.is_active
    except Exception:
        return False


def check_qr_expiry(qr) -> dict:
    """
    Check whether a QR code has expired based on its QRExpiry config.

    Returns {'expired': True, 'reason': '...', 'redirect_url': '...'} or
            {'expired': False}.
    """
    try:
        exp = qr.expiry
    except Exception:
        return {'expired': False}

    if not exp.is_active:
        return {'expired': False}

    if exp.is_expired():
        reason_map = {
            'date': 'This QR code expired on ' + (str(exp.expiry_date) if exp.expiry_date else 'unknown date'),
            'datetime': 'This QR code expired at ' + (str(exp.expiry_datetime) if exp.expiry_datetime else 'unknown time'),
            'scan_count': f'This QR code reached its scan limit ({exp.max_scans} scans)',
        }
        return {
            'expired': True,
            'reason': reason_map.get(exp.expiry_type, 'expired'),
            'redirect_url': exp.expired_redirect_url or '',
        }

    return {'expired': False}


def increment_expiry_scan(qr):
    """Increment the scan counter on QRExpiry if it exists and uses scan_count mode."""
    try:
        exp = qr.expiry
        if exp.is_active and exp.expiry_type == 'scan_count':
            exp.increment_scan()
    except Exception:
        pass


# ── Short-Lived Token Redirect (Feature 20) ──────────

def has_active_token_redirect(qr) -> bool:
    """Return True if QR has an active TokenRedirect."""
    try:
        tr = qr.token_redirect
        return tr.is_active
    except Exception:
        return False


def check_token_redirect_exhausted(qr) -> dict:
    """
    Check whether the QR-level token redirect limits have been reached.

    Returns {'exhausted': True, 'reason': '...'} or {'exhausted': False}.
    This is a QR-level check (across ALL tokens / JTIs).
    """
    from .models import TokenRedirect, TokenUsage
    from django.utils import timezone as dj_tz
    from datetime import timedelta

    try:
        tr = qr.token_redirect
    except Exception:
        return {'exhausted': False}

    if not tr.is_active:
        return {'exhausted': False}

    if tr.mode == 'timed':
        if tr.first_used_at:
            expiry_time = tr.first_used_at + timedelta(seconds=tr.ttl_seconds)
            if dj_tz.now() > expiry_time:
                return {'exhausted': True, 'reason': 'expired'}

    elif tr.mode == 'single_use':
        usage_count = TokenUsage.objects.filter(token_redirect=tr).count()
        if usage_count >= 1:
            return {'exhausted': True, 'reason': 'already_used'}

    elif tr.mode == 'limited_sessions':
        usage_count = TokenUsage.objects.filter(token_redirect=tr).count()
        if usage_count >= tr.max_uses:
            return {'exhausted': True, 'reason': 'max_uses_reached'}

    return {'exhausted': False}


# ════════════════════════════════════════════════════════
# POSTER / CREATIVE GENERATION (Feature 45)
# ════════════════════════════════════════════════════════

# Preset dimensions (width, height) in pixels
POSTER_PRESETS = {
    'flyer':        (1240, 1754),   # A4-ish at 150 dpi
    'poster':       (1500, 2100),   # Large portrait
    'banner':       (1920, 600),    # Wide landscape banner
    'social_square':(1080, 1080),   # Instagram / Facebook square
    'social_story': (1080, 1920),   # Instagram story / TikTok
    'facebook_cover':(1640, 624),   # Facebook cover photo
}


def generate_poster(qr, template: str = 'flyer', title: str = '',
                    subtitle: str = '', bg_color: str = '#1E293B',
                    accent_color: str = '#22D3EE', text_color: str = '#FFFFFF',
                    qr_size: int = 0) -> bytes:
    """
    Compose a poster/creative image with the QR code embedded.

    Returns PNG bytes.
    """
    W, H = POSTER_PRESETS.get(template, POSTER_PRESETS['flyer'])
    bg_rgb = _hex_to_rgb(bg_color)
    accent_rgb = _hex_to_rgb(accent_color)
    text_rgb = _hex_to_rgb(text_color)

    canvas = Image.new('RGB', (W, H), bg_rgb)
    draw = ImageDraw.Draw(canvas)

    # ── Generate QR image ──
    qr_box = max(8, min(20, W // 60))
    qr_img = _generate_base_qr_pil(qr, box_size=qr_box)
    qr_img = _apply_frame(qr_img, qr)
    if qr_img.mode == 'RGBA':
        qr_rgb = Image.new('RGB', qr_img.size, (255, 255, 255))
        qr_rgb.paste(qr_img, mask=qr_img.split()[3])
        qr_img = qr_rgb

    # ── Decide QR placement size ──
    if qr_size <= 0:
        target_qr = min(W, H) // 3
    else:
        target_qr = max(80, min(min(W, H) - 40, qr_size))
    qr_img = qr_img.resize((target_qr, target_qr), Image.LANCZOS)

    # ── Layout depends on template aspect ratio ──
    is_wide = W / H > 1.5
    is_tall = H / W > 1.5

    # ── Accent decorations ──
    if template in ('flyer', 'poster'):
        # Top accent bar
        draw.rectangle([0, 0, W, 12], fill=accent_rgb)
        # Bottom accent bar
        draw.rectangle([0, H - 12, W, H], fill=accent_rgb)
        # Side accent stripe
        draw.rectangle([0, 0, 8, H], fill=accent_rgb)

    elif template == 'banner':
        # Left accent block
        draw.rectangle([0, 0, 16, H], fill=accent_rgb)
        # Right accent block
        draw.rectangle([W - 16, 0, W, H], fill=accent_rgb)

    elif template.startswith('social'):
        # Corner accent triangles
        for i in range(40):
            draw.line([(0, i), (40 - i, 0)], fill=accent_rgb, width=1)
            draw.line([(W - 1, H - 1 - i), (W - 40 + i, H - 1)], fill=accent_rgb, width=1)
        # Accent circle top-right
        draw.ellipse([W - 120, -60, W + 60, 120], fill=accent_rgb + (80,) if canvas.mode == 'RGBA' else accent_rgb)

    elif template == 'facebook_cover':
        draw.rectangle([0, H - 8, W, H], fill=accent_rgb)

    # ── Title & Subtitle ──
    title_text = title or 'Scan Me'
    subtitle_text = subtitle or ''

    if is_wide:
        # Banner layout: text left, QR right
        title_font = _get_font(min(64, H // 5))
        sub_font = _get_font(min(32, H // 8))

        qr_x = W - target_qr - 60
        qr_y = (H - target_qr) // 2
        canvas.paste(qr_img, (qr_x, qr_y))
        # White border around QR
        draw.rectangle([qr_x - 4, qr_y - 4, qr_x + target_qr + 4, qr_y + target_qr + 4],
                       outline=(255, 255, 255), width=3)

        text_x = 60
        text_y = (H - 100) // 2
        draw.text((text_x, text_y), title_text, fill=text_rgb, font=title_font)
        if subtitle_text:
            draw.text((text_x, text_y + 70), subtitle_text, fill=text_rgb, font=sub_font)

    elif is_tall:
        # Tall layout: title top, QR center, subtitle bottom
        title_font = _get_font(min(72, W // 10))
        sub_font = _get_font(min(36, W // 18))

        # Title
        bb = draw.textbbox((0, 0), title_text, font=title_font)
        tw = bb[2] - bb[0]
        title_y = int(H * 0.12)
        draw.text(((W - tw) // 2, title_y), title_text, fill=text_rgb, font=title_font)

        # Accent line under title
        line_y = title_y + (bb[3] - bb[1]) + 20
        lw = min(tw + 40, W - 80)
        draw.rectangle([(W - lw) // 2, line_y, (W + lw) // 2, line_y + 4], fill=accent_rgb)

        # QR centered
        qr_x = (W - target_qr) // 2
        qr_y = (H - target_qr) // 2 - 20
        # White rounded background behind QR
        pad = 20
        draw.rounded_rectangle(
            [qr_x - pad, qr_y - pad, qr_x + target_qr + pad, qr_y + target_qr + pad],
            radius=16, fill=(255, 255, 255))
        canvas.paste(qr_img, (qr_x, qr_y))

        # Subtitle
        if subtitle_text:
            bb2 = draw.textbbox((0, 0), subtitle_text, font=sub_font)
            sw = bb2[2] - bb2[0]
            sub_y = qr_y + target_qr + pad + 40
            draw.text(((W - sw) // 2, sub_y), subtitle_text, fill=text_rgb, font=sub_font)

    else:
        # Square / default layout: title top, QR center-bottom
        title_font = _get_font(min(64, W // 12))
        sub_font = _get_font(min(32, W // 20))

        # Title
        bb = draw.textbbox((0, 0), title_text, font=title_font)
        tw = bb[2] - bb[0]
        title_y = int(H * 0.10)
        draw.text(((W - tw) // 2, title_y), title_text, fill=text_rgb, font=title_font)

        # Accent underline
        line_y = title_y + (bb[3] - bb[1]) + 16
        lw = min(tw + 30, W - 60)
        draw.rectangle([(W - lw) // 2, line_y, (W + lw) // 2, line_y + 3], fill=accent_rgb)

        # Subtitle
        sub_y = line_y + 24
        if subtitle_text:
            bb2 = draw.textbbox((0, 0), subtitle_text, font=sub_font)
            sw = bb2[2] - bb2[0]
            draw.text(((W - sw) // 2, sub_y), subtitle_text, fill=text_rgb, font=sub_font)

        # QR centered lower half
        qr_x = (W - target_qr) // 2
        qr_y = int(H * 0.45)
        pad = 16
        draw.rounded_rectangle(
            [qr_x - pad, qr_y - pad, qr_x + target_qr + pad, qr_y + target_qr + pad],
            radius=12, fill=(255, 255, 255))
        canvas.paste(qr_img, (qr_x, qr_y))

    # ── Branding watermark ──
    wm_font = _get_font(14)
    wm_text = 'Made with QRGenie'
    bb = draw.textbbox((0, 0), wm_text, font=wm_font)
    wm_w = bb[2] - bb[0]
    draw.text((W - wm_w - 16, H - 28), wm_text,
              fill=tuple(max(0, c - 60) for c in bg_rgb) if sum(bg_rgb) > 380
              else tuple(min(255, c + 60) for c in bg_rgb),
              font=wm_font)

    buf = io.BytesIO()
    canvas.save(buf, format='PNG')
    return buf.getvalue()


def generate_redirect_token(qr) -> str:
    """
    Generate a JWT token for a short-lived redirect.

    Token payload:
      - slug: QR slug
      - qr_id: QR UUID
      - jti: unique token ID (for single-use tracking)
      - mode: timed | single_use | limited_sessions
      - max_uses: allowed redemptions
      - exp: expiration timestamp
      - iat: issued-at timestamp

    Signed with Django SECRET_KEY using HS256.
    """
    import jwt
    from datetime import datetime, timedelta, timezone as dt_tz

    try:
        tr = qr.token_redirect
    except Exception:
        return ''

    # Stamp first_used_at on the very first scan
    if not tr.first_used_at:
        from django.utils import timezone as dj_tz
        tr.first_used_at = dj_tz.now()
        tr.save(update_fields=['first_used_at'])

    now = datetime.now(dt_tz.utc)
    payload = {
        'slug': qr.slug,
        'qr_id': str(qr.id),
        'jti': uuid.uuid4().hex,
        'mode': tr.mode,
        'max_uses': tr.max_uses,
        'exp': now + timedelta(seconds=tr.ttl_seconds),
        'iat': now,
    }

    from django.conf import settings
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    return token


def validate_redirect_token(token_str: str, slug: str, client_ip: str = '') -> dict:
    """
    Validate a JWT redirect token.

    Returns dict:
      - valid: bool
      - reason: str (only if invalid)
      - payload: dict (only if valid)

    Checks:
      1. JWT signature + expiry (PyJWT handles this)
      2. Slug matches
      3. Single-use: jti not already recorded in TokenUsage
      4. Limited sessions: usage count < max_uses
    """
    import jwt
    from django.conf import settings
    from .models import TokenRedirect, TokenUsage

    # 1. Decode & verify signature + expiry
    try:
        payload = jwt.decode(token_str, settings.SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return {'valid': False, 'reason': 'expired'}
    except jwt.InvalidTokenError:
        return {'valid': False, 'reason': 'invalid'}

    # 2. Slug must match
    if payload.get('slug') != slug:
        return {'valid': False, 'reason': 'slug_mismatch'}

    jti = payload.get('jti', '')
    mode = payload.get('mode', 'timed')
    max_uses = payload.get('max_uses', 1)
    qr_id = payload.get('qr_id', '')

    # 3. For timed mode, JWT expiry is sufficient — no usage tracking needed
    if mode == 'timed':
        return {'valid': True, 'payload': payload}

    # 4. Look up the TokenRedirect to query usages
    try:
        tr = TokenRedirect.objects.get(qr_code_id=qr_id)
    except TokenRedirect.DoesNotExist:
        return {'valid': False, 'reason': 'config_missing'}

    # 5. Single-use: check if this jti has been used
    if mode == 'single_use':
        used = TokenUsage.objects.filter(token_redirect=tr, jti=jti).exists()
        if used:
            return {'valid': False, 'reason': 'already_used'}

    # 6. Limited sessions: count usages for this jti
    if mode == 'limited_sessions':
        usage_count = TokenUsage.objects.filter(token_redirect=tr, jti=jti).count()
        if usage_count >= max_uses:
            return {'valid': False, 'reason': 'max_uses_reached'}

    return {'valid': True, 'payload': payload}


def record_token_usage(qr_id: str, jti: str, client_ip: str = '', session_key: str = ''):
    """Record a token redemption in the TokenUsage table."""
    from .models import TokenRedirect, TokenUsage

    try:
        tr = TokenRedirect.objects.get(qr_code_id=qr_id)
        TokenUsage.objects.create(
            token_redirect=tr,
            jti=jti,
            ip_address=client_ip or None,
            session_key=session_key,
        )
    except Exception as exc:
        logger.warning('record_token_usage error: %s', exc)


# ════════════════════════════════════════════════════════
# SCAN ALERT NOTIFICATIONS (Feature 25)
# ════════════════════════════════════════════════════════

def send_scan_alert_email(qr_id: str, ip: str = '', city: str = '', country: str = ''):
    """
    Check if a QR code has an active ScanAlert config and send email
    notifications for triggered events.
    Runs inside the background scan-recording thread.
    """
    from django.conf import settings as django_settings
    from django.db.models import F
    from django.utils import timezone
    from .models import QRCode, ScanAlert

    try:
        alert = ScanAlert.objects.select_related('qr_code').get(
            qr_code_id=qr_id, is_active=True,
        )
    except ScanAlert.DoesNotExist:
        return  # No alert configured — skip

    if not alert.alert_events or not alert.email_recipients:
        return  # Nothing to do

    # Parse recipient emails
    recipients = [e.strip() for e in alert.email_recipients.split(',') if e.strip()]
    if not recipients:
        return

    qr = alert.qr_code
    now = timezone.now()

    # Cooldown check — don't spam
    if alert.last_notified_at:
        elapsed = (now - alert.last_notified_at).total_seconds()
        if elapsed < alert.cooldown_minutes * 60:
            return  # Still in cooldown window

    triggered_events = []
    total_scans = qr.total_scans  # Already incremented before this call

    # Check each configured event
    events = alert.alert_events

    # 1. First scan
    if 'first_scan' in events and total_scans == 1:
        triggered_events.append('first_scan')

    # 2. Every scan
    if 'every_scan' in events:
        triggered_events.append('every_scan')

    # 3. Milestone: every N scans
    if 'milestone' in events and alert.milestone_every > 0:
        if total_scans % alert.milestone_every == 0:
            triggered_events.append('milestone')

    # 4. Scan spike: too many scans in a time window
    if 'scan_spike' in events:
        try:
            from apps.analytics.models import ScanEvent
            window_start = now - timezone.timedelta(minutes=alert.spike_window_minutes)
            recent_count = ScanEvent.objects.filter(
                qr_code_id=qr_id,
                scanned_at__gte=window_start,
            ).count()
            if recent_count >= alert.spike_threshold:
                triggered_events.append('scan_spike')
        except Exception:
            pass

    if not triggered_events:
        return

    # Build email
    event_labels = {
        'first_scan': '🎉 First Scan!',
        'every_scan': '📡 New Scan',
        'milestone': f'🏆 Milestone — {total_scans} scans',
        'scan_spike': '🚨 Scan Spike Detected',
    }
    event_summary = ', '.join(event_labels.get(e, e) for e in triggered_events)

    # Determine primary event for styling
    primary_event = triggered_events[0]
    event_colors = {
        'first_scan':  ('#059669', '#ECFDF5', '#D1FAE5'),
        'every_scan':  ('#2563EB', '#EFF6FF', '#DBEAFE'),
        'milestone':   ('#7C3AED', '#F5F3FF', '#EDE9FE'),
        'scan_spike':  ('#DC2626', '#FEF2F2', '#FEE2E2'),
    }
    accent, bg_light, badge_bg = event_colors.get(primary_event, ('#F59E0B', '#FFFBEB', '#FEF3C7'))

    event_icons = {
        'first_scan':  '🎉',
        'every_scan':  '📡',
        'milestone':   '🏆',
        'scan_spike':  '🚨',
    }

    # Build event badges HTML
    badges_html = ''
    for ev in triggered_events:
        ev_accent = event_colors.get(ev, ('#F59E0B', '#FFFBEB', '#FEF3C7'))[0]
        ev_badge_bg = event_colors.get(ev, ('#F59E0B', '#FFFBEB', '#FEF3C7'))[2]
        ev_icon = event_icons.get(ev, '🔔')
        ev_label = event_labels.get(ev, ev)
        badges_html += (
            f'<span style="display:inline-block;padding:6px 14px;margin:4px 4px 4px 0;'
            f'border-radius:20px;font-size:13px;font-weight:600;'
            f'background:{ev_badge_bg};color:{ev_accent};border:1px solid {ev_accent}22;">'
            f'{ev_icon} {ev_label}</span>'
        )

    location_str = f'{city}, {country}' if city or country else 'Unknown'
    scan_time = now.strftime('%B %d, %Y at %H:%M:%S UTC')

    subject = f"[QRGenie] {event_summary} — {qr.title}"

    # Plain text fallback
    body_plain = (
        f"QR Code: {qr.title}\n"
        f"Total Scans: {total_scans}\n"
        f"Events Triggered: {event_summary}\n"
        f"Scanner IP: {ip}\n"
        f"Location: {location_str}\n"
        f"Time: {scan_time}\n"
        f"\n—\nQRGenie Scan Alert System"
    )

    # Professional HTML email
    body_html = f'''<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#F3F4F6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F3F4F6;padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#FFFFFF;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,{accent},{ accent }cc);padding:32px 40px;text-align:center;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <div style="display:inline-block;width:56px;height:56px;line-height:56px;font-size:28px;background:rgba(255,255,255,0.2);border-radius:14px;margin-bottom:12px;">{event_icons.get(primary_event, '🔔')}</div>
    </td></tr>
    <tr><td align="center">
      <h1 style="margin:0;font-size:22px;font-weight:700;color:#FFFFFF;line-height:1.3;">{event_labels.get(primary_event, 'Scan Alert')}</h1>
      <p style="margin:6px 0 0;font-size:14px;color:rgba(255,255,255,0.85);">QR Code scan event detected</p>
    </td></tr>
    </table>
  </td></tr>

  <!-- QR Code Name -->
  <tr><td style="padding:28px 40px 0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F9FAFB;border-radius:12px;border:1px solid #E5E7EB;">
    <tr><td style="padding:16px 20px;">
      <p style="margin:0 0 2px;font-size:11px;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;color:#9CA3AF;">QR Code</p>
      <p style="margin:0;font-size:18px;font-weight:700;color:#111827;">{qr.title}</p>
    </td></tr>
    </table>
  </td></tr>

  <!-- Events Triggered -->
  <tr><td style="padding:20px 40px 0;">
    <p style="margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;color:#9CA3AF;">Events Triggered</p>
    {badges_html}
  </td></tr>

  <!-- Stats Grid -->
  <tr><td style="padding:24px 40px 0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td width="50%" style="padding-right:8px;">
        <div style="background:{bg_light};border:1px solid {accent}18;border-radius:12px;padding:18px 16px;text-align:center;">
          <p style="margin:0;font-size:28px;font-weight:800;color:{accent};">{total_scans:,}</p>
          <p style="margin:4px 0 0;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;font-weight:600;color:#6B7280;">Total Scans</p>
        </div>
      </td>
      <td width="50%" style="padding-left:8px;">
        <div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:12px;padding:18px 16px;text-align:center;">
          <p style="margin:0;font-size:28px;font-weight:800;color:#374151;">{alert.total_alerts_sent + 1}</p>
          <p style="margin:4px 0 0;font-size:11px;text-transform:uppercase;letter-spacing:0.6px;font-weight:600;color:#6B7280;">Alerts Sent</p>
        </div>
      </td>
    </tr>
    </table>
  </td></tr>

  <!-- Scan Details -->
  <tr><td style="padding:24px 40px 0;">
    <p style="margin:0 0 14px;font-size:12px;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;color:#9CA3AF;">Scan Details</p>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F9FAFB;border-radius:12px;border:1px solid #E5E7EB;overflow:hidden;">
    <tr>
      <td style="padding:12px 16px;border-bottom:1px solid #E5E7EB;width:36px;vertical-align:middle;">
        <span style="font-size:16px;">📍</span>
      </td>
      <td style="padding:12px 16px;border-bottom:1px solid #E5E7EB;">
        <p style="margin:0;font-size:11px;font-weight:600;color:#9CA3AF;text-transform:uppercase;letter-spacing:0.5px;">Location</p>
        <p style="margin:2px 0 0;font-size:14px;font-weight:600;color:#374151;">{location_str}</p>
      </td>
    </tr>
    <tr>
      <td style="padding:12px 16px;border-bottom:1px solid #E5E7EB;width:36px;vertical-align:middle;">
        <span style="font-size:16px;">🌐</span>
      </td>
      <td style="padding:12px 16px;border-bottom:1px solid #E5E7EB;">
        <p style="margin:0;font-size:11px;font-weight:600;color:#9CA3AF;text-transform:uppercase;letter-spacing:0.5px;">IP Address</p>
        <p style="margin:2px 0 0;font-size:14px;font-weight:600;color:#374151;">{ip or 'Unknown'}</p>
      </td>
    </tr>
    <tr>
      <td style="padding:12px 16px;width:36px;vertical-align:middle;">
        <span style="font-size:16px;">🕐</span>
      </td>
      <td style="padding:12px 16px;">
        <p style="margin:0;font-size:11px;font-weight:600;color:#9CA3AF;text-transform:uppercase;letter-spacing:0.5px;">Scanned At</p>
        <p style="margin:2px 0 0;font-size:14px;font-weight:600;color:#374151;">{scan_time}</p>
      </td>
    </tr>
    </table>
  </td></tr>

  <!-- CTA Button -->
  <tr><td style="padding:28px 40px 0;" align="center">
    <a href="https://qrgenie.pythonanywhere.com/qr/{qr.id}"
       style="display:inline-block;padding:14px 36px;font-size:14px;font-weight:700;color:#FFFFFF;
              background:{accent};border-radius:10px;text-decoration:none;
              box-shadow:0 2px 8px {accent}40;">
      View QR Code Details →
    </a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:28px 40px 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td style="border-top:1px solid #E5E7EB;padding-top:20px;text-align:center;">
      <p style="margin:0 0 4px;font-size:16px;font-weight:700;color:#374151;">⚡ QRGenie</p>
      <p style="margin:0;font-size:12px;color:#9CA3AF;line-height:1.5;">
        You are receiving this because scan alerts are enabled for this QR code.<br>
        Manage your alert settings in the QRGenie dashboard.
      </p>
    </td></tr>
    </table>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    try:
        from django.core.mail import EmailMultiAlternatives
        from_email = getattr(django_settings, 'DEFAULT_FROM_EMAIL', 'noreply@qrgenie.io')
        msg = EmailMultiAlternatives(subject, body_plain, from_email, recipients)
        msg.attach_alternative(body_html, 'text/html')
        msg.send(fail_silently=True)
        # Update stats
        ScanAlert.objects.filter(pk=alert.pk).update(
            last_notified_at=now,
            total_alerts_sent=F('total_alerts_sent') + 1,
        )
        logger.info(f"[ScanAlert] Sent alert for qr={qr_id} events={triggered_events}")
    except Exception as e:
        logger.error(f"[ScanAlert] Email send failed: {e}")


# ════════════════════════════════════════════════════════
# FEATURE CONFLICT DETECTION (Feature Priority System)
# ════════════════════════════════════════════════════════

# Canonical feature precedence order - matches redirect_views.py evaluation order
FEATURE_PRECEDENCE = {
    'paused': 1,
    'archived': 2,
    'builtin_expiry': 3,
    'expiry': 4,
    'password': 5,
    'token_redirect': 6,
    'gps_district': 7,
    'geo_fence': 8,
    'ab_test': 9,
    'deep_link': 10,
    'loyalty': 11,
    'vcard': 12,
    'product_auth': 13,
    'doc_upload': 14,
    'funnel': 15,
    'video': 16,
    'pdf': 17,
    'language_route': 18,
    'rotation': 19,
    'time_schedule': 20,
    'device_route': 21,
    'routing_rules': 22,
    'fallback': 23,
}

FEATURE_DISPLAY_NAMES = {
    'paused': 'Paused Status',
    'archived': 'Archived Status',
    'builtin_expiry': 'Built-in Expiry',
    'expiry': 'Expiry Settings',
    'password': 'Password Protection',
    'token_redirect': 'Token Redirect',
    'gps_district': 'GPS District Routing',
    'geo_fence': 'Geo-Fence',
    'ab_test': 'A/B Test',
    'deep_link': 'App Deep Link',
    'loyalty': 'Loyalty Program',
    'vcard': 'Digital vCard',
    'product_auth': 'Product Authentication',
    'doc_upload': 'Document Upload',
    'funnel': 'Funnel Pages',
    'video': 'Video Player',
    'pdf': 'PDF Viewer',
    'language_route': 'Geo/Language Routing',
    'rotation': 'Auto-Rotation',
    'time_schedule': 'Time Schedule',
    'device_route': 'Device Routing',
    'routing_rules': 'Routing Rules',
    'fallback': 'Default Destination',
}


def get_all_feature_status(qr) -> list:
    """
    Get status of all features for a QR code.
    Returns list of dicts with feature name, priority, is_active status, and extra info.
    """
    features = []

    # 1. Paused status
    features.append({
        'feature': 'paused',
        'priority': FEATURE_PRECEDENCE['paused'],
        'is_active': qr.status == 'paused',
        'display_name': FEATURE_DISPLAY_NAMES['paused'],
    })

    # 2. Archived status
    features.append({
        'feature': 'archived',
        'priority': FEATURE_PRECEDENCE['archived'],
        'is_active': qr.status == 'archived',
        'display_name': FEATURE_DISPLAY_NAMES['archived'],
    })

    # 3. Built-in expiry
    features.append({
        'feature': 'builtin_expiry',
        'priority': FEATURE_PRECEDENCE['builtin_expiry'],
        'is_active': qr.is_expired() if hasattr(qr, 'is_expired') else False,
        'display_name': FEATURE_DISPLAY_NAMES['builtin_expiry'],
    })

    # 4. Expiry config (Feature 21)
    try:
        exp = qr.expiry
        features.append({
            'feature': 'expiry',
            'priority': FEATURE_PRECEDENCE['expiry'],
            'is_active': exp.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['expiry'],
            'expiry_type': getattr(exp, 'expiry_type', None),
        })
    except Exception:
        features.append({
            'feature': 'expiry',
            'priority': FEATURE_PRECEDENCE['expiry'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['expiry'],
        })

    # 5. Password protection
    features.append({
        'feature': 'password',
        'priority': FEATURE_PRECEDENCE['password'],
        'is_active': bool(qr.is_password_protected),
        'display_name': FEATURE_DISPLAY_NAMES['password'],
    })

    # 6. Token redirect (Feature 20)
    try:
        tr = qr.token_redirect
        features.append({
            'feature': 'token_redirect',
            'priority': FEATURE_PRECEDENCE['token_redirect'],
            'is_active': tr.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['token_redirect'],
            'mode': getattr(tr, 'mode', None),
        })
    except Exception:
        features.append({
            'feature': 'token_redirect',
            'priority': FEATURE_PRECEDENCE['token_redirect'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['token_redirect'],
        })

    # 7. GPS district routing (part of language_route)
    try:
        lang_route = qr.language_route
        has_geo_direct = (
            lang_route.is_active
            and bool(getattr(lang_route, 'geo_direct', None))
            and any(bool((e.get('district') or '').strip()) for e in (lang_route.geo_direct or []))
        )
        features.append({
            'feature': 'gps_district',
            'priority': FEATURE_PRECEDENCE['gps_district'],
            'is_active': has_geo_direct,
            'display_name': FEATURE_DISPLAY_NAMES['gps_district'],
        })
    except Exception:
        features.append({
            'feature': 'gps_district',
            'priority': FEATURE_PRECEDENCE['gps_district'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['gps_district'],
        })

    # 8. Geo-fence (Feature 17)
    try:
        fence = qr.geo_fence
        features.append({
            'feature': 'geo_fence',
            'priority': FEATURE_PRECEDENCE['geo_fence'],
            'is_active': fence.is_active and bool(fence.zones),
            'display_name': FEATURE_DISPLAY_NAMES['geo_fence'],
            'zones_count': len(fence.zones) if fence.zones else 0,
        })
    except Exception:
        features.append({
            'feature': 'geo_fence',
            'priority': FEATURE_PRECEDENCE['geo_fence'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['geo_fence'],
        })

    # 9. A/B test (Feature 18)
    try:
        ab = qr.ab_test
        features.append({
            'feature': 'ab_test',
            'priority': FEATURE_PRECEDENCE['ab_test'],
            'is_active': ab.is_active and bool(ab.variants),
            'display_name': FEATURE_DISPLAY_NAMES['ab_test'],
            'variants_count': len(ab.variants) if ab.variants else 0,
        })
    except Exception:
        features.append({
            'feature': 'ab_test',
            'priority': FEATURE_PRECEDENCE['ab_test'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['ab_test'],
        })

    # 10. Deep link (Feature 19)
    try:
        dl = qr.deep_link
        features.append({
            'feature': 'deep_link',
            'priority': FEATURE_PRECEDENCE['deep_link'],
            'is_active': dl.is_active and bool(dl.ios_deep_link or dl.android_deep_link or dl.custom_uri),
            'display_name': FEATURE_DISPLAY_NAMES['deep_link'],
        })
    except Exception:
        features.append({
            'feature': 'deep_link',
            'priority': FEATURE_PRECEDENCE['deep_link'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['deep_link'],
        })

    # 11. Loyalty program (Feature 26)
    try:
        lp = qr.loyalty_program
        features.append({
            'feature': 'loyalty',
            'priority': FEATURE_PRECEDENCE['loyalty'],
            'is_active': lp.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['loyalty'],
        })
    except Exception:
        features.append({
            'feature': 'loyalty',
            'priority': FEATURE_PRECEDENCE['loyalty'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['loyalty'],
        })

    # 12. Digital vCard (Feature 28)
    try:
        vc = qr.vcard
        features.append({
            'feature': 'vcard',
            'priority': FEATURE_PRECEDENCE['vcard'],
            'is_active': vc.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['vcard'],
        })
    except Exception:
        features.append({
            'feature': 'vcard',
            'priority': FEATURE_PRECEDENCE['vcard'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['vcard'],
        })

    # 13. Product auth (Feature 31)
    try:
        pa = qr.product_auth
        features.append({
            'feature': 'product_auth',
            'priority': FEATURE_PRECEDENCE['product_auth'],
            'is_active': pa.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['product_auth'],
        })
    except Exception:
        features.append({
            'feature': 'product_auth',
            'priority': FEATURE_PRECEDENCE['product_auth'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['product_auth'],
        })

    # 14. Doc upload form (Feature 33)
    try:
        duf = qr.doc_upload_form
        features.append({
            'feature': 'doc_upload',
            'priority': FEATURE_PRECEDENCE['doc_upload'],
            'is_active': duf.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['doc_upload'],
        })
    except Exception:
        features.append({
            'feature': 'doc_upload',
            'priority': FEATURE_PRECEDENCE['doc_upload'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['doc_upload'],
        })

    # 15. Funnel pages (Feature 34)
    try:
        fc = qr.funnel_config
        features.append({
            'feature': 'funnel',
            'priority': FEATURE_PRECEDENCE['funnel'],
            'is_active': fc.is_active and fc.steps.exists(),
            'display_name': FEATURE_DISPLAY_NAMES['funnel'],
        })
    except Exception:
        features.append({
            'feature': 'funnel',
            'priority': FEATURE_PRECEDENCE['funnel'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['funnel'],
        })

    # 16. Video player
    try:
        vd = qr.video_document
        features.append({
            'feature': 'video',
            'priority': FEATURE_PRECEDENCE['video'],
            'is_active': vd.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['video'],
        })
    except Exception:
        features.append({
            'feature': 'video',
            'priority': FEATURE_PRECEDENCE['video'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['video'],
        })

    # 17. PDF viewer
    try:
        pdf = qr.pdf_document
        features.append({
            'feature': 'pdf',
            'priority': FEATURE_PRECEDENCE['pdf'],
            'is_active': pdf.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['pdf'],
        })
    except Exception:
        features.append({
            'feature': 'pdf',
            'priority': FEATURE_PRECEDENCE['pdf'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['pdf'],
        })

    # 18. Language/geo route
    try:
        lr = qr.language_route
        features.append({
            'feature': 'language_route',
            'priority': FEATURE_PRECEDENCE['language_route'],
            'is_active': lr.is_active and bool(lr.routes or lr.geo_fallback),
            'display_name': FEATURE_DISPLAY_NAMES['language_route'],
            'routes_count': len(lr.routes) if lr.routes else 0,
        })
    except Exception:
        features.append({
            'feature': 'language_route',
            'priority': FEATURE_PRECEDENCE['language_route'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['language_route'],
        })

    # 19. Rotation schedule
    try:
        rs = qr.rotation_schedule
        features.append({
            'feature': 'rotation',
            'priority': FEATURE_PRECEDENCE['rotation'],
            'is_active': rs.is_active and bool(rs.pages),
            'display_name': FEATURE_DISPLAY_NAMES['rotation'],
            'pages_count': len(rs.pages) if rs.pages else 0,
        })
    except Exception:
        features.append({
            'feature': 'rotation',
            'priority': FEATURE_PRECEDENCE['rotation'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['rotation'],
        })

    # 20. Time schedule
    try:
        ts = qr.time_schedule
        features.append({
            'feature': 'time_schedule',
            'priority': FEATURE_PRECEDENCE['time_schedule'],
            'is_active': ts.is_active and bool(ts.rules),
            'display_name': FEATURE_DISPLAY_NAMES['time_schedule'],
            'rules_count': len(ts.rules) if ts.rules else 0,
        })
    except Exception:
        features.append({
            'feature': 'time_schedule',
            'priority': FEATURE_PRECEDENCE['time_schedule'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['time_schedule'],
        })

    # 21. Device route
    try:
        dr = qr.device_route
        features.append({
            'feature': 'device_route',
            'priority': FEATURE_PRECEDENCE['device_route'],
            'is_active': dr.is_active,
            'display_name': FEATURE_DISPLAY_NAMES['device_route'],
        })
    except Exception:
        features.append({
            'feature': 'device_route',
            'priority': FEATURE_PRECEDENCE['device_route'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['device_route'],
        })

    # 22. Routing rules (legacy)
    try:
        has_rules = qr.routing_rules.exists()
        features.append({
            'feature': 'routing_rules',
            'priority': FEATURE_PRECEDENCE['routing_rules'],
            'is_active': has_rules,
            'display_name': FEATURE_DISPLAY_NAMES['routing_rules'],
        })
    except Exception:
        features.append({
            'feature': 'routing_rules',
            'priority': FEATURE_PRECEDENCE['routing_rules'],
            'is_active': False,
            'display_name': FEATURE_DISPLAY_NAMES['routing_rules'],
        })

    # 23. Fallback URL
    features.append({
        'feature': 'fallback',
        'priority': FEATURE_PRECEDENCE['fallback'],
        'is_active': bool(qr.destination_url or qr.fallback_url),
        'display_name': FEATURE_DISPLAY_NAMES['fallback'],
        'url': qr.destination_url or qr.fallback_url or '',
    })

    return sorted(features, key=lambda x: x['priority'])


def detect_feature_conflicts(features: list) -> list:
    """
    Detect which features are being blocked by higher-priority features.
    Returns list of conflict objects.
    """
    conflicts = []

    # Find the highest priority active feature
    highest_active = None
    for feat in features:
        if feat['is_active']:
            if highest_active is None or feat['priority'] < highest_active['priority']:
                highest_active = feat

    if not highest_active:
        return []

    # Find all active features that are blocked by the highest priority one
    for feat in features:
        if feat['is_active'] and feat['priority'] > highest_active['priority']:
            # Skip fallback as it's not really a "feature" that conflicts
            if feat['feature'] == 'fallback':
                continue
            conflicts.append({
                'feature': feat['feature'],
                'priority': feat['priority'],
                'display_name': feat['display_name'],
                'blocked_by': highest_active['feature'],
                'blocked_by_priority': highest_active['priority'],
                'blocked_by_display_name': highest_active['display_name'],
                'message': f"This feature is blocked by {highest_active['display_name']} (priority #{highest_active['priority']})",
            })

    return conflicts


def simulate_redirect(qr, params: dict) -> dict:
    """
    Simulate the redirect engine without recording analytics.
    Returns which feature would handle the scan and the destination.
    """
    user_agent = params.get('user_agent', '')
    ua_lower = user_agent.lower()
    country = params.get('country', '')
    region = params.get('region', '')
    city = params.get('city', '')
    accept_language = params.get('accept_language', 'en-US')
    latitude = params.get('latitude')
    longitude = params.get('longitude')

    # Parse device info
    is_mobile = any(m in ua_lower for m in ['mobile', 'android', 'iphone', 'ipad'])
    device_type = 'mobile' if is_mobile else 'desktop'
    platform = 'ios' if 'iphone' in ua_lower or 'ipad' in ua_lower else 'android' if 'android' in ua_lower else 'other'

    simulation_context = {
        'device_type': device_type,
        'platform': platform,
        'country': country,
        'region': region,
        'city': city,
        'latitude': latitude,
        'longitude': longitude,
        'accept_language': accept_language,
    }

    # Get all feature statuses
    features = get_all_feature_status(qr)
    conflicts = detect_feature_conflicts(features)

    # Simulate the precedence chain
    matched_feature = None
    destination = None

    # 1. Check paused
    if qr.status == 'paused':
        return {
            'destination': None,
            'matched_feature': 'paused',
            'matched_feature_display': 'Paused Status',
            'matched_feature_priority': 1,
            'blocked_features': [],
            'active_features': features,
            'simulation_context': simulation_context,
            'error': 'QR code is paused',
        }

    # 2. Check archived
    if qr.status == 'archived':
        return {
            'destination': None,
            'matched_feature': 'archived',
            'matched_feature_display': 'Archived Status',
            'matched_feature_priority': 2,
            'blocked_features': [],
            'active_features': features,
            'simulation_context': simulation_context,
            'error': 'QR code is archived',
        }

    # 3. Check built-in expiry
    if hasattr(qr, 'is_expired') and qr.is_expired():
        return {
            'destination': None,
            'matched_feature': 'builtin_expiry',
            'matched_feature_display': 'Built-in Expiry',
            'matched_feature_priority': 3,
            'blocked_features': [],
            'active_features': features,
            'simulation_context': simulation_context,
            'error': 'QR code has expired',
        }

    # 4. Check expiry config
    if has_active_expiry(qr):
        result = check_qr_expiry(qr)
        if result.get('expired'):
            return {
                'destination': result.get('redirect_url', ''),
                'matched_feature': 'expiry',
                'matched_feature_display': 'Expiry Settings',
                'matched_feature_priority': 4,
                'blocked_features': conflicts,
                'active_features': features,
                'simulation_context': simulation_context,
            }

    # 5. Check password
    if qr.is_password_protected:
        return {
            'destination': None,
            'matched_feature': 'password',
            'matched_feature_display': 'Password Protection',
            'matched_feature_priority': 5,
            'blocked_features': conflicts,
            'active_features': features,
            'simulation_context': simulation_context,
            'error': 'Password required',
        }

    # 6. Check token redirect
    if has_active_token_redirect(qr):
        matched_feature = 'token_redirect'
        destination = 'Token gate page (JWT required)'

    # 7. Check GPS district routing
    if not matched_feature:
        try:
            lang_route = qr.language_route
            has_geo_direct = (
                lang_route.is_active
                and bool(getattr(lang_route, 'geo_direct', None))
                and any(bool((e.get('district') or '').strip()) for e in (lang_route.geo_direct or []))
            )
            if has_geo_direct:
                matched_feature = 'gps_district'
                destination = 'GPS permission page'
        except Exception:
            pass

    # 8. Check geo-fence
    if not matched_feature and has_active_geofence(qr):
        matched_feature = 'geo_fence'
        if latitude and longitude:
            dest = get_geofence_destination(qr, float(latitude), float(longitude))
            destination = dest or 'GPS permission page (no zone match)'
        else:
            destination = 'GPS permission page'

    # 9. Check A/B test
    if not matched_feature and has_active_ab_test(qr):
        matched_feature = 'ab_test'
        dest, _ = get_ab_test_destination(qr, None)
        destination = dest or 'A/B variant URL'

    # 10. Check deep link
    if not matched_feature and has_active_deep_link(qr):
        matched_feature = 'deep_link'
        dl_config = get_deep_link_config(qr, user_agent)
        if dl_config:
            destination = dl_config.get('deep_link') or dl_config.get('fallback_url', '')
        else:
            destination = 'Deep link interstitial'

    # 11. Check loyalty
    if not matched_feature:
        try:
            lp = qr.loyalty_program
            if lp.is_active:
                matched_feature = 'loyalty'
                destination = 'Loyalty scan page'
        except Exception:
            pass

    # 12. Check vCard
    if not matched_feature:
        try:
            vc = qr.vcard
            if vc.is_active:
                matched_feature = 'vcard'
                destination = 'Digital vCard page'
        except Exception:
            pass

    # 13. Check product auth
    if not matched_feature:
        try:
            pa = qr.product_auth
            if pa.is_active:
                matched_feature = 'product_auth'
                destination = 'Product verification page'
        except Exception:
            pass

    # 14. Check doc upload
    if not matched_feature:
        try:
            duf = qr.doc_upload_form
            if duf.is_active:
                matched_feature = 'doc_upload'
                destination = 'Document upload form'
        except Exception:
            pass

    # 15. Check funnel
    if not matched_feature:
        try:
            fc = qr.funnel_config
            if fc.is_active and fc.steps.exists():
                matched_feature = 'funnel'
                destination = 'Funnel page'
        except Exception:
            pass

    # 16. Check video
    if not matched_feature:
        dest = get_video_destination(qr)
        if dest:
            matched_feature = 'video'
            destination = dest

    # 17. Check PDF
    if not matched_feature:
        dest = get_pdf_destination(qr)
        if dest:
            matched_feature = 'pdf'
            destination = dest

    # 18. Check language route
    if not matched_feature:
        dest = get_language_destination(qr, accept_language, country, region, city)
        if dest:
            matched_feature = 'language_route'
            destination = dest

    # 19. Check rotation
    if not matched_feature:
        dest = get_rotation_destination(qr)
        if dest:
            matched_feature = 'rotation'
            destination = dest

    # 20. Check time schedule
    if not matched_feature:
        dest = get_time_destination(qr)
        if dest:
            matched_feature = 'time_schedule'
            destination = dest

    # 21. Check device route
    if not matched_feature:
        dest = get_device_destination(qr, user_agent)
        if dest:
            matched_feature = 'device_route'
            destination = dest

    # 22. Check routing rules
    if not matched_feature:
        minimal_context = {
            'device_type': device_type,
            'country': country,
            'language': accept_language[:10] if accept_language else 'en',
        }
        dest = evaluate_rules(qr, minimal_context)
        if dest:
            matched_feature = 'routing_rules'
            destination = dest

    # 23. Fallback
    if not matched_feature:
        matched_feature = 'fallback'
        destination = qr.destination_url or qr.fallback_url or ''

    return {
        'destination': destination,
        'matched_feature': matched_feature,
        'matched_feature_display': FEATURE_DISPLAY_NAMES.get(matched_feature, matched_feature),
        'matched_feature_priority': FEATURE_PRECEDENCE.get(matched_feature, 99),
        'blocked_features': conflicts,
        'active_features': features,
        'simulation_context': simulation_context,
    }
