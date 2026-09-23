#!/usr/bin/env python3
"""
translate_ts.py  —  Auto-translate a Qt .ts message across all language files.

Usage:
    python translate_ts.py <ContextClass> "<English source string>" [lang1 lang2 ...]
    python translate_ts.py    (retry-only mode: retries all failed translations from database)

    If no language codes are given, ALL .ts files are processed.
    The source string can be plain text or the inner text inside an HTML <source>.

Examples:
    python translate_ts.py FlameAPIKeyWizardPage "Fetch CurseForge API key"
    python translate_ts.py FlameAPIKeyWizardPage "Fetch CurseForge API key" uk ru de
    python translate_ts.py    # Retry all failed translations

Configuration:
    The DeepL API key is read from the DEEPL_API_KEY environment variable,
    which is loaded from a ".env" file placed next to this script (or from
    the real environment if you prefer to export it yourself). Create a
    ".env" file next to this script with a line like:

        DEEPL_API_KEY=your-deepl-api-key-here
"""

import sys
import io
import os
import re
import html as _html
import json
import time
from pathlib import Path
from datetime import datetime

# Force UTF-8 output so emojis don't crash on Windows cp1251 terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Directory the script lives in (used for .env, database.json, and *.ts globbing)
SCRIPT_DIR = Path(__file__).parent

# Database file for failed translations
DB_FILE = SCRIPT_DIR / "database.json"


# ─── dependency bootstrap ────────────────────────────────────────────────────

def _get_translators():
    """Install and return both DeepL and Google translators."""
    try:
        import deepl
        from deep_translator import GoogleTranslator
        return deepl, GoogleTranslator
    except ImportError:
        import subprocess
        print("📦  Installing deepl and deep-translator...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "deepl", "deep-translator"],
        )
        import deepl
        from deep_translator import GoogleTranslator
        return deepl, GoogleTranslator


def _get_dotenv():
    """Install (if needed) and return the load_dotenv function from python-dotenv."""
    try:
        from dotenv import load_dotenv
        return load_dotenv
    except ImportError:
        import subprocess
        print("📦  Installing python-dotenv...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "python-dotenv"],
        )
        from dotenv import load_dotenv
        return load_dotenv


def load_deepl_api_key() -> str:
    """
    Load the DeepL API key from a .env file next to this script (or from
    whatever is already in the environment). Exits with a clear error
    message if the key is missing.
    """
    load_dotenv = _get_dotenv()

    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        # Fall back to any .env discoverable from the current working
        # directory, and otherwise just rely on real environment variables.
        load_dotenv()

    api_key = os.getenv("DEEPL_API_KEY")

    if not api_key:
        print("❌  DEEPL_API_KEY not found.")
        print(f"    Create a file at: {env_path}")
        print("    with contents:")
        print("        DEEPL_API_KEY=your-deepl-api-key-here")
        sys.exit(1)

    return api_key


# ─── database management ─────────────────────────────────────────────────────

def load_database():
    """Load failed translations from database.json"""
    if not DB_FILE.exists():
        return {}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Warning: Could not load database.json: {e}")
        return {}


def save_database(db):
    """Save failed translations to database.json"""
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️  Warning: Could not save database.json: {e}")


def add_failed_translation(db, context_name, xml_source, lang_key, error_msg):
    """Add a failed translation to the database"""
    key = f"{context_name}::{xml_source}"
    if key not in db:
        db[key] = {
            "context": context_name,
            "source": xml_source,
            "failed_langs": {},
            "first_failed": datetime.now().isoformat(),
        }

    db[key]["failed_langs"][lang_key] = {
        "error": str(error_msg),
        "last_attempt": datetime.now().isoformat(),
        "attempt_count": db[key]["failed_langs"].get(lang_key, {}).get("attempt_count", 0) + 1
    }


def remove_successful_translation(db, context_name, xml_source, lang_key):
    """Remove a language from failed translations after successful translation"""
    key = f"{context_name}::{xml_source}"
    if key in db and lang_key in db[key]["failed_langs"]:
        del db[key]["failed_langs"][lang_key]
        # Remove the entire entry if no failed languages remain
        if not db[key]["failed_langs"]:
            del db[key]
        return True
    return False


# ─── language-code mapping ───────────────────────────────────────────────────
# .ts file stem  →  DeepL language code (primary), Google Translate code (fallback)
# Format: "ts_code": ("deepl_code", "google_code") or (None, "google_code")

TS_TO_CODES: dict[str, tuple[str | None, str | None]] = {
    ".template": (None, None),
    "af":        (None, "af"),
    "ar":        ("AR", "ar"),
    "az":        (None, "az"),
    "azb":       (None, "az"),    # South Azerbaijani → closest: Azerbaijani
    "be":        (None, "be"),
    "bg":        ("BG", "bg"),
    "bn":        (None, "bn"),
    "ca":        (None, "ca"),
    "ca@valencia": (None, "ca"),
    "ceb":       (None, "ceb"),
    "ckb":       (None, "ku"),    # Central Kurdish → Kurdish
    "cop":       (None, None),    # Coptic
    "cs":        ("CS", "cs"),
    "cy":        (None, "cy"),
    "da":        ("DA", "da"),
    "de":        ("DE", "de"),
    "de_CH":     ("DE", "de"),
    "el":        ("EL", "el"),
    "en@pirate": (None, None),    # joke language
    "en@uwu":    (None, None),    # joke language
    "en_AU":     ("EN-GB", "en"),
    "en_CA":     ("EN-US", "en"),
    "en_GB":     ("EN-GB", "en"),
    "en_NZ":     ("EN-GB", "en"),
    "eo":        (None, "eo"),
    "es":        ("ES", "es"),
    "es_UY":     ("ES", "es"),
    "et":        ("ET", "et"),
    "eu":        (None, "eu"),
    "fa":        (None, "fa"),
    "fi":        ("FI", "fi"),
    "fil":       (None, "tl"),    # Filipino → Tagalog code
    "fr":        ("FR", "fr"),
    "fr_CA":     ("FR", "fr"),
    "fur":       (None, None),    # Friulian
    "fy":        (None, "fy"),
    "ga":        (None, "ga"),
    "gl":        (None, "gl"),
    "grc":       (None, None),    # Ancient Greek
    "gv":        (None, None),    # Manx
    "haw":       (None, "haw"),
    "he":        (None, "iw"),    # Google uses "iw" for Hebrew
    "hi":        (None, "hi"),
    "hr":        (None, "hr"),
    "hu":        ("HU", "hu"),
    "hy":        (None, "hy"),
    "id":        ("ID", "id"),
    "is":        (None, "is"),
    "it":        ("IT", "it"),
    "ja":        ("JA", "ja"),
    "ja_KANJI":  ("JA", "ja"),
    "jam":       (None, None),    # Jamaican Creole
    "ka":        (None, "ka"),
    "kk":        (None, "kk"),
    "km":        (None, "km"),
    "ko":        ("KO", "ko"),
    "kxm":       (None, None),    # Northern Khmer
    "lb":        (None, "lb"),
    "lo":        (None, "lo"),
    "lt":        ("LT", "lt"),
    "lv":        ("LV", "lv"),
    "lzh":       (None, None),    # Literary Chinese
    "mk":        (None, "mk"),
    "mn":        (None, "mn"),
    "ms":        (None, "ms"),
    "mt":        (None, "mt"),
    "nan":       (None, None),    # Min Nan Chinese
    "nan_Hant":  (None, None),
    "nb":        ("NB", "no"),    # Norwegian Bokmål
    "nl":        ("NL", "nl"),
    "nn":        (None, "no"),    # Norwegian Nynorsk → Google only
    "peo":       (None, None),    # Old Persian
    "pl":        ("PL", "pl"),
    "pt":        ("PT-PT", "pt"),
    "pt_BR":     ("PT-BR", "pt"),
    "ro":        ("RO", "ro"),
    "ru":        ("RU", "ru"),
    "sk":        ("SK", "sk"),
    "sl":        ("SL", "sl"),
    "sq":        (None, "sq"),
    "sr":        (None, "sr"),
    "sv":        ("SV", "sv"),
    "szl":       (None, None),    # Silesian
    "ta":        (None, "ta"),
    "th":        (None, "th"),
    "tok":       (None, None),    # Toki Pona
    "tr":        ("TR", "tr"),
    "tt":        (None, "tt"),
    "uk":        ("UK", "uk"),
    "ur":        (None, "ur"),
    "uz":        (None, "uz"),
    "vec":       (None, None),    # Venetian
    "vi":        (None, "vi"),
    "zh":        ("ZH", "zh-CN"),
    "zh_Hant_HK": ("ZH-HANT", "zh-TW"),
    "zh_TW":     ("ZH-HANT", "zh-TW"),
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


def do_translate(
    plain_text: str,
    deepl_code: str | None,
    google_code: str | None,
    deepl_translator,
    GoogleTranslator,
    lang_key: str
) -> tuple[str, str]:
    """
    Translate plain_text (already XML-unescaped).
    If the text is an HTML wrapper, only the inner text is translated.

    Returns: (translated_text, method) where method is "deepl" or "google"
    """
    m = _HTML_RE.match(plain_text)
    text_to_translate = plain_text
    is_html_wrapper = False

    if m:
        is_html_wrapper = True
        prefix, inner, suffix = m.group(1), m.group(2), m.group(3)
        if not inner.strip():
            return plain_text, "skip"
        text_to_translate = inner

    # Try DeepL first if available
    if deepl_code:
        try:
            result = deepl_translator.translate_text(
                text_to_translate,
                source_lang="EN",
                target_lang=deepl_code
            )
            translated = result.text
            method = "deepl"
        except Exception as e:
            # Check if it's a quota exceeded error
            if "quota" in str(e).lower() or "limit" in str(e).lower():
                if google_code:
                    translated = GoogleTranslator(source="en", target=google_code).translate(text_to_translate)
                    method = "google"
                else:
                    raise
            else:
                raise
    elif google_code:
        translated = GoogleTranslator(source="en", target=google_code).translate(text_to_translate)
        method = "google"
    else:
        raise ValueError(f"No translation method available for {lang_key}")

    if is_html_wrapper:
        return f"{prefix}{translated}{suffix}", method
    return translated, method


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


# ─── translation processing ──────────────────────────────────────────────────

def process_translation(
    context_name: str,
    xml_source: str,
    plain_source: str,
    lang_key: str,
    ts_path: Path,
    deepl_translator,
    GoogleTranslator,
    db: dict,
    retry_on_fail: bool = True
) -> tuple[bool, str, str | None]:
    """
    Process a single translation.
    Returns: (success, status, error_msg)

    Args:
        retry_on_fail: If True and translation fails, retry once before saving to database
    """
    # Special case: English variants just copy the source text
    if lang_key in COPY_FROM_SOURCE:
        new_translation_xml = xml_source
        replaced = patch_ts_file(ts_path, context_name, xml_source, new_translation_xml)
        if replaced:
            remove_successful_translation(db, context_name, xml_source, lang_key)
            return True, "✅ (English copy)", None
        return False, "skip", None

    codes = TS_TO_CODES.get(lang_key)
    if codes is None:
        return False, "unsupported", None

    deepl_code, google_code = codes
    if deepl_code is None and google_code is None:
        return False, "unsupported", None

    try:
        translated_plain, method = do_translate(
            plain_source,
            deepl_code,
            google_code,
            deepl_translator,
            GoogleTranslator,
            lang_key
        )

        emoji = "🔷" if method == "deepl" else "🔶"

        new_translation_xml = xml_escape(translated_plain)
        replaced = patch_ts_file(ts_path, context_name, xml_source, new_translation_xml)

        if replaced:
            # Success! Remove from failed database
            remove_successful_translation(db, context_name, xml_source, lang_key)
            preview = translated_plain if not translated_plain.startswith("<html") else \
                      re.sub(r'<[^>]+>', '', translated_plain).strip()
            status = f"{emoji}  [{lang_key:16}] {preview[:55]}{'…' if len(preview) > 55 else ''}"
            return True, status, None
        else:
            return False, "skip", None

    except Exception as exc:
        error_msg = str(exc)

        # If retry_on_fail is enabled, try ONE more time before saving to database
        if retry_on_fail:
            try:
                time.sleep(1)  # Small delay before retry

                translated_plain, method = do_translate(
                    plain_source,
                    deepl_code,
                    google_code,
                    deepl_translator,
                    GoogleTranslator,
                    lang_key
                )

                emoji = "🔷" if method == "deepl" else "🔶"
                new_translation_xml = xml_escape(translated_plain)
                replaced = patch_ts_file(ts_path, context_name, xml_source, new_translation_xml)

                if replaced:
                    remove_successful_translation(db, context_name, xml_source, lang_key)
                    preview = translated_plain if not translated_plain.startswith("<html") else \
                              re.sub(r'<[^>]+>', '', translated_plain).strip()
                    status = f"{emoji}  [{lang_key:16}] {preview[:55]} (retry✓)"
                    return True, status, None
                else:
                    return False, "skip", None

            except Exception as retry_exc:
                # Both attempts failed - now save to database
                error_msg = str(retry_exc)
                add_failed_translation(db, context_name, xml_source, lang_key, error_msg)
                return False, f"⚠️  error: {error_msg[:40]}", error_msg

        # No retry - save to database immediately
        add_failed_translation(db, context_name, xml_source, lang_key, error_msg)
        return False, f"⚠️  error: {error_msg[:40]}", error_msg


def retry_all_failed(db, ts_dir, deepl_translator, GoogleTranslator):
    """Retry all failed translations from the database"""
    if not db:
        return 0, 0

    total_retried = 0
    total_success = 0

    print(f"🔄  Retrying {sum(len(entry['failed_langs']) for entry in db.values())} failed translation(s) from database...\n")

    for key, entry in list(db.items()):
        ctx = entry["context"]
        xml_src = entry["source"]
        plain_src = xml_unescape(xml_src)
        failed_langs = list(entry["failed_langs"].keys())

        for lang_key in failed_langs:
            ts_path = ts_dir / f"{lang_key}.ts"
            if not ts_path.exists():
                continue

            total_retried += 1
            attempt_info = entry["failed_langs"][lang_key]
            attempt_count = attempt_info.get("attempt_count", 0)

            success, status, error = process_translation(
                ctx, xml_src, plain_src, lang_key, ts_path,
                deepl_translator, GoogleTranslator, db,
                retry_on_fail=False  # Don't double-retry on database retries
            )

            if success:
                total_success += 1
                print(f"  {status} (attempt #{attempt_count + 1})")
            else:
                print(f"  ❌  [{lang_key:16}] {status} (attempt #{attempt_count + 1})")

    if total_retried > 0:
        print()

    return total_retried, total_success


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    # Check if running in retry-only mode (no arguments)
    retry_only_mode = len(sys.argv) < 3

    if not retry_only_mode:
        context_name = sys.argv[1]
        source_input = sys.argv[2]
        filter_langs = set(sys.argv[3:]) if len(sys.argv) > 3 else None
    else:
        context_name = None
        source_input = None
        filter_langs = None

    deepl, GoogleTranslator = _get_translators()

    # Load DeepL API key from .env (or environment)
    deepl_api_key = load_deepl_api_key()
    deepl_translator = deepl.Translator(deepl_api_key)

    ts_dir = SCRIPT_DIR

    # Load the failed translations database
    db = load_database()

    # ─── RETRY MODE: Only retry failed translations ──────────────────────────
    if retry_only_mode:
        if not db:
            print("\n✅  No failed translations in database. Nothing to retry.\n")
            return

        print(f"\n🔄  Retry-only mode: Processing {len(db)} failed source(s) from database\n")

        total_retried, total_success = retry_all_failed(db, ts_dir, deepl_translator, GoogleTranslator)
        total_failed = total_retried - total_success

        save_database(db)

        print("━" * 62)
        print(f"  Retry Summary:")
        print(f"  Retried: {total_retried}  |  Success: {total_success}  |  Still failing: {total_failed}")
        if total_success > 0:
            print()
            print("  🚨  YO! Don't forget to git commit + git push in halkyi8n!")
            print("  💀  I'm watching you. The files are changed. They need saving.")
        print("━" * 62)
        return

    # ─── NORMAL MODE: Retry all failed first, then new translation ───────────

    # First, retry ALL failed translations from database
    if db:
        print()
        db_retried, db_success = retry_all_failed(db, ts_dir, deepl_translator, GoogleTranslator)
        if db_retried > 0:
            print(f"  📊  Database retry: {db_success}/{db_retried} successful\n")

    # Resolve the XML source string (handles plain text and HTML inner text)
    xml_source = find_full_xml_source(ts_dir, context_name, source_input)
    if xml_source is None:
        xml_source = xml_escape(source_input)

    plain_source = xml_unescape(xml_source)

    print(f"🌍  Translating: '{source_input[:70]}{'…' if len(source_input) > 70 else ''}'")
    print(f"    Context: {context_name}\n")

    ts_files = sorted(ts_dir.glob("*.ts"))
    updated = skipped = unsupported = errors = 0
    deepl_count = google_count = 0

    for ts_path in ts_files:
        lang_key = ts_path.stem

        if filter_langs and lang_key not in filter_langs:
            continue

        success, status, error = process_translation(
            context_name, xml_source, plain_source, lang_key, ts_path,
            deepl_translator, GoogleTranslator, db,
            retry_on_fail=True  # Enable automatic retry before adding to database
        )

        if success:
            updated += 1
            if "🔷" in status:
                deepl_count += 1
            elif "🔶" in status:
                google_count += 1
            print(f"  {status}")
        elif status == "unsupported":
            unsupported += 1
        elif status == "skip":
            skipped += 1
        elif "⚠️" in status:
            errors += 1
            print(f"  ❌  [{lang_key:16}] {status}")

    # Save the database with any new failures
    save_database(db)

    # ── summary ──────────────────────────────────────────────────────────────
    print()
    print(f"  Translated: {updated}  |  DeepL: {deepl_count} 🔷  |  Google: {google_count} 🔶")
    print(f"  Skipped/already done: {skipped}  |  Unsupported langs: {unsupported}  |  Errors: {errors}")

    if errors > 0:
        print(f"\n  💾  {errors} failed translation(s) saved to database.json")
        print(f"     Run without arguments to retry: python translate_ts.py")

    print()
    print("━" * 62)
    print("  🚨  YO! Don't forget to git commit + git push in halkyi8n!")
    print("  💀  I'm watching you. The files are changed. They need saving.")
    print("  🫵  Don't make me remind you again. (I will though. Every time.)")
    print("━" * 62)


if __name__ == "__main__":
    main()