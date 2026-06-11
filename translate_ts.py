#!/usr/bin/env python3
"""
translate_ts.py  —  Auto-translate a Qt .ts message across all language files.

Usage:
    python translate_ts.py <ContextClass> "<English source string>" [lang1 lang2 ...]

    If no language codes are given, ALL .ts files are processed.
    The source string can be plain text or the inner text inside an HTML <source>.

Examples:
    python translate_ts.py FlameAPIKeyWizardPage "Fetch CurseForge API key"
    python translate_ts.py FlameAPIKeyWizardPage "Fetch CurseForge API key" uk ru de
    python translate_ts.py FetchFlameAPIKey "Fetching Curseforge core API key (may take a few seconds)..."
"""

import sys
import io
import re
import html as _html
from pathlib import Path

# Force UTF-8 output so emojis don't crash on Windows cp1251 terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ─── dependency bootstrap ────────────────────────────────────────────────────

def _get_translator():
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator
    except ImportError:
        import subprocess
        print("📦  Installing deep-translator...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "deep-translator"],
        )
        from deep_translator import GoogleTranslator
        return GoogleTranslator


# ─── language-code mapping ───────────────────────────────────────────────────
# .ts file stem  →  Google Translate language code (None = not supported, skip)

TS_TO_GOOGLE: dict[str, str | None] = {
    ".template": None,
    "af":        "af",
    "ar":        "ar",
    "az":        "az",
    "azb":       "az",    # South Azerbaijani → closest: Azerbaijani
    "be":        "be",
    "bg":        "bg",
    "bn":        "bn",
    "ca":        "ca",
    "ca@valencia": "ca",
    "ceb":       "ceb",
    "ckb":       "ku",    # Central Kurdish → Kurdish
    "cop":       None,    # Coptic
    "cs":        "cs",
    "cy":        "cy",
    "da":        "da",
    "de":        "de",
    "de_CH":     "de",
    "el":        "el",
    "en@pirate": None,    # joke language
    "en@uwu":    None,    # joke language
    "en_AU":     "en",
    "en_CA":     "en",
    "en_GB":     "en",
    "en_NZ":     "en",
    "eo":        "eo",
    "es":        "es",
    "es_UY":     "es",
    "et":        "et",
    "eu":        "eu",
    "fa":        "fa",
    "fi":        "fi",
    "fil":       "tl",    # Filipino → Tagalog code
    "fr":        "fr",
    "fr_CA":     "fr",
    "fur":       None,    # Friulian
    "fy":        "fy",
    "ga":        "ga",
    "gl":        "gl",
    "grc":       None,    # Ancient Greek
    "gv":        None,    # Manx
    "haw":       "haw",
    "he":        "iw",    # Google uses "iw" for Hebrew
    "hi":        "hi",
    "hr":        "hr",
    "hu":        "hu",
    "hy":        "hy",
    "id":        "id",
    "is":        "is",
    "it":        "it",
    "ja":        "ja",
    "ja_KANJI":  "ja",
    "jam":       None,    # Jamaican Creole
    "ka":        "ka",
    "kk":        "kk",
    "km":        "km",
    "ko":        "ko",
    "kxm":       None,    # Northern Khmer
    "lb":        "lb",
    "lo":        "lo",
    "lt":        "lt",
    "lv":        "lv",
    "lzh":       None,    # Literary Chinese
    "mk":        "mk",
    "mn":        "mn",
    "ms":        "ms",
    "mt":        "mt",
    "nan":       None,    # Min Nan Chinese
    "nan_Hant":  None,
    "nb":        "no",    # Norwegian Bokmål → no
    "nl":        "nl",
    "nn":        "no",    # Norwegian Nynorsk → no
    "peo":       None,    # Old Persian
    "pl":        "pl",
    "pt":        "pt",
    "pt_BR":     "pt",
    "ro":        "ro",
    "ru":        "ru",
    "sk":        "sk",
    "sl":        "sl",
    "sq":        "sq",
    "sr":        "sr",
    "sv":        "sv",
    "szl":       None,    # Silesian
    "ta":        "ta",
    "th":        "th",
    "tok":       None,    # Toki Pona
    "tr":        "tr",
    "tt":        "tt",
    "uk":        "uk",
    "ur":        "ur",
    "uz":        "uz",
    "vec":       None,    # Venetian
    "vi":        "vi",
    "zh":        "zh-CN",
    "zh_Hant_HK": "zh-TW",
    "zh_TW":     "zh-TW",
}

# These language codes just copy the English source as-is
COPY_FROM_SOURCE = {"en_AU", "en_CA", "en_GB", "en_NZ"}


# ─── XML / HTML helpers ──────────────────────────────────────────────────────

def xml_unescape(s: str) -> str:
    return _html.unescape(s)

def xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&apos;")
    )

# Detects HTML wrapper like <html><head/><body>…<span …>TEXT</span>…</html>
_HTML_RE = re.compile(
    r'^(<html>.*?<span[^>]*>)(.*?)(</span>.*?</html>)$',
    re.DOTALL | re.IGNORECASE,
)


def do_translate(plain_text: str, google_code: str, GoogleTranslator) -> str:
    """
    Translate plain_text (already XML-unescaped).
    If the text is an HTML wrapper, only the inner text is translated.
    """
    m = _HTML_RE.match(plain_text)
    if m:
        prefix, inner, suffix = m.group(1), m.group(2), m.group(3)
        if not inner.strip():
            return plain_text
        translated_inner = GoogleTranslator(source="en", target=google_code).translate(inner)
        return f"{prefix}{translated_inner}{suffix}"
    return GoogleTranslator(source="en", target=google_code).translate(plain_text)


# ─── .ts file patcher ───────────────────────────────────────────────────────

def patch_ts_file(
    ts_path: Path,
    context_name: str,
    xml_source: str,         # already XML-escaped, as it appears in the file
    new_translation_xml: str # already XML-escaped translation value
) -> bool:
    """
    In the given .ts file, inside <context><name>context_name</name>…</context>,
    find the <message> whose <source> equals xml_source and whose <translation>
    is type="unfinished", then replace it.

    Returns True if a replacement was made.
    """
    content = ts_path.read_text(encoding="utf-8")

    # Locate the right context block
    ctx_re = re.compile(
        r'(<context>\s*<name>' + re.escape(context_name) + r'</name>)(.*?)(</context>)',
        re.DOTALL,
    )
    ctx_match = ctx_re.search(content)
    if not ctx_match:
        return False

    ctx_body = ctx_match.group(2)

    # Inside that block, find source + unfinished translation
    msg_re = re.compile(
        r'(<source>' + re.escape(xml_source) + r'</source>\s*)'
        r'(<translation type="unfinished"></translation>)',
        re.DOTALL,
    )
    msg_match = msg_re.search(ctx_body)
    if not msg_match:
        return False

    new_tag = f"<translation>{new_translation_xml}</translation>"
    new_ctx_body = ctx_body[: msg_match.start(2)] + new_tag + ctx_body[msg_match.end(2):]

    new_content = (
        content[: ctx_match.start(2)]
        + new_ctx_body
        + content[ctx_match.end(2):]
    )
    ts_path.write_text(new_content, encoding="utf-8")
    return True


def find_full_xml_source(ts_dir: Path, context_name: str, search_text: str) -> str | None:
    """
    Given a plain-text search_text, look in any .ts file for a <source> element
    inside context_name that contains this text (handles both plain and HTML sources).
    Returns the raw XML-encoded source string, or None if not found.
    """
    xml_exact = xml_escape(search_text)
    # Also try to find it as inner text of an HTML source
    xml_inner = xml_escape(search_text)

    for ts_path in ts_dir.glob("*.ts"):
        content = ts_path.read_text(encoding="utf-8", errors="replace")
        ctx_re = re.compile(
            r'<context>\s*<name>' + re.escape(context_name) + r'</name>(.*?)</context>',
            re.DOTALL,
        )
        ctx_match = ctx_re.search(content)
        if not ctx_match:
            continue
        ctx_body = ctx_match.group(1)

        # Try exact match first
        if f"<source>{xml_exact}</source>" in ctx_body:
            return xml_exact

        # Try as inner text in an HTML source
        src_re = re.compile(r'<source>(.*?)</source>', re.DOTALL)
        for m in src_re.finditer(ctx_body):
            raw = m.group(1)
            decoded = xml_unescape(raw)
            # Extract plain inner text from the decoded HTML
            inner_text = re.sub(r'<[^>]+>', '', decoded).strip()
            if inner_text == search_text.strip():
                return raw  # return the XML-encoded version from the file
    return None


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    context_name = sys.argv[1]
    source_input  = sys.argv[2]
    filter_langs  = set(sys.argv[3:]) if len(sys.argv) > 3 else None

    GoogleTranslator = _get_translator()

    ts_dir = Path(__file__).parent

    # Resolve the XML source string (handles plain text and HTML inner text)
    xml_source = find_full_xml_source(ts_dir, context_name, source_input)
    if xml_source is None:
        # Fallback: assume the input is already the exact source
        xml_source = xml_escape(source_input)

    plain_source = xml_unescape(xml_source)  # decoded for translation

    print(f"\n🌍  Translating: '{source_input[:70]}{'…' if len(source_input) > 70 else ''}'")
    print(f"    Context: {context_name}\n")

    ts_files = sorted(ts_dir.glob("*.ts"))
    updated = skipped = unsupported = errors = 0

    for ts_path in ts_files:
        lang_key = ts_path.stem

        if filter_langs and lang_key not in filter_langs:
            continue

        # Special case: English variants just copy the source text
        if lang_key in COPY_FROM_SOURCE:
            new_translation_xml = xml_source  # same as source
            replaced = patch_ts_file(ts_path, context_name, xml_source, new_translation_xml)
            if replaced:
                print(f"  ✅  [{lang_key:16}] (English copy)")
                updated += 1
            else:
                skipped += 1
            continue

        google_code = TS_TO_GOOGLE.get(lang_key)

        if google_code is None:
            unsupported += 1
            continue

        try:
            translated_plain = do_translate(plain_source, google_code, GoogleTranslator)
        except Exception as exc:
            print(f"  ⚠️   [{lang_key:16}] error: {exc}")
            errors += 1
            continue

        new_translation_xml = xml_escape(translated_plain)
        replaced = patch_ts_file(ts_path, context_name, xml_source, new_translation_xml)

        if replaced:
            preview = translated_plain if not translated_plain.startswith("<html") else \
                      re.sub(r'<[^>]+>', '', translated_plain).strip()
            print(f"  ✅  [{lang_key:16}] {preview[:60]}{'…' if len(preview) > 60 else ''}")
            updated += 1
        else:
            skipped += 1

    # ── summary ──────────────────────────────────────────────────────────────
    print()
    print(f"  Translated: {updated}  |  Skipped/already done: {skipped}  |  "
          f"Unsupported langs: {unsupported}  |  Errors: {errors}")
    print()
    print("━" * 62)
    print("  🚨  YO! Don't forget to git commit + git push in halkyi8n!")
    print("  💀  I'm watching you. The files are changed. They need saving.")
    print("  🫵  Don't make me remind you again. (I will though. Every time.)")
    print("━" * 62)


if __name__ == "__main__":
    main()
