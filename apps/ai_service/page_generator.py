"""
QRGenie — Landing Page Generator v3
======================================
Generates beautiful, mobile-responsive HTML pages for 6 QR page types
using 5 structurally distinct design templates — matching the frontend preview.

Designs (theme name → visual style):
  gradient  — Hero Card:       gradient header + white card body
  dark      — Cyber Dark:      space-black bg, neon glow, mono font
  minimal   — Editorial:       pure white page, masthead, oversized typography
  vibrant   — Poster:          full-bleed gradient hero + white bottom sheet
  ocean     — Glassmorphism:   radial-gradient bg + frosted glass card

Page types:
  multi_link    — Bio/linktree with multiple buttons (4 layout variants)
  payment       — UPI / Razorpay / Stripe payment page
  file_delivery — Download page for PDF/video/image/APK
  password      — Password-protected reveal page
  product       — Product detail page
  chat          — Chat app launcher (WhatsApp / Telegram / Messenger)
"""
import html as _html_lib

# ─────────────────────────── Palette lookup ──────────────────────────────────

_PALETTES = {
    "gradient": {"accent": "#6366f1", "bg": "#eef2ff"},
    "dark":     {"accent": "#818cf8", "bg": "#080814"},
    "minimal":  {"accent": "#111827", "bg": "#ffffff"},
    "vibrant":  {"accent": "#f97316", "bg": "#fff7ed"},
    "ocean":    {"accent": "#0891b2", "bg": "#0c4a6e"},
    # legacy / fallback names
    "rose":     {"accent": "#f43f5e", "bg": "#fff1f2"},
    "forest":   {"accent": "#16a34a", "bg": "#f0fdf4"},
    "sunset":   {"accent": "#d97706", "bg": "#fefce8"},
}

# Keep THEMES alias for any external code that imports it
THEMES = {k: {"primary": v["accent"], "bg": v["bg"],
              "card_bg": "#ffffff", "text": "#111827", "subtext": "#6b7280",
              "btn_text": "#ffffff", "border": v["accent"] + "28",
              "shadow": "0 8px 32px " + v["accent"] + "22",
              "header_bg": "linear-gradient(135deg," + v["accent"] + " 0%," + v["accent"] + "aa 100%)",
              "header_text": "#ffffff"}
         for k, v in _PALETTES.items()}


def _e(s):
    """HTML-escape."""
    return _html_lib.escape(str(s) if s is not None else "")


def _resolve(theme_name: str, accent_override=None, bg_override=None):
    """Return (accent, bg), honouring per-user colour overrides."""
    pal = _PALETTES.get(theme_name, _PALETTES["gradient"])
    accent = (accent_override
              if accent_override and accent_override.startswith("#") and len(accent_override) in (4, 7)
              else pal["accent"])
    bg = (bg_override
          if bg_override and bg_override.startswith("#") and len(bg_override) in (4, 7)
          else pal["bg"])
    return accent, bg


# Kept for any external callers that import _theme
def _theme(name: str, accent_color: str = None, bg_color: str = None) -> dict:
    t = dict(THEMES.get(name, THEMES["gradient"]))
    a, b = _resolve(name, accent_color, bg_color)
    t["primary"] = t["primary_dark"] = a
    t["bg"] = b
    t["header_bg"] = f"linear-gradient(135deg,{a} 0%,{a}aa 100%)"
    t["border"] = a + "33"
    return t


# ─────────────────────────── 5 Design chrome functions ───────────────────────

_SHARED_JS_STYLES = """
  #error-msg{color:#ef4444;font-size:.85rem;margin-bottom:12px;display:none}
  #content-section{display:none}
"""


def _design_gradient(page_title, title, subtitle, icon, inner_html, accent, bg):
    """Hero Card — gradient header, white card body."""
    grad = f"linear-gradient(135deg,{accent} 0%,{accent}aa 100%)"
    return f"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{page_title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:{bg};min-height:100vh;
         display:flex;align-items:center;justify-content:center;padding:20px 14px}}
    .card{{background:#fff;border-radius:24px;max-width:440px;width:100%;
          box-shadow:0 16px 56px {accent}22,0 2px 8px {accent}10;
          border:1.5px solid {accent}14;overflow:hidden}}
    .hdr{{background:{grad};padding:32px 24px 40px;text-align:center;position:relative}}
    .hdr::after{{content:'';position:absolute;bottom:-1px;left:0;right:0;height:24px;
                background:#fff;border-radius:24px 24px 0 0}}
    .ico-wrap{{width:64px;height:64px;border-radius:20px;
               background:rgba(255,255,255,.22);display:flex;
               align-items:center;justify-content:center;
               margin:0 auto 14px;font-size:30px;
               box-shadow:0 4px 16px rgba(0,0,0,.12)}}
    .hdr h1{{color:#fff;font-size:21px;font-weight:800;margin-bottom:4px}}
    .hdr p{{color:rgba(255,255,255,.78);font-size:13px}}
    .body{{padding:8px 22px 22px}}
    .amount-box{{display:flex;align-items:center;justify-content:space-between;
                background:{accent}0e;border:1.5px solid {accent}28;
                border-radius:16px;padding:16px 20px;margin-bottom:18px}}
    .albl{{color:#6b7280;font-size:11px;font-weight:700;
           letter-spacing:.1em;text-transform:uppercase}}
    .aval{{color:{accent};font-size:32px;font-weight:900;line-height:1;margin-top:4px}}
    .amount-badge{{display:none}}
    .btn,.btn-custom{{display:flex;align-items:center;justify-content:center;gap:9px;
         width:100%;padding:15px;border-radius:14px;
         background:{accent};color:#fff;font-size:15px;font-weight:700;
         margin-bottom:10px;letter-spacing:.01em;text-decoration:none;
         border:none;cursor:pointer;transition:opacity .15s}}
    .btn:hover,.btn-custom:hover{{opacity:.9}}
    .btn-outline{{display:flex;align-items:center;justify-content:center;gap:9px;
                  width:100%;padding:13px;border-radius:14px;
                  background:transparent;color:{accent};font-size:14px;font-weight:600;
                  border:2px solid {accent}45;text-decoration:none;margin-bottom:10px}}
    .note{{color:#9ca3af;font-size:11px;text-align:center;line-height:1.7;margin-top:12px}}
    .rule{{display:none}}
    .file-box{{display:flex;align-items:center;gap:14px;
               background:{bg};border:1px solid {accent}28;
               border-radius:14px;padding:16px;margin-bottom:20px}}
    .file-icon{{font-size:2.8rem;line-height:1}}
    .file-meta strong{{display:block;font-size:1rem;font-weight:700;color:#111827}}
    .file-meta span{{font-size:.82rem;color:#6b7280}}
    .unlock-input{{width:100%;padding:14px;border:2px solid {accent}28;
                   border-radius:12px;font-size:1rem;background:{bg};color:#111;
                   outline:none;margin-bottom:12px}}
    .unlock-input:focus{{border-color:{accent}}}
    .hint{{font-size:.82rem;color:#6b7280;text-align:center;margin-top:12px;line-height:1.5}}
    .content-body{{font-size:.95rem;line-height:1.7;color:#111;
                   background:{bg};border-radius:12px;padding:16px;
                   border:1px solid {accent}28;margin-bottom:16px}}
    .feat-list{{list-style:none;margin-bottom:20px}}
    .feat-list li{{display:flex;align-items:center;gap:8px;
                   padding:10px 0;border-bottom:1px solid {accent}18;
                   font-size:.95rem;color:#374151}}
    .feat-check{{color:{accent}}}
    .product-img{{width:100%;max-height:220px;object-fit:cover;
                  border-radius:12px;margin-bottom:16px}}
    .badge-tag{{display:inline-block;background:{accent};color:#fff;
                border-radius:6px;padding:3px 10px;font-size:.75rem;font-weight:700;
                margin-bottom:12px}}
    .sub-desc{{font-size:.85rem;color:#6b7280;margin-bottom:4px}}
    {_SHARED_JS_STYLES}
    .foot{{text-align:center;padding:12px;font-size:10.5px;color:#d1d5db;
           border-top:1px solid {accent}12;margin-top:8px}}
    .foot a,.foot b{{color:{accent};text-decoration:none}}
  </style>
</head><body>
<div class="card">
  <div class="hdr">
    <div class="ico-wrap">{icon}</div>
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="body">{inner_html}</div>
  <div class="foot">Powered by <a href="https://qrgenie.io" target="_blank"><b>QRGenie</b></a></div>
</div>
</body></html>"""


def _design_dark(page_title, title, subtitle, inner_html, accent, bg):
    """Cyber Dark — space-black bg, neon glow, monospace."""
    hex_no_hash = accent.lstrip('#')
    return f"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{page_title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Courier New',Courier,monospace;
         background:#07071a url("data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 20h40M20 0v40' stroke='%23{hex_no_hash}' stroke-opacity='.06' stroke-width='1'/%3E%3C/svg%3E");
         min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px 16px}}
    .card{{max-width:440px;width:100%;border-radius:18px;overflow:hidden;
          border:1px solid {accent}60;
          box-shadow:0 0 0 1px {accent}20,0 0 60px {accent}25,inset 0 1px 0 {accent}40}}
    .hdr{{background:linear-gradient(180deg,{accent}22 0%,{accent}06 100%);
          padding:28px 22px 22px;border-bottom:1px solid {accent}40;
          position:relative;overflow:hidden}}
    .scanline{{position:absolute;top:0;left:0;right:0;height:2px;
               background:linear-gradient(90deg,transparent,{accent}cc,transparent);opacity:.8}}
    .tag{{display:inline-flex;align-items:center;gap:6px;color:{accent};
          font-size:10px;font-weight:700;letter-spacing:.2em;text-transform:uppercase;
          margin-bottom:10px}}
    .tag::before{{content:'▶';font-size:8px}}
    .hdr h1{{color:#fff;font-size:20px;font-weight:800;letter-spacing:.04em;margin-bottom:4px}}
    .hdr p{{color:rgba(255,255,255,.38);font-size:11px;letter-spacing:.08em}}
    .body{{background:#0d0d22;padding:22px}}
    .amount-box{{background:#000;border:1px solid {accent}50;border-radius:12px;
                padding:18px 20px;margin-bottom:18px;
                box-shadow:inset 0 2px 8px rgba(0,0,0,.6),0 0 20px {accent}12}}
    .albl{{color:{accent}80;font-size:10px;letter-spacing:.18em;text-transform:uppercase;
           margin-bottom:8px}}
    .aval{{color:{accent};font-size:36px;font-weight:900;
           text-shadow:0 0 20px {accent},0 0 40px {accent}80;letter-spacing:.02em}}
    .amount-badge{{display:none}}
    .rule{{border:none;height:1px;
           background:linear-gradient(90deg,transparent,{accent}40,transparent);
           margin:2px 0 18px;display:block}}
    .btn,.btn-custom{{display:flex;align-items:center;justify-content:center;gap:9px;
         width:100%;padding:14px;border-radius:10px;
         background:{accent};color:#07071a;font-size:14px;font-weight:800;
         margin-bottom:10px;letter-spacing:.04em;text-transform:uppercase;
         box-shadow:0 0 24px {accent}55;text-decoration:none;border:none;cursor:pointer}}
    .btn-outline{{display:flex;align-items:center;justify-content:center;gap:9px;
                  width:100%;padding:13px;border-radius:10px;
                  background:transparent;color:{accent};font-size:13px;font-weight:700;
                  border:1px solid {accent}60;letter-spacing:.04em;text-transform:uppercase;
                  text-decoration:none;margin-bottom:10px}}
    .note{{color:{accent}55;font-size:10px;text-align:center;line-height:1.8;margin-top:14px;letter-spacing:.06em}}
    .file-box{{display:flex;align-items:center;gap:14px;
               background:#000;border:1px solid {accent}40;
               border-radius:12px;padding:16px;margin-bottom:18px}}
    .file-icon{{font-size:2.4rem;line-height:1}}
    .file-meta strong{{display:block;font-size:.95rem;font-weight:700;color:#fff;letter-spacing:.05em}}
    .file-meta span{{font-size:.78rem;color:{accent}80;letter-spacing:.12em;text-transform:uppercase}}
    .unlock-input{{width:100%;padding:14px;border:1px solid {accent}50;
                   border-radius:10px;font-size:.9rem;background:#000;color:{accent};
                   outline:none;margin-bottom:12px;letter-spacing:.04em;font-family:'Courier New',monospace}}
    .unlock-input:focus{{border-color:{accent};box-shadow:0 0 12px {accent}30}}
    .unlock-input::placeholder{{color:{accent}40}}
    .hint{{font-size:.78rem;color:{accent}50;text-align:center;margin-top:12px;line-height:1.5;letter-spacing:.06em}}
    .content-body{{font-size:.88rem;line-height:1.7;color:#e0e0ff;
                   background:#000;border-radius:10px;padding:14px;
                   border:1px solid {accent}40;margin-bottom:14px;letter-spacing:.03em}}
    .feat-list{{list-style:none;margin-bottom:18px}}
    .feat-list li{{display:flex;align-items:center;gap:8px;padding:8px 0;
                   border-bottom:1px solid {accent}20;font-size:.88rem;color:#c4c4dd;letter-spacing:.04em}}
    .feat-check{{color:{accent}}}
    .product-img{{width:100%;max-height:200px;object-fit:cover;border-radius:10px;
                  margin-bottom:14px;border:1px solid {accent}30}}
    .badge-tag{{display:inline-block;background:{accent};color:#07071a;
                border-radius:4px;padding:3px 10px;font-size:.7rem;font-weight:800;
                margin-bottom:12px;letter-spacing:.1em;text-transform:uppercase}}
    .sub-desc{{font-size:.8rem;color:{accent}70;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px}}
    {_SHARED_JS_STYLES}
    #error-msg{{color:#ff4466}}
    .foot{{background:#07071a;text-align:center;padding:11px;font-size:10px;
           color:{accent}50;border-top:1px solid {accent}30;letter-spacing:.12em;text-transform:uppercase}}
    .foot a,.foot b{{color:{accent}90;text-decoration:none}}
  </style>
</head><body>
<div class="card">
  <div class="hdr">
    <div class="scanline"></div>
    <div class="tag">QRGenie</div>
    <h1>{title.upper()}</h1>
    <p>{subtitle.upper()}</p>
  </div>
  <div class="body">{inner_html}</div>
  <div class="foot"><a href="https://qrgenie.io" target="_blank"><b>QRGENIE</b></a> · SECURE</div>
</div>
</body></html>"""


def _design_minimal(page_title, title, subtitle, inner_html, accent, bg):
    """Editorial — pure white page, masthead topbar, oversized typography."""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{page_title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:#fff;min-height:100vh;padding:40px 32px 48px;max-width:480px;margin:0 auto}}
    .mast{{display:flex;justify-content:space-between;align-items:flex-start;
           margin-bottom:36px;padding-bottom:14px;border-bottom:3px solid #111}}
    .mast-brand{{font-size:11px;font-weight:700;letter-spacing:.2em;
                 text-transform:uppercase;color:{accent}}}
    .mast-tag{{font-size:10px;color:#9ca3af;letter-spacing:.05em}}
    h1{{font-size:28px;font-weight:900;color:#111;line-height:1.15;margin-bottom:6px}}
    .deck{{font-size:14px;color:#6b7280;margin-bottom:28px;font-style:italic}}
    .amount-box{{margin-bottom:8px}}
    .albl{{font-size:10px;font-weight:700;letter-spacing:.2em;
           text-transform:uppercase;color:#9ca3af;margin-bottom:4px}}
    .aval{{font-size:64px;font-weight:900;color:{accent};line-height:.95;margin-bottom:8px}}
    .amount-badge{{display:none}}
    .rule{{border:none;border-top:1px solid #e5e7eb;margin:20px 0;display:block}}
    .btn,.btn-custom{{display:flex;align-items:center;justify-content:center;gap:8px;
         width:100%;padding:15px;border-radius:8px;
         background:{accent};color:#fff;font-size:15px;font-weight:700;
         margin-bottom:10px;text-decoration:none;border:none;cursor:pointer;transition:opacity .15s}}
    .btn:hover,.btn-custom:hover{{opacity:.9}}
    .btn-outline{{display:flex;align-items:center;justify-content:center;gap:8px;
                  width:100%;padding:14px;border-radius:8px;
                  background:transparent;color:{accent};font-size:14px;font-weight:600;
                  border:2px solid {accent};text-decoration:none;margin-bottom:10px}}
    .note{{color:#d1d5db;font-size:11px;text-align:center;
           line-height:1.7;margin-top:14px;font-style:italic}}
    .file-box{{display:flex;align-items:center;gap:16px;padding:16px;
               border:1.5px solid #e5e7eb;border-radius:10px;margin-bottom:20px}}
    .file-icon{{font-size:2.6rem;line-height:1}}
    .file-meta strong{{display:block;font-size:1rem;font-weight:800;color:#111}}
    .file-meta span{{font-size:.82rem;color:#9ca3af}}
    .unlock-input{{width:100%;padding:14px;border:2px solid #e5e7eb;
                   border-radius:8px;font-size:1rem;background:#f9fafb;color:#111;
                   outline:none;margin-bottom:12px}}
    .unlock-input:focus{{border-color:{accent}}}
    .hint{{font-size:.82rem;color:#9ca3af;text-align:center;margin-top:12px;line-height:1.5}}
    .content-body{{font-size:.95rem;line-height:1.7;color:#374151;
                   background:#f9fafb;border-radius:8px;padding:16px;
                   border:1px solid #e5e7eb;margin-bottom:16px}}
    .feat-list{{list-style:none;margin-bottom:20px}}
    .feat-list li{{display:flex;align-items:center;gap:8px;padding:10px 0;
                   border-bottom:1px solid #f3f4f6;font-size:.95rem;color:#374151}}
    .feat-check{{color:{accent}}}
    .product-img{{width:100%;max-height:220px;object-fit:cover;border-radius:8px;margin-bottom:16px}}
    .badge-tag{{display:inline-block;background:{accent};color:#fff;
                border-radius:4px;padding:3px 10px;font-size:.75rem;font-weight:700;margin-bottom:12px}}
    .sub-desc{{font-size:.88rem;color:#6b7280;margin-bottom:4px}}
    {_SHARED_JS_STYLES}
    .foot{{margin-top:24px;padding-top:14px;border-top:1px solid #f3f4f6;
           font-size:10px;color:#d1d5db;text-align:center}}
    .foot a,.foot b{{color:{accent};text-decoration:none}}
  </style>
</head><body>
  <div class="mast">
    <div class="mast-brand">QRGenie</div>
    <div class="mast-tag">SECURE · INSTANT</div>
  </div>
  <h1>{title}</h1>
  <div class="deck">{subtitle}</div>
  {inner_html}
  <div class="foot">Powered by <a href="https://qrgenie.io" target="_blank"><b>QRGenie</b></a></div>
</body></html>"""


def _design_vibrant(page_title, title, subtitle, icon, inner_html, accent, bg):
    """Poster — full-bleed gradient hero, white bottom sheet."""
    grad = f"linear-gradient(135deg,{accent} 0%,{accent}aa 100%)"
    return f"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{page_title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    html,body{{height:100%}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:{grad};min-height:100vh;
         display:flex;align-items:stretch;justify-content:center}}
    .page{{max-width:440px;width:100%;position:relative;min-height:100vh;
           display:flex;flex-direction:column}}
    .blob1{{position:absolute;width:220px;height:220px;border-radius:50%;
            background:rgba(255,255,255,.1);top:-60px;right:-60px;pointer-events:none}}
    .blob2{{position:absolute;width:140px;height:140px;border-radius:50%;
            background:rgba(255,255,255,.07);top:80px;left:-40px;pointer-events:none}}
    .hero{{padding:48px 28px 32px;text-align:center;position:relative;z-index:1;flex-shrink:0}}
    .ico-wrap{{width:72px;height:72px;border-radius:22px;
               background:rgba(255,255,255,.25);backdrop-filter:blur(8px);
               display:flex;align-items:center;justify-content:center;
               font-size:34px;margin:0 auto 16px;
               box-shadow:0 8px 24px rgba(0,0,0,.12),inset 0 1px 0 rgba(255,255,255,.4)}}
    .hero h1{{color:#fff;font-size:24px;font-weight:900;margin-bottom:5px;
              text-shadow:0 2px 12px rgba(0,0,0,.15)}}
    .hero p{{color:rgba(255,255,255,.78);font-size:14px}}
    .sheet{{background:#fff;border-radius:28px 28px 0 0;padding:24px 22px 32px;
            flex:1;box-shadow:0 -8px 40px rgba(0,0,0,.12);position:relative;z-index:2}}
    .pill{{width:36px;height:4px;background:#e5e7eb;border-radius:2px;margin:0 auto 20px}}
    .amount-box{{background:{accent}0d;border:1.5px solid {accent}30;
                border-radius:14px;padding:14px 18px;
                display:flex;align-items:center;justify-content:space-between;
                margin-bottom:16px}}
    .albl{{color:#9ca3af;font-size:11px;font-weight:700;
           letter-spacing:.1em;text-transform:uppercase}}
    .aval{{color:{accent};font-size:28px;font-weight:900;line-height:1;margin-top:4px}}
    .amount-badge{{background:{accent};color:#fff;font-size:10px;font-weight:700;
                   padding:4px 10px;border-radius:50px;text-transform:uppercase;letter-spacing:.06em}}
    .rule{{display:none}}
    .btn,.btn-custom{{display:flex;align-items:center;justify-content:center;gap:8px;
         width:100%;padding:15px;border-radius:14px;
         background:{accent};color:#fff;font-size:15px;font-weight:700;
         margin-bottom:10px;text-decoration:none;border:none;cursor:pointer;transition:opacity .15s}}
    .btn:hover,.btn-custom:hover{{opacity:.9}}
    .btn-outline{{display:flex;align-items:center;justify-content:center;gap:8px;
                  width:100%;padding:13px;border-radius:14px;
                  background:{accent}0f;color:{accent};font-size:14px;font-weight:600;
                  border:1.5px solid {accent}35;text-decoration:none;margin-bottom:10px}}
    .note{{color:#d1d5db;font-size:10.5px;text-align:center;line-height:1.7;margin-top:10px}}
    .file-box{{display:flex;align-items:center;gap:14px;
               background:{accent}08;border:1px solid {accent}20;
               border-radius:14px;padding:14px;margin-bottom:16px}}
    .file-icon{{font-size:2.4rem;line-height:1}}
    .file-meta strong{{display:block;font-size:.95rem;font-weight:700;color:#111}}
    .file-meta span{{font-size:.8rem;color:#9ca3af}}
    .unlock-input{{width:100%;padding:14px;border:1.5px solid {accent}30;
                   border-radius:12px;font-size:1rem;background:#fff;color:#111;
                   outline:none;margin-bottom:12px}}
    .unlock-input:focus{{border-color:{accent}}}
    .hint{{font-size:.82rem;color:#9ca3af;text-align:center;margin-top:12px;line-height:1.5}}
    .content-body{{font-size:.95rem;line-height:1.7;color:#374151;
                   background:{accent}06;border-radius:12px;padding:16px;
                   border:1px solid {accent}18;margin-bottom:16px}}
    .feat-list{{list-style:none;margin-bottom:18px}}
    .feat-list li{{display:flex;align-items:center;gap:8px;padding:9px 0;
                   border-bottom:1px solid {accent}12;font-size:.92rem;color:#374151}}
    .feat-check{{color:{accent}}}
    .product-img{{width:100%;max-height:200px;object-fit:cover;border-radius:12px;margin-bottom:14px}}
    .badge-tag{{display:inline-block;background:{accent};color:#fff;
                border-radius:12px;padding:3px 12px;font-size:.75rem;font-weight:700;margin-bottom:12px}}
    .sub-desc{{font-size:.85rem;color:#6b7280;margin-bottom:4px}}
    {_SHARED_JS_STYLES}
    .foot{{text-align:center;padding-top:14px;font-size:10px;color:#d1d5db;
           border-top:1px solid {accent}12;margin-top:8px}}
    .foot a,.foot b{{color:{accent};text-decoration:none}}
  </style>
</head><body>
<div class="page">
  <div class="blob1"></div>
  <div class="blob2"></div>
  <div class="hero">
    <div class="ico-wrap">{icon}</div>
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="sheet">
    <div class="pill"></div>
    {inner_html}
    <div class="foot">Powered by <a href="https://qrgenie.io" target="_blank"><b>QRGenie</b></a></div>
  </div>
</div>
</body></html>"""


def _design_ocean(page_title, title, subtitle, icon, inner_html, accent, bg):
    """Glassmorphism — radial-gradient bg + frosted glass card."""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{page_title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:{bg};min-height:100vh;
         display:flex;align-items:center;justify-content:center;padding:24px 16px;
         background-image:
           radial-gradient(circle at 20% 20%,{accent}55 0%,transparent 55%),
           radial-gradient(circle at 80% 80%,{accent}33 0%,transparent 50%),
           radial-gradient(circle at 60% 10%,{accent}40 0%,transparent 40%)}}
    .card{{background:rgba(255,255,255,.14);backdrop-filter:blur(28px);
          -webkit-backdrop-filter:blur(28px);border-radius:26px;max-width:440px;width:100%;
          border:1.5px solid rgba(255,255,255,.5);
          box-shadow:0 12px 48px rgba(0,0,0,.22),inset 0 1px 0 rgba(255,255,255,.5);
          overflow:hidden}}
    .hdr{{padding:30px 24px 24px;text-align:center;
          border-bottom:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08)}}
    .ico-ring{{width:60px;height:60px;border-radius:50%;
               border:2px solid rgba(255,255,255,.55);
               display:flex;align-items:center;justify-content:center;
               margin:0 auto 13px;font-size:27px;
               background:rgba(255,255,255,.18);box-shadow:0 4px 16px rgba(0,0,0,.1)}}
    .hdr h1{{color:#fff;font-size:21px;font-weight:800;text-shadow:0 2px 10px rgba(0,0,0,.2)}}
    .hdr p{{color:rgba(255,255,255,.65);font-size:13px;margin-top:5px}}
    .body{{padding:22px}}
    .amount-box{{background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.38);
                border-radius:16px;padding:18px;text-align:center;margin-bottom:16px;
                box-shadow:inset 0 1px 0 rgba(255,255,255,.3)}}
    .albl{{color:rgba(255,255,255,.65);font-size:11px;font-weight:700;
           letter-spacing:.12em;text-transform:uppercase}}
    .aval{{color:#fff;font-size:36px;font-weight:900;margin-top:6px;
           text-shadow:0 2px 10px rgba(0,0,0,.25)}}
    .amount-badge{{display:none}}
    .rule{{display:none}}
    .btn,.btn-custom{{display:flex;align-items:center;justify-content:center;gap:9px;
         width:100%;padding:15px;border-radius:14px;
         background:rgba(255,255,255,.92);color:{accent};
         font-size:15px;font-weight:700;margin-bottom:10px;
         box-shadow:0 4px 20px rgba(0,0,0,.12);text-decoration:none;border:none;cursor:pointer;
         transition:opacity .15s}}
    .btn:hover,.btn-custom:hover{{opacity:.9}}
    .btn-outline{{display:flex;align-items:center;justify-content:center;gap:9px;
                  width:100%;padding:13px;border-radius:14px;
                  background:rgba(255,255,255,.1);color:#fff;font-size:14px;font-weight:600;
                  border:1.5px solid rgba(255,255,255,.45);text-decoration:none;margin-bottom:10px}}
    .note{{color:rgba(255,255,255,.5);font-size:11px;text-align:center;line-height:1.7;margin-top:12px}}
    .file-box{{display:flex;align-items:center;gap:14px;
               background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);
               border-radius:14px;padding:14px;margin-bottom:16px}}
    .file-icon{{font-size:2.4rem;line-height:1}}
    .file-meta strong{{display:block;font-size:.95rem;font-weight:700;color:#fff}}
    .file-meta span{{font-size:.8rem;color:rgba(255,255,255,.55)}}
    .unlock-input{{width:100%;padding:14px;border:1.5px solid rgba(255,255,255,.35);
                   border-radius:12px;font-size:1rem;background:rgba(255,255,255,.12);color:#fff;
                   outline:none;margin-bottom:12px}}
    .unlock-input::placeholder{{color:rgba(255,255,255,.4)}}
    .unlock-input:focus{{border-color:rgba(255,255,255,.7)}}
    .hint{{font-size:.82rem;color:rgba(255,255,255,.45);text-align:center;margin-top:12px;line-height:1.5}}
    .content-body{{font-size:.92rem;line-height:1.7;color:rgba(255,255,255,.85);
                   background:rgba(255,255,255,.1);border-radius:10px;padding:14px;
                   border:1px solid rgba(255,255,255,.2);margin-bottom:14px}}
    .feat-list{{list-style:none;margin-bottom:18px}}
    .feat-list li{{display:flex;align-items:center;gap:8px;padding:8px 0;
                   border-bottom:1px solid rgba(255,255,255,.12);
                   font-size:.9rem;color:rgba(255,255,255,.8)}}
    .feat-check{{color:rgba(255,255,255,.9)}}
    .product-img{{width:100%;max-height:200px;object-fit:cover;border-radius:12px;
                  margin-bottom:14px;border:1px solid rgba(255,255,255,.2)}}
    .badge-tag{{display:inline-block;background:rgba(255,255,255,.25);color:#fff;
                border-radius:12px;padding:3px 12px;font-size:.75rem;font-weight:700;
                margin-bottom:12px;border:1px solid rgba(255,255,255,.3)}}
    .sub-desc{{font-size:.85rem;color:rgba(255,255,255,.6);margin-bottom:4px}}
    {_SHARED_JS_STYLES}
    #error-msg{{color:#ff8090}}
    .foot{{text-align:center;padding:13px;font-size:10.5px;color:rgba(255,255,255,.35);
           border-top:1px solid rgba(255,255,255,.12)}}
    .foot a,.foot b{{color:rgba(255,255,255,.75);text-decoration:none}}
  </style>
</head><body>
<div class="card">
  <div class="hdr">
    <div class="ico-ring">{icon}</div>
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="body">{inner_html}</div>
  <div class="foot">Powered by <a href="https://qrgenie.io" target="_blank"><b>QRGenie</b></a></div>
</div>
</body></html>"""


def _wrap(design, *, page_title, title, subtitle, icon, inner_html, accent, bg):
    """Dispatch inner_html to the correct design chrome."""
    if design == "dark":
        return _design_dark(page_title, title, subtitle, inner_html, accent, bg)
    elif design == "minimal":
        return _design_minimal(page_title, title, subtitle, inner_html, accent, bg)
    elif design == "vibrant":
        return _design_vibrant(page_title, title, subtitle, icon, inner_html, accent, bg)
    elif design == "ocean":
        return _design_ocean(page_title, title, subtitle, icon, inner_html, accent, bg)
    else:  # gradient + any fallback
        return _design_gradient(page_title, title, subtitle, icon, inner_html, accent, bg)


# ─────────────────────────── Multi-link helpers ───────────────────────────────

ICON_MAP = {
    "instagram": ("📸", "#E1306C"),
    "whatsapp":  ("💬", "#25D366"),
    "facebook":  ("👥", "#1877F2"),
    "twitter":   ("🐦", "#1DA1F2"),
    "youtube":   ("▶️", "#FF0000"),
    "tiktok":    ("🎵", "#010101"),
    "website":   ("🌐", None),
    "menu":      ("🍽️", None),
    "order":     ("🛒", None),
    "maps":      ("📍", "#4285F4"),
    "download":  ("⬇️", None),
    "email":     ("✉️", None),
    "phone":     ("📞", None),
    "telegram":  ("✈️", "#0088CC"),
    "linkedin":  ("💼", "#0A66C2"),
    "github":    ("💻", "#181717"),
    "spotify":   ("🎧", "#1DB954"),
}


def _multilink_classic(buttons, accent):
    html = ""
    for btn in buttons:
        label = _e(btn.get("label", "Link"))
        url = _e(btn.get("url", "#"))
        icon_key = str(btn.get("icon", "website")).lower()
        emoji, color = ICON_MAP.get(icon_key, ("🔗", None))
        btn_color = color or accent
        html += (f'<a href="{url}" class="btn-custom" target="_blank" '
                 f'style="background:{btn_color};color:#fff">'
                 f'<span style="font-size:1.1rem">{emoji}</span>{label}</a>')
    return html


def _multilink_grid(buttons, accent):
    items = ""
    for btn in buttons:
        label = _e(btn.get("label", "Link"))
        url = _e(btn.get("url", "#"))
        icon_key = str(btn.get("icon", "website")).lower()
        emoji, color = ICON_MAP.get(icon_key, ("🔗", None))
        btn_color = color or accent
        items += (f'<a href="{url}" target="_blank" style="display:flex;flex-direction:column;'
                  f'align-items:center;justify-content:center;gap:8px;padding:18px 10px;'
                  f'border-radius:16px;border:2px solid {accent}28;text-decoration:none;'
                  f'font-size:.85rem;font-weight:600;transition:transform .15s;color:{btn_color}">'
                  f'<span style="font-size:2rem;line-height:1">{emoji}</span>'
                  f'<span>{label}</span></a>')
    return f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">{items}</div>'


def _multilink_pill(buttons, accent):
    html = ""
    for btn in buttons:
        label = _e(btn.get("label", "Link"))
        url = _e(btn.get("url", "#"))
        icon_key = str(btn.get("icon", "website")).lower()
        emoji, color = ICON_MAP.get(icon_key, ("🔗", None))
        btn_color = color or accent
        html += (f'<div style="text-align:center;margin-bottom:10px">'
                 f'<a href="{url}" target="_blank" style="display:inline-flex;align-items:center;'
                 f'gap:8px;padding:10px 28px;border-radius:50px;background:{btn_color};'
                 f'color:#fff;text-decoration:none;font-weight:600;font-size:.9rem;'
                 f'box-shadow:0 4px 14px {btn_color}55">'
                 f'<span>{emoji}</span>{label}</a></div>')
    return html


def _multilink_minimal_layout(buttons, accent):
    html = ""
    for btn in buttons:
        label = _e(btn.get("label", "Link"))
        url = _e(btn.get("url", "#"))
        icon_key = str(btn.get("icon", "website")).lower()
        emoji, color = ICON_MAP.get(icon_key, ("🔗", None))
        btn_color = color or accent
        html += (f'<a href="{url}" target="_blank" style="display:flex;align-items:center;'
                 f'justify-content:space-between;padding:14px 18px;margin-bottom:10px;'
                 f'border:1.5px solid {btn_color};border-radius:10px;'
                 f'color:{btn_color};text-decoration:none;font-weight:600;background:transparent">'
                 f'<span style="display:flex;align-items:center;gap:10px">'
                 f'<span>{emoji}</span>{label}</span>'
                 f'<span style="font-size:1.1rem">→</span></a>')
    return html


_LAYOUT_RENDERERS = {
    "classic": _multilink_classic,
    "grid": _multilink_grid,
    "pill": _multilink_pill,
    "minimal": _multilink_minimal_layout,
}


# ─────────────────────────── Page Generators ─────────────────────────────────

def generate_multi_link_page(data: dict, theme_name: str = "gradient") -> str:
    accent, bg = _resolve(theme_name, data.get("accent_color"), data.get("bg_color"))
    title = _e(data.get("title", "Welcome"))
    greeting = _e(data.get("greeting", ""))
    avatar_url = _e(data.get("avatar_url", ""))
    buttons = data.get("buttons", [])
    layout = data.get("layout", "classic")

    renderer = _LAYOUT_RENDERERS.get(layout, _multilink_classic)
    btn_html = renderer(buttons, accent)

    inner_html = btn_html
    if greeting:
        inner_html = (f'<div style="margin-bottom:16px;font-size:.9rem;opacity:.8">'
                      f'{greeting}</div>') + inner_html
    if avatar_url:
        inner_html = (f'<div style="text-align:center;margin-bottom:20px">'
                      f'<img src="{avatar_url}" alt="avatar" style="width:80px;height:80px;'
                      f'border-radius:50%;object-fit:cover;border:3px solid rgba(255,255,255,.6)">'
                      f'</div>') + inner_html

    return _wrap(
        theme_name,
        page_title=_e(data.get("title", "Welcome")),
        title=title,
        subtitle=greeting or "Scan &amp; connect",
        icon="🔗",
        inner_html=inner_html,
        accent=accent,
        bg=bg,
    )


def generate_payment_page(data: dict, theme_name: str = "gradient") -> str:
    accent, bg = _resolve(theme_name, data.get("accent_color"), data.get("bg_color"))
    business_name = _e(data.get("business_name", "Payment"))
    amount = _e(data.get("amount", ""))
    currency = data.get("currency", "INR")
    upi_id = data.get("upi_id", "")
    upi_name = _e(data.get("upi_name", data.get("business_name", "Payment")))
    note = _e(data.get("note", "Payment"))
    razorpay_url = data.get("razorpay_url", "")
    stripe_url = data.get("stripe_url", "")

    currency_sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency)
    amount_display = f"{currency_sym}{amount}" if amount else ""

    amount_html = ""
    if amount_display:
        amount_html = f"""
        <div class="amount-box">
          <div>
            <div class="albl">Amount Due</div>
            <div class="aval">{amount_display}</div>
          </div>
          <div class="amount-badge">PAY NOW</div>
        </div>"""

    upi_btn = ""
    if upi_id:
        encoded_note = note.replace(" ", "%20")
        upi_link = f"upi://pay?pa={upi_id}&pn={upi_name}&am={amount}&cu={currency}&tn={encoded_note}"
        upi_btn = (f'<a href="{_e(upi_link)}" class="btn" style="background:#00b9f1;color:#fff">'
                   f'<span style="font-size:1.1rem">📲</span> Pay via UPI</a>')

    razorpay_btn = ""
    if razorpay_url:
        razorpay_btn = (f'<a href="{_e(razorpay_url)}" class="btn" '
                        f'style="background:#072654;color:#fff" target="_blank">'
                        f'<span style="font-size:1.1rem">💳</span> Pay via Razorpay</a>')

    stripe_btn = ""
    if stripe_url:
        stripe_btn = (f'<a href="{_e(stripe_url)}" class="btn" '
                      f'style="background:#635bff;color:#fff" target="_blank">'
                      f'<span style="font-size:1.1rem">💳</span> Pay via Stripe</a>')

    note_html = ('<p class="note">Select your preferred payment method above.<br>'
                 'Transactions are secure and encrypted.</p>')

    # Editorial (minimal) gets a visible horizontal rule between amount and buttons
    rule_html = '<hr class="rule">'

    inner_html = f"{amount_html}{rule_html}{upi_btn}{razorpay_btn}{stripe_btn}{note_html}"

    return _wrap(
        theme_name,
        page_title=f"Pay — {_e(data.get('business_name', 'Payment'))}",
        title=business_name,
        subtitle="Scan &amp; Pay Instantly",
        icon="💰",
        inner_html=inner_html,
        accent=accent,
        bg=bg,
    )


def generate_file_delivery_page(data: dict, theme_name: str = "gradient") -> str:
    accent, bg = _resolve(theme_name, data.get("accent_color"), data.get("bg_color"))
    title = _e(data.get("title", "Download File"))
    filename = _e(data.get("filename", "file"))
    file_size = _e(data.get("file_size", ""))
    file_url = _e(data.get("file_url", "#"))
    description = _e(data.get("description", "")).replace("\n", "<br>")
    file_type = str(data.get("file_type", "pdf")).lower()

    _TYPE_ICONS = {
        "pdf": ("📄", "PDF Document"),
        "video": ("🎬", "Video File"),
        "image": ("🖼️", "Image File"),
        "apk": ("📱", "Android App"),
        "zip": ("📦", "ZIP Archive"),
        "doc": ("📝", "Document"),
        "xls": ("📊", "Spreadsheet"),
        "ppt": ("📽️", "Presentation"),
    }
    icon_emoji, type_label = _TYPE_ICONS.get(file_type, ("📎", "File"))
    size_html = (f'<span>{type_label} · {file_size}</span>' if file_size
                 else f'<span>{type_label}</span>')
    desc_html = (f'<p style="margin-bottom:18px;font-size:.9rem;line-height:1.6;opacity:.8">'
                 f'{description}</p>') if description else ""

    inner_html = f"""
    <div class="file-box">
      <div class="file-icon">{icon_emoji}</div>
      <div class="file-meta">
        <strong>{filename}</strong>
        {size_html}
      </div>
    </div>
    {desc_html}
    <a href="{file_url}" class="btn" download target="_blank">
      <span style="font-size:1.1rem">⬇️</span> Download {type_label}
    </a>"""

    return _wrap(
        theme_name,
        page_title=_e(data.get("title", "Download File")),
        title=title,
        subtitle=f"Your {type_label} is ready to download",
        icon=icon_emoji,
        inner_html=inner_html,
        accent=accent,
        bg=bg,
    )


def generate_password_page(data: dict, theme_name: str = "gradient") -> str:
    import base64
    accent, bg = _resolve(theme_name, data.get("accent_color"), data.get("bg_color"))
    title = _e(data.get("title", "Protected Content"))
    hint = _e(data.get("hint", "Contact the organizer if you don't have the code"))
    password = str(data.get("password", ""))
    content_title = _e(data.get("content_title", data.get("title", "Content")))
    content_body = _e(data.get("content_body", "")).replace("\n", "<br>")
    content_links = data.get("content_links", [])

    encoded_pw = base64.b64encode(password.encode()).decode()

    links_html = ""
    for lnk in content_links:
        lnk_label = _e(lnk.get("label", "Link"))
        lnk_url = _e(lnk.get("url", "#"))
        links_html += (f'<a href="{lnk_url}" class="btn" target="_blank" style="margin-top:12px">'
                       f'🔗 {lnk_label}</a>')

    inner_html = f"""
    <div id="unlock-section">
      <div style="margin-bottom:8px;font-weight:600">Enter Password:</div>
      <input type="password" class="unlock-input" id="pw-input"
             placeholder="Enter access code"
             onkeydown="if(event.key==='Enter')unlock()">
      <div id="error-msg">&#x274C; Incorrect password. Try again.</div>
      <button class="btn" onclick="unlock()">&#x1F513; Unlock</button>
      <p class="hint">{hint}</p>
    </div>
    <div id="content-section">
      <div style="text-align:center;margin-bottom:16px">
        <span style="font-size:1.8rem">&#x2705;</span>
        <div style="font-size:1.2rem;font-weight:700;margin-top:8px">{content_title}</div>
      </div>
      <div class="content-body">{content_body}</div>
      {links_html}
    </div>
    <script>
      var _k="{encoded_pw}";
      function unlock(){{
        var v=document.getElementById('pw-input').value;
        var encoded=btoa(unescape(encodeURIComponent(v)));
        if(encoded===_k){{
          document.getElementById('unlock-section').style.display='none';
          document.getElementById('content-section').style.display='block';
        }}else{{
          document.getElementById('error-msg').style.display='block';
          document.getElementById('pw-input').value='';
        }}
      }}
    </script>"""

    return _wrap(
        theme_name,
        page_title=_e(data.get("title", "Protected Content")),
        title=title,
        subtitle="This content is protected",
        icon="&#x1F512;",
        inner_html=inner_html,
        accent=accent,
        bg=bg,
    )


def generate_product_page(data: dict, theme_name: str = "gradient") -> str:
    accent, bg = _resolve(theme_name, data.get("accent_color"), data.get("bg_color"))
    product_name = _e(data.get("product_name", "Product"))
    subtitle = _e(data.get("subtitle", ""))
    description = _e(data.get("description", "")).replace("\n", "<br>")
    features = data.get("features", [])
    buy_url = _e(data.get("buy_url", ""))
    image_url = _e(data.get("image_url", ""))
    badge = _e(data.get("badge", ""))

    img_html = (f'<img class="product-img" src="{image_url}" alt="{product_name}">'
                if image_url else "")
    features_html = ""
    if features:
        items = "".join(
            f'<li><span class="feat-check">✓</span> {_e(f)}</li>'
            for f in features
        )
        features_html = f'<ul class="feat-list">{items}</ul>'
    badge_html = (f'<span class="badge-tag">{badge}</span><br>' if badge else "")
    buy_html = (f'<a href="{buy_url}" class="btn" target="_blank">🛒 Buy Now</a>'
                if buy_url else "")
    desc_html = (f'<p style="margin-bottom:16px;font-size:.9rem;line-height:1.6;opacity:.8">'
                 f'{description}</p>') if description else ""
    sub_html = (f'<div class="sub-desc">{subtitle}</div>' if subtitle else "")

    inner_html = f"{img_html}{badge_html}{sub_html}{desc_html}{features_html}{buy_html}"

    return _wrap(
        theme_name,
        page_title=_e(data.get("product_name", "Product")),
        title=product_name,
        subtitle=subtitle or "Product details",
        icon="&#x1F6CD;",
        inner_html=inner_html,
        accent=accent,
        bg=bg,
    )


def generate_chat_page(data: dict, theme_name: str = "gradient") -> str:
    import urllib.parse
    accent, bg = _resolve(theme_name, data.get("accent_color"), data.get("bg_color"))
    title = _e(data.get("title", "Chat with us"))
    subtitle = _e(data.get("subtitle", "Choose your preferred messaging app"))

    whatsapp_number = data.get("whatsapp", "")
    whatsapp_msg = data.get("whatsapp_message", "Hello! I have a query.")
    telegram_username = data.get("telegram", "").lstrip("@")
    telegram_msg = data.get("telegram_message", "")
    messenger_page = data.get("messenger", "")

    buttons = []
    if whatsapp_number:
        clean_num = "".join(c for c in whatsapp_number if c.isdigit() or c == "+")
        wa_url = f"https://wa.me/{clean_num}?text={urllib.parse.quote(whatsapp_msg)}"
        buttons.append(f'<a href="{_e(wa_url)}" class="btn-custom" '
                       f'style="background:#25D366;color:#fff" target="_blank">'
                       f'<span style="font-size:1.2rem">💬</span> WhatsApp</a>')
    if telegram_username:
        msg_param = f"?start={urllib.parse.quote(telegram_msg)}" if telegram_msg else ""
        tg_url = f"https://t.me/{telegram_username}{msg_param}"
        buttons.append(f'<a href="{_e(tg_url)}" class="btn-custom" '
                       f'style="background:#0088CC;color:#fff" target="_blank">'
                       f'<span style="font-size:1.2rem">✈️</span> Telegram</a>')
    if messenger_page:
        ms_url = f"https://m.me/{_e(messenger_page)}"
        buttons.append(f'<a href="{ms_url}" class="btn-custom" '
                       f'style="background:#0084ff;color:#fff" target="_blank">'
                       f'<span style="font-size:1.2rem">💙</span> Messenger</a>')

    return _wrap(
        theme_name,
        page_title=_e(data.get("title", "Chat with us")),
        title=title,
        subtitle=subtitle,
        icon="💬",
        inner_html="\n".join(buttons),
        accent=accent,
        bg=bg,
    )


# ─────────────────────────── Public dispatcher ───────────────────────────────

def generate_page(page_type: str, form_data: dict, theme: str = "gradient") -> str:
    """
    Main entry point. Returns complete HTML for the page.

    form_data may include:
      accent_color  — any hex string (#abc or #aabbcc) to override the theme primary
      bg_color      — background colour override
      layout        — multi_link only: "classic" | "grid" | "pill" | "minimal"
    """
    generators = {
        "multi_link":    generate_multi_link_page,
        "payment":       generate_payment_page,
        "file_delivery": generate_file_delivery_page,
        "password":      generate_password_page,
        "product":       generate_product_page,
        "chat":          generate_chat_page,
    }
    fn = generators.get(page_type)
    if not fn:
        raise ValueError(
            f"Unknown page_type: {page_type!r}. Must be one of: {list(generators.keys())}"
        )
    return fn(form_data, theme)
