#!/usr/bin/env python3
"""
translate_redesign.py — Translates all new redesign strings across all .ts files in one pass.

Reads each .ts file once, fills in all unfinished translations for the new contexts,
then writes the file back.

Usage:
    python halkyi8n/translate_redesign.py
"""

import sys
import io
import re
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _get_translator():
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator
    except ImportError:
        import subprocess
        print("Installing deep-translator...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "deep-translator"])
        from deep_translator import GoogleTranslator
        return GoogleTranslator


TS_TO_GOOGLE = {
    ".template": None, "af": "af", "ar": "ar", "az": "az", "azb": "az",
    "be": "be", "bg": "bg", "bn": "bn", "ca": "ca", "ca@valencia": "ca",
    "ceb": "ceb", "ckb": "ku", "cop": None, "cs": "cs", "cy": "cy",
    "da": "da", "de": "de", "el": "el", "en_AU": None, "en_CA": None,
    "en_GB": None, "en_NZ": None, "eo": "eo", "es": "es", "es_MX": "es",
    "et": "et", "eu": "eu", "fa": "fa", "fi": "fi", "fil": "tl",
    "fr": "fr", "ga": "ga", "gl": "gl", "gu": "gu", "he": "iw",
    "hi": "hi", "hr": "hr", "hu": "hu", "hy": "hy", "id": "id",
    "is": "is", "it": "it", "ja": "ja", "ka": "ka", "kk": "kk",
    "km": "km", "kn": "kn", "ko": "ko", "ku": "ku", "lb": "lb",
    "lo": "lo", "lt": "lt", "lv": "lv", "mk": "mk", "ml": "ml",
    "mn": "mn", "mr": "mr", "ms": "ms", "mt": "mt", "my": "my",
    "nb": "no", "ne": "ne", "nl": "nl", "nn": "nn", "pa": "pa",
    "pl": "pl", "pt_BR": "pt", "pt_PT": "pt", "ro": "ro", "ru": "ru",
    "si": "si", "sk": "sk", "sl": "sl", "sq": "sq", "sr": "sr",
    "sr@latin": "sr", "sv": "sv", "sw": "sw", "ta": "ta", "te": "te",
    "th": "th", "tl": "tl", "tr": "tr", "uk": "uk", "ur": "ur",
    "uz": "uz", "vi": "vi", "zh_CN": "zh-CN", "zh_TW": "zh-TW",
}

ENGLISH_LANGS = {"en_AU", "en_CA", "en_GB", "en_NZ"}

NEW_CONTEXTS = [
    "HalkyNavBar", "NewsPanel", "HomePage",
    "BrowsePage", "OnboardingOverlay", "MainWindow",
    # Wizard redesign
    "WizardSidebar", "SetupWizard",
    # Settings and dialog redesign
    "PageDialog", "PageContainer", "NewInstanceDialog",
    "LanguageWizardPage", "JavaWizardPage", "AutoJavaWizardPage",
    "PasteWizardPage", "ThemeWizardPage", "LoginWizardPage", "FlameAPIKeyWizardPage",
]


def xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))


def xml_unescape(s):
    return (s.replace("&amp;", "&").replace("&lt;", "<")
             .replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))


def collect_unfinished(content):
    """Return list of (context_name, source_str) pairs that are unfinished."""
    unfinished = []
    ctx_pattern = re.compile(r'<context>(.*?)</context>', re.DOTALL)
    msg_pattern = re.compile(
        r'<message>\s*<source>(.*?)</source>\s*<translation type="unfinished"></translation>',
        re.DOTALL
    )
    name_pattern = re.compile(r'<name>(.*?)</name>')

    for ctx_match in ctx_pattern.finditer(content):
        ctx_body = ctx_match.group(1)
        name_m = name_pattern.search(ctx_body)
        if not name_m:
            continue
        ctx_name = name_m.group(1).strip()
        if ctx_name not in NEW_CONTEXTS:
            continue
        for msg_match in msg_pattern.finditer(ctx_body):
            src = xml_unescape(msg_match.group(1).strip())
            unfinished.append((ctx_name, src))

    return unfinished


def translate_all_strings(strings_set, google_lang, GoogleTranslator):
    """Translate a set of English strings to google_lang. Returns {english: translated}."""
    results = {}
    for src in strings_set:
        try:
            translated = GoogleTranslator(source="en", target=google_lang).translate(src)
            results[src] = translated if translated else src
            time.sleep(0.05)  # small delay to avoid rate limiting
        except Exception as e:
            print(f"    ⚠️  Translation error for '{src[:40]}': {e}")
            results[src] = src  # fallback to English
    return results


def fill_translations(content, ctx_name, src_str, translated_str):
    """Replace unfinished translation for a specific context+source with translated text."""
    escaped_src = re.escape(xml_escape(src_str))
    escaped_translated = xml_escape(translated_str)

    pattern = re.compile(
        r'(<context>.*?<name>' + re.escape(ctx_name) + r'</name>.*?'
        r'<source>' + escaped_src + r'</source>\s*)'
        r'<translation type="unfinished"></translation>',
        re.DOTALL
    )

    def replacer(m):
        return m.group(1) + f'<translation>{escaped_translated}</translation>'

    new_content, count = pattern.subn(replacer, content)
    return new_content, count


def process_ts_file(ts_path, all_translations, lang):
    """Fill all unfinished translations for new contexts in one .ts file."""
    content = ts_path.read_text(encoding="utf-8", errors="replace")
    total_filled = 0

    for ctx_name, src_str in all_translations:
        translated = all_translations[(ctx_name, src_str)].get(lang)
        if not translated:
            continue
        content, count = fill_translations(content, ctx_name, src_str, translated)
        total_filled += count

    if total_filled > 0:
        ts_path.write_text(content, encoding="utf-8")

    return total_filled


def main():
    GoogleTranslator = _get_translator()

    ts_dir = Path(__file__).parent
    ts_files = sorted(ts_dir.glob("*.ts"))
    ts_files = [f for f in ts_files if f.stem != ".template"]

    # Step 1: collect all unique (ctx, src) pairs that need translation
    # Use any non-English .ts file to find unfinished strings
    sample_file = next((f for f in ts_files if f.stem not in ENGLISH_LANGS and f.stem in TS_TO_GOOGLE and TS_TO_GOOGLE[f.stem] is not None), None)
    if not sample_file:
        print("No suitable sample file found.")
        return

    sample_content = sample_file.read_text(encoding="utf-8", errors="replace")
    unfinished_pairs = collect_unfinished(sample_content)

    if not unfinished_pairs:
        print("No unfinished translations found in new contexts.")
        return

    unique_sources = list(dict.fromkeys(src for _, src in unfinished_pairs))
    print(f"Found {len(unfinished_pairs)} unfinished entries ({len(unique_sources)} unique strings) in {len(NEW_CONTEXTS)} contexts")
    print(f"Processing {len(ts_files)} .ts files...\n")

    # Step 2: for each language, translate all strings, then update the file
    grand_total = 0
    files_updated = 0

    for ts_path in ts_files:
        lang = ts_path.stem
        google_lang = TS_TO_GOOGLE.get(lang)

        if lang in ENGLISH_LANGS:
            # English variants already have translations from add_new_strings.py
            continue
        if google_lang is None:
            continue

        print(f"  [{lang:20}] translating {len(unique_sources)} strings...", end=" ", flush=True)

        # Translate all unique sources for this language
        translations = translate_all_strings(unique_sources, google_lang, GoogleTranslator)

        # Build flat lookup: (ctx, src) -> translated
        flat = {}
        for ctx, src in unfinished_pairs:
            if src in translations:
                flat[(ctx, src)] = translations[src]

        # Apply to file
        content = ts_path.read_text(encoding="utf-8", errors="replace")
        filled = 0
        for (ctx_name, src_str), translated_str in flat.items():
            content, count = fill_translations(content, ctx_name, src_str, translated_str)
            filled += count

        if filled > 0:
            ts_path.write_text(content, encoding="utf-8")
            grand_total += filled
            files_updated += 1
            print(f"✅  +{filled}")
        else:
            print("(nothing to fill)")

    print(f"\nDone: updated {files_updated} files, filled {grand_total} translations total.")


if __name__ == "__main__":
    main()
