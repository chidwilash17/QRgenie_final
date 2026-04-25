"""
AI Service — OpenRouter Client
===================================
Uses OpenRouter API with Gemini 2.0 Flash for ultra-fast, stunning
landing page generation with rich JavaScript animations.
"""
import json
import logging
import re
import requests
from decouple import config
from django.utils import timezone

logger = logging.getLogger('qrgenie')

OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions'

# Gemini 2.0 Flash — fast, good for JSON planning tasks
FAST_MODEL = 'google/gemini-2.0-flash-001'

# Gemini 2.5 Flash — higher quality for HTML/CSS/JS page generation
GENERATION_MODEL = 'google/gemini-2.5-flash'

DEFAULT_MODEL = FAST_MODEL


def _get_api_key() -> str:
    api_key = config('OPENROUTER_API_KEY', default='')
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. Add it to backend/.env"
        )
    return api_key


def _parse_json_response(text: str) -> dict:
    """
    Robustly parse JSON from AI response — handles markdown fences,
    code blocks, and other wrapping that models sometimes add.
    """
    cleaned = text.strip()

    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try finding first { ... last }
    first_brace = cleaned.find('{')
    last_brace = cleaned.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    # Give up
    return None


def chat_completion(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    response_format: dict = None,
    timeout: int = 90,
) -> dict:
    """
    Make an OpenRouter chat completion call. Returns dict with:
      content, prompt_tokens, completion_tokens, total_tokens, model
    """
    api_key = _get_api_key()

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    if response_format:
        payload['response_format'] = response_format

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://qrgenie.pythonanywhere.com',
        'X-Title': 'QRGenie',
    }

    logger.info(f"OpenRouter request: model={model}, max_tokens={max_tokens}, temp={temperature}")
    resp = requests.post(OPENROUTER_API_URL, json=payload, headers=headers, timeout=timeout)
    logger.info(f"OpenRouter response: status={resp.status_code}, len={len(resp.text)}")
    resp.raise_for_status()
    data = resp.json()

    if 'error' in data:
        raise RuntimeError(f"OpenRouter error: {data['error'].get('message', data['error'])}")

    choices = data.get('choices')
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices. Keys: {list(data.keys())}")

    choice = choices[0]
    usage = data.get('usage', {})
    content = choice.get('message', {}).get('content', '')
    finish_reason = choice.get('finish_reason', 'stop')
    logger.info(f"OpenRouter done: finish_reason={finish_reason}, content_len={len(content)}, tokens={usage.get('total_tokens', 0)}")

    return {
        'content': content,
        'prompt_tokens': usage.get('prompt_tokens', 0),
        'completion_tokens': usage.get('completion_tokens', 0),
        'total_tokens': usage.get('total_tokens', 0),
        'model': data.get('model', model),
        'finish_reason': finish_reason,
    }


# ─── AI Feature Functions ─────────────────────────────────────────────────────


def generate_landing_page_html(
    business_name: str,
    business_type: str,
    description: str,
    links: list[dict] = None,
    style: str = 'modern',
    color_scheme: str = '#6366f1',
) -> dict:
    """
    Generate a complete landing page HTML using GPT-4o.
    Returns { html, title, meta_description, tokens_used }.
    """
    links_text = ""
    if links:
        links_text = "Include these links as buttons:\n"
        for link in links:
            links_text += f"- {link.get('label', 'Link')}: {link.get('url', '#')}\n"

    prompt = f"""You are a professional web designer. Generate a complete, self-contained HTML landing page.

Requirements:
- Business Name: {business_name}
- Business Type: {business_type}
- Description: {description}
- Style: {style}
- Primary Color: {color_scheme}
{links_text}

The HTML must:
1. Be fully responsive (mobile-first)
2. Include inline CSS (no external stylesheets)
3. Use the primary color as the accent
4. Have a hero section with the business name and description
5. Include a professional layout with proper spacing
6. Include a footer with "Powered by QRGenie"
7. Be complete and ready to serve — no placeholder content
8. Use modern CSS (flexbox/grid, rounded corners, shadows)

Return ONLY valid JSON with these keys:
- "html": the complete HTML document
- "title": the page title
- "meta_description": a 160-char meta description"""

    result = chat_completion(
        messages=[
            {'role': 'system', 'content': 'You are a web design expert. Return only valid JSON.'},
            {'role': 'user', 'content': prompt},
        ],
        model=FAST_MODEL,
        temperature=0.7,
        max_tokens=4096,
    )

    parsed = _parse_json_response(result['content'])
    if not parsed:
        parsed = {'html': result['content'], 'title': business_name, 'meta_description': ''}

    return {
        **parsed,
        'tokens_used': result['total_tokens'],
        'model': result['model'],
    }


def ai_plan_page_fields(prompt: str) -> dict:
    """
    Analyze a user's page request and return structured form fields
    the user should fill in before the AI generates the page.
    Returns { fields: [...], page_type, description, suggested_tagline,
              suggested_sections, tokens_used, model }.
    """
    system_prompt = """You are a senior conversion-rate-optimisation strategist and landing page architect. A user describes the page they want. Your job is to:
1. Understand the PAGE PURPOSE deeply (what action should a visitor take?)
2. Return a smart field schema — every field is a real piece of content the AI will embed in specific, named spots in the page.
3. Pre-plan the page structure so the generation step produces a cohesive, high-converting result.

Return ONLY valid JSON with EXACTLY these top-level keys:
- "page_type": underscore_slug category (e.g. "wedding_invitation", "restaurant", "portfolio", "saas_product", "event_ticket", "ecommerce", "personal_brand", "nonprofit")
- "description": 1-2 sentences describing the stunning page you will build
- "suggested_tagline": a compelling hero tagline suggestion the user can edit (make it punchy and benefit-driven)
- "suggested_sections": array of section names that will appear on the page (e.g. ["Hero", "Features", "Gallery", "Pricing", "Testimonials", "Contact", "Footer"])
- "fields": array of field objects

Each field object MUST have:
- "name": snake_case unique key (e.g. "founder_name", "event_date", "hero_cta_text")
- "label": human-readable label shown in the form (clear and friendly)
- "type": one of "text", "textarea", "date", "time", "email", "phone", "url", "number", "select", "color"
- "placeholder": a concrete example showing exactly what to type (NOT "Enter your..." — show real example data)
- "required": false (ALL fields are optional — user fills what they have)
- "group": logical group name to visually cluster related fields
- "hint": one short sentence explaining WHERE this will appear on the page (e.g. "Shown as the main headline in the hero section")
- "options": array of strings ONLY for "select" type fields

FIELD PLANNING RULES:
- 12–20 fields per schema — be thorough and anticipate everything
- Cover: branding (name, tagline, logo notion), core content, social proof, CTAs, contact info, design preferences
- ALWAYS include these groups: one content-specific group, "Social Proof & Trust", "Call to Action", "Design Preferences"
- "Design Preferences" group must include: primary_color (color), font_style (select: Modern Sans, Elegant Serif, Playful Rounded, Bold Display, Minimalist Clean), page_tone (select: Luxury & Premium, Fun & Energetic, Professional & Corporate, Warm & Personal, Bold & Edgy), dark_mode (select: Dark Theme, Light Theme, Mixed)
- "Call to Action" group must include: cta_button_text (text), cta_target_url (url), secondary_cta_text (text), secondary_cta_url (url)
- For every page type, add 2–3 TESTIMONIAL fields: testimonial_1_text (textarea), testimonial_1_author (text), etc.
- Think like a marketing agency: what would a copywriter need to write great headlines, subheadlines, feature bullets, and benefit statements?
- Placeholder examples should contain REAL-looking sample data specific to the page type (e.g. for a restaurant: "Biryani Palace — Award-winning North Indian cuisine since 2010")"""

    user_msg = f"""The user wants to create: {prompt}

Analyze this and return the complete JSON field schema. Make the suggested_tagline genuinely compelling — it should make someone want to scroll down."""

    result = chat_completion(
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_msg},
        ],
        model=FAST_MODEL,
        temperature=0.5,
        max_tokens=3000,
    )

    parsed = _parse_json_response(result['content'])
    if not parsed:
        parsed = {'fields': [], 'page_type': 'custom', 'description': 'Custom page', 'suggested_tagline': '', 'suggested_sections': []}

    return {
        **parsed,
        'tokens_used': result['total_tokens'],
        'model': result['model'],
    }


def ai_generate_page_from_prompt(prompt: str, style_hint: str = 'modern', fields_data: dict = None, form_links: list = None, page_type: str = None, suggested_sections: list = None, media_files: list = None) -> dict:
    """
    Generate a complete, stunning landing page from a free-form user prompt.
    If fields_data is provided, the AI uses those real details in the page.
    If form_links is provided, the AI creates real buttons linking to those forms.
    Returns { html, title, meta_description, tokens_used, model }.
    """

    # ── Style-specific design systems ──
    STYLE_SYSTEMS = {
        'modern': """DESIGN SYSTEM — Modern
PALETTE: Primary #6366f1 (indigo), Secondary #8B5CF6 (violet), Accent #06B6D4 (cyan), Success #10B981
BACKGROUNDS: Hero gradient linear-gradient(135deg, #0F0F1A 0%, #1E1B4B 50%, #312E81 100%). Light sections #FAFAFE. Dark sections #0F0F1A.
FONTS: <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@700;800&display=swap" rel="stylesheet">. Headings "Plus Jakarta Sans",sans-serif weight 800. Body "Inter",sans-serif weight 400.
CARDS: background rgba(255,255,255,0.04); border 1px solid rgba(99,102,241,0.15); border-radius 16px; backdrop-filter blur(12px); padding 32px.
BUTTONS: background linear-gradient(135deg,#6366f1,#8B5CF6); color #fff; border-radius 50px; padding 14px 32px; font-weight 600; box-shadow 0 4px 20px rgba(99,102,241,0.35). Hover: transform scale(1.05) via CSS :hover.""",

        'minimal': """DESIGN SYSTEM — Minimal
PALETTE: Primary #18181B (near-black), Secondary #71717A (zinc), Accent #3B82F6 (blue). Almost no color — let whitespace and typography speak.
BACKGROUNDS: All sections white #FFFFFF or #FAFAFA. Hero is white with large bold text only. No gradients on backgrounds.
FONTS: <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">. Headings "DM Sans",sans-serif weight 700. Body "DM Sans",sans-serif weight 400.
CARDS: background #FFFFFF; border 1px solid #E4E4E7; border-radius 12px; padding 28px. No backdrop-filter.
BUTTONS: background #18181B; color #fff; border-radius 8px; padding 12px 28px; font-weight 500. Hover: background #3B82F6 via CSS :hover. Secondary buttons: border 1px solid #E4E4E7; background transparent.""",

        'bold': """DESIGN SYSTEM — Bold
PALETTE: Primary #EF4444 (red), Secondary #F97316 (orange), Accent #FBBF24 (amber), Dark #0A0A0A.
BACKGROUNDS: Hero solid #0A0A0A with massive colored text. Alternating #0A0A0A and #FFFFFF sections. No subtle gradients — go big.
FONTS: <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">. Headings "Space Grotesk",sans-serif weight 700. Body "Outfit",sans-serif weight 400. Hero h1 should be extremely large: clamp(48px,8vw,96px).
CARDS: background #111111; border 2px solid rgba(239,68,68,0.2); border-radius 20px; padding 32px.
BUTTONS: background #EF4444; color #fff; border-radius 12px; padding 16px 36px; font-weight 700; font-size 18px; text-transform uppercase; letter-spacing 0.05em. Hover: background #F97316 via CSS :hover.""",

        'elegant': """DESIGN SYSTEM — Elegant
PALETTE: Primary #D4AF37 (gold), Secondary #1C1C1E (charcoal), Accent #F5F0E8 (cream), Text #2D2D2D.
BACKGROUNDS: Hero #1C1C1E with gold accents. Content sections cream #FAF8F4. No harsh #FFFFFF.
FONTS: <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Lora:wght@400;500&display=swap" rel="stylesheet">. Headings "Playfair Display",serif weight 700. Body "Lora",serif weight 400. Refined, editorial feel.
CARDS: background #FFFFFF; border 1px solid rgba(212,175,55,0.15); border-radius 8px; padding 32px; box-shadow 0 2px 12px rgba(0,0,0,0.04).
BUTTONS: background #1C1C1E; color #D4AF37; border-radius 4px; padding 14px 36px; font-weight 600; letter-spacing 0.12em; text-transform uppercase; font-size 13px. Hover: background #D4AF37; color #1C1C1E via CSS :hover.""",

        'playful': """DESIGN SYSTEM — Playful
PALETTE: Primary #8B5CF6 (purple), Secondary #EC4899 (pink), Accent #FBBF24 (yellow), Teal #14B8A6. Use all 4 colors generously.
BACKGROUNDS: Hero gradient linear-gradient(135deg, #8B5CF6 0%, #EC4899 50%, #FBBF24 100%) background-size 300% 300% with animation. Content sections alternate white and pastel tints.
FONTS: <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">. Everything "Nunito",sans-serif. Headings weight 800. Body weight 400. Generous roundness.
CARDS: background #FFFFFF; border 2px solid #F3E8FF; border-radius 24px; padding 28px; box-shadow 0 8px 30px rgba(139,92,246,0.08).
BUTTONS: background linear-gradient(135deg,#8B5CF6,#EC4899); color #fff; border-radius 50px; padding 14px 32px; font-weight 700. Hover: transform scale(1.08) box-shadow 0 8px 30px rgba(139,92,246,0.3) via CSS :hover.""",
    }

    system_prompt = """You are an elite landing-page designer who creates $10,000-agency-quality pages. Output a COMPLETE, self-contained HTML page.

OUTPUT FORMAT:
- Raw HTML only. Start with <!DOCTYPE html>, end with </html>.
- No JSON wrapping, no markdown fences, no commentary.

❌❌❌ ABSOLUTE PROHIBITION — EMBEDDING FORMS IS STRICTLY FORBIDDEN ❌❌❌:
YOU MUST NEVER DO ANY OF THE FOLLOWING (violations will cause critical system failure):
- ❌ NO <form> tags anywhere in the HTML
- ❌ NO <input> elements of any type (text, email, password, checkbox, radio, submit, etc.)
- ❌ NO <textarea> elements
- ❌ NO <select> dropdowns or <option> elements
- ❌ NO <button type="submit"> elements
- ❌ NO form validation JavaScript
- ❌ NO form submission handlers (addEventListener on forms, prevent default, fetch/AJAX to submit data)
- ❌ NEVER write phrases like "Email Signup", "Subscribe", "Enter your email", "Join our newsletter" with input fields
- ❌ If user says "registration form", "RSVP", "contact form", "survey" — DO NOT create the form HTML
- ❌ NO fixed bottom CTAs with comments like "QRGenie: Linked Form CTA"
- ❌ NO position:fixed bottom form buttons or popups
- ❌ NO automatically generated form elements or buttons unless explicitly provided in LINKED FORMS section
- ❌ DO NOT create any buttons linking to forms unless specifically listed in LINKED FORMS section below

✅ WHAT TO DO INSTEAD:
- If user needs forms, you will receive LINKED FORMS section with button labels and URLs
- Create beautiful <a href="URL"> LINK BUTTONS (NOT forms!) with the provided button text
- Button examples: <a href="https://..." class="cta-btn">Register Now</a>
- Style these buttons as prominent CTAs using the design system
- NO form elements — ONLY navigation links disguised as buttons
- ONLY create form buttons if they are explicitly listed in the LINKED FORMS section below

CRITICAL SECURITY CONSTRAINT — MUST FOLLOW:
- NEVER use inline event handlers (onclick, onmouseover, onmouseout, onload, onerror, onfocus, etc.)
- All hover effects MUST use CSS :hover pseudo-class
- All click handlers MUST use addEventListener() in the <script> block
- All scroll handlers MUST use addEventListener('scroll', ...) in the <script> block
- Inline on* attributes will be stripped by the sanitizer and BREAK the page

TECH STACK:
- Single <style> block in <head>, single <script> block before </body>
- One Google Font via <link> (specified in the design system below)
- No external CSS/JS libraries
- Mobile-first responsive with breakpoints at 480px, 768px, 1024px
- <meta name="viewport" content="width=device-width, initial-scale=1">
- CSS custom properties in :root for colors, spacing, border-radius
- html { scroll-behavior: smooth }

DESIGN QUALITY REQUIREMENTS:
- Animated gradient hero — background-size:300% 300% with CSS @keyframes gradient animation
- Glassmorphism cards — backdrop-filter:blur(12px); rgba background; subtle border
- Gradient text on hero headline — background: linear-gradient(...); -webkit-background-clip: text; -webkit-text-fill-color: transparent
- Pill-shaped or style-appropriate CTA buttons with CSS :hover scale + shadow transitions
- Alternating light/dark sections with generous padding using clamp()
- Typography: hero h1 clamp(36px,5vw,72px) weight 800; body 17px; line-height 1.7
- Layered box-shadows for depth on cards and images
- Floating decorative blurred circles in hero using CSS @keyframes float animation
- Subtle border-bottom on section dividers
- Section headings with small colored overline text (label) above the main heading
- Consistent spacing system: sections padding clamp(48px,8vw,96px) 0

CSS ANIMATIONS (define all in <style>):
@keyframes fadeUp { from { opacity:0; transform:translateY(30px) } to { opacity:1; transform:translateY(0) } }
@keyframes gradient { 0%{background-position:0% 50%} 50%{background-position:100% 50%} 100%{background-position:0% 50%} }
@keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-20px)} }

JS INTERACTIONS (implement all in <script> using addEventListener):
- IntersectionObserver for scroll-reveal: elements with class .reveal start with opacity:0;transform:translateY(30px); observer adds .revealed class
- Animated number counters using requestAnimationFrame on stats (not setInterval)
- Sticky nav: addEventListener('scroll') — add class when scrollY > 80
- Mobile hamburger: addEventListener('click') on burger icon — toggle nav visibility
- Smooth-scroll: already handled by CSS scroll-behavior:smooth, but add addEventListener('click') to nav links to close mobile menu

CONTENT RULES:
- Use ALL user-provided data visibly on the page — never omit any field the user filled
- Write real marketing copy for any section not covered by user data — no "Lorem ipsum" or placeholder text
- Benefit-driven headlines. Action-oriented CTA button text
- Include relevant emoji in section headings for visual interest
- Social proof sections should feel authentic — use real-sounding names and titles
- Footer must include "Powered by QRGenie" link

CRITICAL — NO EMBEDDED FORMS:
- NEVER create embedded form elements (<form>, <input>, <textarea>, <select>, <checkbox>, <radio>, etc.) on the page
- Forms are handled by external URLs — only create <a> LINK BUTTONS that navigate to those URLs
- If user wants a registration, RSVP, contact, survey, or any form — create a beautiful CTA BUTTON that LINKS to the form URL
- The button should have the user-provided label text and href pointing to the form URL
- No form submission logic, no form fields, no input elements — ONLY link buttons"""

    # ── Build style directive ──
    style_system = STYLE_SYSTEMS.get(style_hint.lower(), STYLE_SYSTEMS.get('modern'))
    system_prompt += f"\n\n{style_system}"

    # ── Build user-provided details as a flat list ──
    fields_section = ""
    if fields_data:
        details = []
        for key, value in fields_data.items():
            if value:
                details.append(f"- {key.replace('_', ' ').title()}: {value}")
        if details:
            fields_section = "\n\nUSER DETAILS (use ALL of these visibly on the page):\n" + "\n".join(details)

    # ── Build form links section ──
    forms_section = ""
    if form_links:
        forms_section = """

═══════════════════════════════════════════════════════════════
🔗 CRITICAL: LINKED FORM BUTTONS — YOU MUST USE THESE EXACT URLS
═══════════════════════════════════════════════════════════════
For EACH form below, create a prominent CTA button with:
- The EXACT href URL provided (copy it exactly, do not modify)
- The button label text provided
- Style as a beautiful, prominent call-to-action button

BUTTONS TO CREATE:
"""
        for fl in form_links:
            forms_section += f"""
📌 Button #{form_links.index(fl) + 1}:
   - Label Text: "{fl['label']}"
   - EXACT href URL: {fl['url']}
   - HTML Example: <a href="{fl['url']}" class="cta-btn">{fl['label']}</a>
"""
        forms_section += """
⚠️ MANDATORY REQUIREMENTS:
1. Use the EXACT URL provided above as the href (do not use "#" or placeholder URLs)
2. Create <a> link buttons, NOT <form> elements
3. Style these as prominent, clickable CTA buttons
4. Place at least one button in the hero section and one near the bottom
═══════════════════════════════════════════════════════════════
"""

    # ── Build sections directive ──
    sections_note = ""
    if suggested_sections:
        sections_note = "\n\nPLANNED SECTIONS (build these in this order):\n" + "\n".join(f"- {s}" for s in suggested_sections)
    elif page_type:
        sections_note = f"\n\nBuild sections appropriate for a {page_type.replace('_', ' ')} page. Include at minimum: Nav, Hero, main content sections, CTA, Footer."

    # ── Build media files section ──
    media_section = ""
    if media_files:
        media_section = "\n\nUSER-PROVIDED MEDIA FILES — MUST USE THESE in the page:\n"
        for mf in media_files:
            media_type = mf.get('type', 'file')
            url = mf.get('url', '')
            name = mf.get('name', '')
            if url:
                if media_type == 'image':
                    media_section += f"- IMAGE: {url} (name: {name}) — Use as hero background, product image, or gallery item. Use <img src=\"{url}\" alt=\"{name}\" ...>\n"
                elif media_type == 'video':
                    media_section += f"- VIDEO: {url} (name: {name}) — Embed as background video or content video. Use <video src=\"{url}\" ...> with autoplay, muted, loop for backgrounds\n"
                else:
                    media_section += f"- FILE: {url} (name: {name}) — Link to this file if appropriate\n"
        media_section += "\nIMPORTANT: Use ALL provided media files prominently in the design. Images should be displayed, videos should be embedded."

    user_msg = f"""Create a landing page for:

{prompt}

Style: {style_hint}
{fields_section}{forms_section}{sections_note}{media_section}
Start with <!DOCTYPE html>. No JSON. No markdown fences."""

    result = chat_completion(
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_msg},
        ],
        model=GENERATION_MODEL,
        temperature=0.75,
        max_tokens=24000,
        timeout=120,
    )

    raw = result['content'].strip()

    # Strip markdown code fences if the model wraps the HTML anyway
    fence_match = re.search(r'```(?:html)?\s*\n?(.*)', raw, re.DOTALL | re.IGNORECASE)
    if fence_match:
        raw = fence_match.group(1).strip()
        raw = re.sub(r'\n?```\s*$', '', raw).strip()

    # Ensure document starts at <!DOCTYPE html>
    doctype_pos = raw.lower().find('<!doctype')
    if doctype_pos > 0:
        raw = raw[doctype_pos:]

    # Handle truncation: close any open tags so browser can render what we got
    if '</html>' not in raw.lower():
        # Close open style/script blocks first
        lower = raw.lower()
        if lower.rfind('<style') > lower.rfind('</style'):
            raw += '\n</style>'
        if lower.rfind('<script') > lower.rfind('</script'):
            raw += '\n</script>'
        if '</body>' not in raw.lower():
            raw += '\n</body>'
        raw += '\n</html>'

    # Extract title and meta_description from the HTML
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', raw, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else 'AI Generated Page'

    desc_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        raw, re.IGNORECASE
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        raw, re.IGNORECASE
    )
    meta_description = desc_match.group(1).strip() if desc_match else ''

    return {
        'html': raw,
        'title': title,
        'meta_description': meta_description,
        'tokens_used': result['total_tokens'],
        'model': result['model'],
    }


def generate_analytics_summary(analytics_data: dict) -> dict:
    """
    Generate a human-readable analytics summary from raw data.
    """
    prompt = f"""Analyze this QR code analytics data and provide actionable insights:

{json.dumps(analytics_data, indent=2, default=str)}

Provide:
1. A brief executive summary (2-3 sentences)
2. Top 3 key insights
3. Top 3 recommendations for improvement
4. Any anomalies or notable patterns

Return valid JSON with keys: summary, insights (list), recommendations (list), anomalies (list)"""

    result = chat_completion(
        messages=[
            {'role': 'system', 'content': 'You are a data analytics expert. Return only valid JSON.'},
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.5,
        max_tokens=2048,
    )

    parsed = _parse_json_response(result['content'])
    if not parsed:
        parsed = {'summary': result['content'], 'insights': [], 'recommendations': [], 'anomalies': []}

    return {**parsed, 'tokens_used': result['total_tokens']}


def suggest_smart_routing(qr_data: dict, scan_history: list) -> dict:
    """
    AI-powered routing rule suggestions based on scan patterns.
    """
    prompt = f"""You are a QR code marketing expert. Based on the following QR code and its scan history,
suggest optimal routing rules to improve conversion.

QR Code Info:
{json.dumps(qr_data, indent=2, default=str)}

Recent Scan History (sample):
{json.dumps(scan_history[:50], indent=2, default=str)}

Suggest routing rules in JSON format:
{{
    "suggestions": [
        {{
            "rule_type": "device|geo|time|language",
            "conditions": {{"key": "value"}},
            "destination_url": "suggested URL or description",
            "reasoning": "why this rule would help"
        }}
    ],
    "overall_strategy": "brief strategy description"
}}"""

    result = chat_completion(
        messages=[
            {'role': 'system', 'content': 'You are a marketing optimization expert. Return only valid JSON.'},
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.6,
        max_tokens=2048,
    )

    parsed = _parse_json_response(result['content'])
    if not parsed:
        parsed = {'suggestions': [], 'overall_strategy': result['content']}

    return {**parsed, 'tokens_used': result['total_tokens']}


def optimize_ab_test(variants: list[dict]) -> dict:
    """
    Given A/B test variant performance data, recommend a winner or adjustments.
    """
    prompt = f"""Analyze these A/B test variants for a QR code campaign and recommend the best approach:

{json.dumps(variants, indent=2, default=str)}

Return JSON with:
- winner: the winning variant identifier (or null if inconclusive)
- confidence: percentage confidence in the recommendation
- reasoning: explanation
- next_steps: what to do next"""

    result = chat_completion(
        messages=[
            {'role': 'system', 'content': 'You are a conversion optimization expert. Return only valid JSON.'},
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.4,
        max_tokens=1024,
    )

    parsed = _parse_json_response(result['content'])
    if not parsed:
        parsed = {'winner': None, 'confidence': 0, 'reasoning': result['content'], 'next_steps': ''}

    return {**parsed, 'tokens_used': result['total_tokens']}
