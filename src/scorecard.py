"""
거인의 어깨 — 적중률 스코어카드 v0 (로드맵 v1.3)

tickers+direction(긍정/부정)이 있는 '시황' 인사이트를 가격 데이터로 채점한다.
- 수익률: 인사이트 날짜(발언일)의 종가 → 현재가. 한국(6자리)=yfinance .KS→.KQ 폴백, 미국=티커 그대로.
- 판정 v0: 긍정→수익률 ≥ +3% 적중 / ≤ -3% 빗나감 / 그 사이 보류(중립구간). 부정은 반대.
  (표본이 얇은 초기라 보수적 문턱. 시간이 지날수록 자동으로 유의미해짐)
- kind:원칙, 중립, 티커 없는 인사이트는 채점 대상 아님(원래 채점 불가능한 성격).
- 출력: data/scorecard.json — 사이트가 전문가 헤더에 표기. 판단은 참고용, 랭킹 아님.

사용법: python src/scorecard.py [--quiet]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = ROOT / "data" / "knowledge-packs"
OUT_PATH = ROOT / "data" / "scorecard.json"
THRESH = 3.0   # 판정 문턱(%)

_price_cache: dict[str, object] = {}


def yf_symbol_candidates(ticker: str) -> list[str]:
    t = ticker.strip().upper()
    if t.isdigit() and len(t) == 6:
        return [t + ".KS", t + ".KQ"]   # 한국: 코스피 → 코스닥 폴백
    return [t]


def fetch_history(symbol: str):
    """심볼의 일별 종가 시리즈(캐시). 실패 시 None."""
    if symbol in _price_cache:
        return _price_cache[symbol]
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(period="2y", auto_adjust=True)
        closes = h["Close"] if h is not None and not h.empty else None
    except Exception:
        closes = None
    _price_cache[symbol] = closes
    return closes


def price_on(closes, date_str: str):
    """해당 날짜(휴장이면 이후 첫 거래일) 종가."""
    try:
        target = datetime.fromisoformat(date_str).date()
    except Exception:
        return None
    for _ in range(7):   # 최대 7일 앞으로 탐색
        for ts, v in closes.items():
            if ts.date() == target:
                return float(v)
        target += timedelta(days=1)
    return None


def score_insight(i: dict) -> list[dict]:
    """인사이트 1건 → 티커별 판정 목록."""
    out = []
    for tk in i.get("tickers", []):
        rec = {"ticker": tk, "date": i.get("date", ""), "topic": i.get("topic", ""),
               "direction": i.get("direction", ""), "verdict": "데이터없음", "ret": None}
        for sym in yf_symbol_candidates(tk):
            closes = fetch_history(sym)
            if closes is None or closes.empty:
                continue
            base = price_on(closes, i.get("date", ""))
            if not base:
                continue
            last = float(closes.iloc[-1])
            ret = (last / base - 1) * 100
            rec["ret"] = round(ret, 1)
            d = i.get("direction")
            if d == "긍정":
                rec["verdict"] = "적중" if ret >= THRESH else ("빗나감" if ret <= -THRESH else "보류")
            elif d == "부정":
                rec["verdict"] = "적중" if ret <= -THRESH else ("빗나감" if ret >= THRESH else "보류")
            break
        out.append(rec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    manifest = json.load(open(PACK_DIR / "manifest.json", encoding="utf-8"))
    result = {"_generated": datetime.now().isoformat()[:16], "_thresh": THRESH, "experts": {}}
    for m in manifest:
        pack = json.load(open(PACK_DIR / f"{m['slug']}.json", encoding="utf-8"))
        details = []
        for i in pack.get("insights", []):
            if i.get("kind") == "원칙" or i.get("direction") not in ("긍정", "부정") or not i.get("tickers"):
                continue
            details.extend(score_insight(i))
        if not details:
            continue
        hits = sum(1 for d in details if d["verdict"] == "적중")
        miss = sum(1 for d in details if d["verdict"] == "빗나감")
        hold = sum(1 for d in details if d["verdict"] == "보류")
        nodata = sum(1 for d in details if d["verdict"] == "데이터없음")
        result["experts"][m["slug"]] = {"name": m["name"], "hits": hits, "miss": miss,
                                        "hold": hold, "nodata": nodata, "details": details}
        if not args.quiet:
            print(f"{m['name']:24s} 적중 {hits} · 빗나감 {miss} · 보류 {hold} · 데이터없음 {nodata}")
            for d in details:
                print(f"   [{d['verdict']}] {d['ticker']} {d['direction']} ({d['date']}) → {d['ret']}%")
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n→ {OUT_PATH.relative_to(ROOT)} 저장 (전문가 {len(result['experts'])}명 채점)")


if __name__ == "__main__":
    main()
