"""Package SatKit Space Systems Book - V2 into a SpacePoint-ready .zip bundle with auto-extracted book.json.

Usage:
    python -m scripts.package_satkit_book \
        --source "C:\\Users\\ahmed\\Downloads\\SatKit Space Systems Book - V2" \
        --out "backend/storage/seed_bundles/satkit-space-systems-v2.zip"
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any


_QSTR = r"(?:`([^`]*)`|'((?:\\.|[^'\\])*)'|\"((?:\\.|[^\"\\])*)\")"


def _pick_str(m: tuple[str, ...]) -> str:
    for s in m:
        if s:
            return s
    return ""


def parse_satkit_manifest(index_html: str) -> dict[str, Any]:
    """Extract chapters, units, lessons/spreads, and curriculum profiles from SatKit V2 index.html."""
    # 1. Parse UNITS
    units_meta: dict[str, dict[str, str]] = {}
    m_units = re.search(r"const UNITS\s*=\s*\[(.*?)\];", index_html, re.S)
    if m_units:
        for um in re.finditer(
            r"\[\s*(\d+)\s*,\s*" + _QSTR + r"\s*,\s*" + _QSTR + r"\s*,\s*" + _QSTR + r"\s*,\s*" + _QSTR,
            m_units.group(1),
        ):
            num = um.group(1)
            en = _pick_str(um.groups()[1:4]).replace("\\'", "'")
            ar = _pick_str(um.groups()[4:7])
            units_meta[f"u{num}"] = {
                "key": f"u{num}",
                "code": f"U{num}",
                "part": "Physics Units",
                "title_en": en,
                "title_ar": ar,
            }

    # 2. Parse CHN (Mission Labs 1-7 + AI strand + Side Missions)
    chn_meta: dict[str, dict[str, str]] = {}
    m_chn = re.search(r"const CHN\s*=\s*\{(.*?)\};", index_html, re.S)
    if m_chn:
        for cm in re.finditer(r"(\d+)\s*:\s*\[\s*" + _QSTR + r"\s*,\s*" + _QSTR, m_chn.group(1)):
            num = cm.group(1)
            chn_meta[f"m{num}"] = {
                "key": f"m{num}",
                "code": f"M{num}",
                "part": "SatKit Mission Labs",
                "title_en": _pick_str(cm.groups()[1:4]),
                "title_ar": _pick_str(cm.groups()[4:7]),
            }

    m_extra = re.search(r"Object\.assign\(CHN,\s*\{(.*?)\}\);", index_html, re.S)
    if m_extra:
        for em in re.finditer(r"([a-z0-9]+)\s*:\s*\[\s*" + _QSTR + r"\s*,\s*" + _QSTR, m_extra.group(1)):
            k = em.group(1)
            code = "AI" if k == "a1" else k.upper()
            chn_meta[k] = {
                "key": k,
                "code": code,
                "part": "AI & Side Missions",
                "title_en": _pick_str(em.groups()[1:4]),
                "title_ar": _pick_str(em.groups()[4:7]),
            }

    # 3. Collect all lessons/spreads per chapter key
    lessons_by_ch: dict[str, list[dict[str, Any]]] = {}

    def add_lesson(ch_raw: str, spread: str, en: str, ar: str) -> None:
        if not spread or "${" in spread or spread in ("cover", "welcome", "key", "appendix"):
            return
        ch_key = f"m{ch_raw}" if ch_raw.isdigit() else ch_raw
        bucket = lessons_by_ch.setdefault(ch_key, [])
        if any(item["spread"] == spread for item in bucket):
            return
        bucket.append({
            "spread": spread,
            "title_en": en,
            "title_ar": ar,
            "game_keys": [],
        })

    # Static HTML spreads (Chapter 3, etc.)
    for sm in re.finditer(r'<div class="spread"([^>]*)>', index_html):
        attrs = sm.group(1)
        dn = re.search(r'data-name="([^"]+)"', attrs)
        dc = re.search(r'data-ch="([^"]+)"', attrs)
        ten = re.search(r'data-ten="([^"]+)"', attrs)
        tar = re.search(r'data-tar="([^"]+)"', attrs)
        if dn and dc and ten:
            add_lesson(dc.group(1), dn.group(1), ten.group(1), tar.group(1) if tar else "")

    # OPENER(ch, name, titleEn, titleAr, ...)
    for om in re.finditer(r"OPENER\(\s*(\d+)\s*,\s*" + _QSTR + r"\s*,\s*" + _QSTR + r"\s*,\s*" + _QSTR, index_html):
        ch = om.group(1)
        name = _pick_str(om.groups()[1:4])
        en = _pick_str(om.groups()[4:7])
        ar = _pick_str(om.groups()[7:10])
        add_lesson(ch, name, en, ar)

    # SPREAD(name, ch, [titleEn, titleAr], ...)
    for dm in re.finditer(
        r"SPREAD\(\s*" + _QSTR + r"\s*,\s*" + _QSTR + r"\s*,\s*\[\s*" + _QSTR + r"\s*,\s*" + _QSTR + r"\s*\]",
        index_html,
    ):
        g = dm.groups()
        name = _pick_str(g[0:3])
        ch = _pick_str(g[3:6])
        en = _pick_str(g[6:9])
        ar = _pick_str(g[9:12])
        add_lesson(ch, name, en, ar)

    # SBOX(id, ch, name, titleEn, titleAr, ...)
    for sbm in re.finditer(
        r"SBOX\(\s*" + _QSTR + r"\s*,\s*" + _QSTR + r"\s*,\s*" + _QSTR + r"\s*,\s*" + _QSTR + r"\s*,\s*" + _QSTR,
        index_html,
    ):
        g = sbm.groups()
        ch = _pick_str(g[3:6])
        name = _pick_str(g[6:9])
        en = _pick_str(g[9:12])
        ar = _pick_str(g[12:15])
        add_lesson(ch, name, en, ar)

    # CHECK(ch, name, ...)
    for ckm in re.finditer(r"CHECK\(\s*(\d+)\s*,\s*" + _QSTR, index_html):
        ch = ckm.group(1)
        name = _pick_str(ckm.groups()[1:4])
        add_lesson(ch, name, "Check and reflect", "تحقق وتأمّل")

    # 4. Assemble ordered outline matching LIB order
    ordered_keys = (
        [f"u{i}" for i in range(1, 16)]
        + [f"m{i}" for i in range(1, 8)]
        + ["a1", "s1", "s2", "s3"]
    )
    outline: list[dict[str, Any]] = []
    for k in ordered_keys:
        meta = units_meta.get(k) or chn_meta.get(k)
        if not meta:
            continue
        outline.append({
            **meta,
            "lessons": lessons_by_ch.get(k, []),
        })

    # 5. Parse PROFILES
    profiles: list[dict[str, Any]] = []
    m_prof = re.search(r"const PROFILES\s*=\s*\{(.*?)\n\};", index_html, re.S)
    if m_prof:
        pblock = m_prof.group(1)
        for pk in ("all", "uae10", "uae11", "om11b", "om11a"):
            pm = re.search(
                rf"\b{pk}\s*:\s*\{{(.*?)\n\s*\}}",
                pblock,
                re.S,
            )
            # Some profiles close on the next line or same block
            if not pm:
                pm = re.search(rf"\b{pk}\s*:\s*\{{([^}}]+)\}}", pblock, re.S)
            if not pm:
                continue
            body = pm.group(1)
            en_m = re.search(r"en\s*:\s*" + _QSTR, body)
            ar_m = re.search(r"ar\s*:\s*" + _QSTR, body)
            sub_m = re.search(r"sub\s*:\s*\[\s*" + _QSTR + r"\s*,\s*" + _QSTR, body)
            lang_m = re.search(r"lang\s*:\s*" + _QSTR, body)
            grp_m = re.search(r"groups\s*:\s*\[(.*?)\]", body, re.S)
            groups: list[str] = []
            if grp_m:
                raw_g = grp_m.group(1)
                if "...ML" in raw_g:
                    for tok in re.findall(r"'([^']+)'|\.\.\.ML", raw_g):
                        if tok:
                            groups.append(tok)
                    # Insert m1..m7 where ...ML appeared
                    parts = [p.strip() for p in raw_g.split(",")]
                    groups = []
                    for part in parts:
                        if part == "...ML":
                            groups.extend([f"m{i}" for i in range(1, 8)])
                        else:
                            sm = re.match(r"['\"]([^'\"]+)['\"]", part)
                            if sm:
                                groups.append(sm.group(1))
                else:
                    groups = re.findall(r"['\"]([^'\"]+)['\"]", raw_g)

            profiles.append({
                "key": pk,
                "label_en": _pick_str(en_m.groups()) if en_m else pk,
                "label_ar": _pick_str(ar_m.groups()) if ar_m else "",
                "subtitle_en": _pick_str(sub_m.groups()[:3]) if sub_m else "",
                "subtitle_ar": _pick_str(sub_m.groups()[3:6]) if sub_m else "",
                "default_lang": _pick_str(lang_m.groups()) if lang_m else "en",
                "groups": groups,
            })

    return {
        "title": "Space Systems with SatKit",
        "title_ar": "أنظمة الفضاء مع SatKit",
        "entry": "index.html",
        "languages": ["en", "ar"],
        "default_profile": "all",
        "profiles": profiles,
        "outline": outline,
    }


def package_book(source_dir: Path, out_zip: Path) -> dict[str, Any]:
    index_path = source_dir / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError(f"index.html not found in {source_dir}")

    html_text = index_path.read_text(encoding="utf-8")
    manifest = parse_satkit_manifest(html_text)

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    files_packed: list[str] = []
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("book.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        files_packed.append("book.json")
        for fp in sorted(source_dir.rglob("*")):
            if not fp.is_file():
                continue
            rel = fp.relative_to(source_dir).as_posix()
            if rel.startswith(".") or rel == "book.json":
                continue
            zf.write(fp, rel)
            files_packed.append(rel)

    return {
        "out_zip": str(out_zip),
        "files_packed": files_packed,
        "chapters": len(manifest["outline"]),
        "total_lessons": sum(len(ch["lessons"]) for ch in manifest["outline"]),
        "profiles": [p["key"] for p in manifest["profiles"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Package SatKit Space Systems Book V2 into a SpacePoint .zip bundle.")
    parser.add_argument(
        "--source",
        default=r"C:\Users\ahmed\Downloads\SatKit Space Systems Book - V2",
        help="Path to the unpacked SatKit book folder",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "storage" / "seed_bundles" / "satkit-space-systems-v2.zip"),
        help="Destination .zip path",
    )
    args = parser.parse_args()
    summary = package_book(Path(args.source), Path(args.out))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
