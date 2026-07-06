"""
youtube-mentor — 지식팩 빌더 (인덱싱 2단계)

전문가별로 (자동)영상목록·페르소나 + (Claude 큐레이션)인사이트·인용을 합쳐
data/knowledge-packs/<slug>.json 지식팩을 조립한다.

- 영상 목록: data/transcripts/<slug>/*.json 에서 자동 수집
- 페르소나: personas/<slug>.yaml
- 인사이트/인용: data/knowledge-packs/_curated/<slug>.json (Claude가 자막을 읽고 작성)
  형식: { "insights": [ {topic,tickers,direction,thesis,date,video} ], "quotes": [ {text,date,video} ] }
  이 파일이 없으면 insights/quotes 는 빈 배열로 두고 경고한다(자막만으로는 채우지 않음).

사용법:
  python src/build_knowledge_pack.py kimdante
  python src/build_knowledge_pack.py --all
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIR = ROOT / "personas"
TRANSCRIPT_DIR = ROOT / "data" / "transcripts"
PACK_DIR = ROOT / "data" / "knowledge-packs"
CURATED_DIR = PACK_DIR / "_curated"


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def video_list(slug: str) -> list[dict]:
    out = []
    # glob("*.json") 이 이미 보조 .txt 파일을 제외한다.
    # 영상 ID가 '_'로 시작할 수 있으므로(예: _UqhawRBnuo) 언더스코어 필터를 두지 않는다.
    for f in sorted(glob.glob(str(TRANSCRIPT_DIR / slug / "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        out.append(
            {
                "id": d["video_id"],
                "title": d["title"],
                "date": (d.get("published") or "")[:10],
                "url": d["url"],
                "lang": d.get("lang", "?"),
                "source": d.get("source", "youtube"),
                "char_count": d.get("char_count", 0),
            }
        )
    out.sort(key=lambda v: v["date"], reverse=True)
    return out


def build(slug: str) -> dict | None:
    persona_path = PERSONA_DIR / f"{slug}.yaml"
    if not persona_path.exists():
        print(f"   ! persona 없음: {slug}")
        return None
    persona = load_yaml(persona_path)
    videos = video_list(slug)
    if not videos:
        print(f"   ! 자막 없음(먼저 collect_transcripts 실행): {slug}")
        return None

    curated_path = CURATED_DIR / f"{slug}.json"
    if curated_path.exists():
        curated = json.load(open(curated_path, encoding="utf-8"))
        insights = curated.get("insights", [])
        quotes = curated.get("quotes", [])
    else:
        insights, quotes = [], []
        print(f"   · 큐레이션 없음(insights 비어있음): {curated_path.name}")

    latest = max(v["date"] for v in videos)
    pack = {
        "slug": slug,
        "name": persona.get("name", slug),
        "intro": (persona.get("intro", "") or "").strip(),
        "persona": {
            "domain": persona.get("domain", ""),
            "tone": (persona.get("tone", "") or "").strip(),
            "guardrails": (persona.get("guardrails", "") or "").strip(),
        },
        "last_indexed": latest,
        "video_count": len(videos),
        "insight_count": len(insights),
        "videos": videos,
        "insights": insights,
        "quotes": quotes,
    }
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    dest = PACK_DIR / f"{slug}.json"
    dest.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"   ✓ {slug}: 영상 {len(videos)} · 인사이트 {len(insights)} · 인용 {len(quotes)}"
        f"  → {dest.relative_to(ROOT)}"
    )
    return pack


def resolve_targets(args) -> list[str]:
    if args.all:
        return sorted(p.stem for p in PERSONA_DIR.glob("*.yaml") if not p.stem.startswith("_"))
    return args.slugs


def main():
    ap = argparse.ArgumentParser(description="youtube-mentor 지식팩 빌더")
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    targets = resolve_targets(args)
    if not targets:
        ap.print_help()
        sys.exit("\n대상이 없습니다.")

    print(f"지식팩 빌드 대상: {', '.join(targets)}")
    for slug in targets:
        build(slug)
    write_manifest()


def write_manifest():
    """사이트가 읽을 지식팩 목록(manifest.json) 갱신 — _curated 제외 전체 팩 스캔."""
    entries = []
    for f in sorted(PACK_DIR.glob("*.json")):
        if f.name == "manifest.json":
            continue
        p = json.load(open(f, encoding="utf-8"))
        entries.append(
            {
                "slug": p["slug"],
                "name": p["name"],
                "domain": p["persona"]["domain"],
                "intro": p.get("intro", ""),
                "video_count": p["video_count"],
                "insight_count": p["insight_count"],
                "last_indexed": p["last_indexed"],
            }
        )
    dest = PACK_DIR / "manifest.json"
    dest.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ✓ manifest.json: {len(entries)}명")


if __name__ == "__main__":
    main()
