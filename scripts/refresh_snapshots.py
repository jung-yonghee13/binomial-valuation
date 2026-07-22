# -*- coding: utf-8 -*-
"""폴백 스냅샷(국고채 곡선 + 피어 변동성)을 최신으로 갱신하고, 선택적으로 커밋·push한다.

배포 서버(Render 등)는 해외에 있어 SEIBRO·FinanceDataReader 실시간 수집이 막힌다.
그래서 공개 데모가 최신값을 쓰려면, 국내(한국) IP에서 주기적으로 스냅샷을 새로 떠
저장소에 밀어넣어야 한다. 이 스크립트가 그 역할을 한다.

  ⚠ 반드시 국내(한국) IP에서 실행할 것. 해외 IP에서 돌리면 수집이 막혀 실패한다.

사용:
    python scripts/refresh_snapshots.py           # 스냅샷 파일만 갱신 (커밋 안 함)
    python scripts/refresh_snapshots.py --push     # 갱신 + 변경 있으면 커밋·push
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = next((p for p in Path(__file__).resolve().parents
             if (p / "valuation" / "__init__.py").exists()), None)
if ROOT and str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from valuation import seibro, volatility  # noqa: E402

DATA = ROOT / "data"
PEERS = [
    {"name": "안랩", "ticker": "053800"},
    {"name": "더존비즈온", "ticker": "012510"},
    {"name": "한글과컴퓨터", "ticker": "030520"},
    {"name": "웹케시", "ticker": "053580"},
    {"name": "알서포트", "ticker": "131370"},
]


def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_ytm(today: str):
    c = seibro.fetch_treasury_curve(today)
    _write(DATA / "fallback_ytm_curve.json", {
        "description": "국고채 만기수익률 스냅샷 (배포 환경에서 SEIBRO 실시간 수집이 차단될 때의 폴백)",
        "source": c["source"],
        "date": c["date"],
        "maturities": c["maturities"],
        "yields": c["yields"],
    })
    return c["date"], len(c["maturities"])


def refresh_peer_vol(today: str):
    d = volatility.peer_group_volatility(PEERS, valuation_date=today, lookback_years=1.0)
    _write(DATA / "fallback_peer_vol.json", {
        "description": "피어그룹 역사적 변동성 스냅샷 (배포 환경에서 FinanceDataReader 실시간 "
                       "수집이 차단될 때의 폴백). 한국 IP(로컬)에서 실제 산출한 값.",
        "date": today,
        "data_source": d["data_source"] + " — 번들 스냅샷 폴백",
        "mean_volatility": d["mean_volatility"],
        "lookback_years": d["lookback_years"],
        "trading_days": d["trading_days"],
        "period": d["period"],
        "peers": d["peers"],
    })
    return d["mean_volatility"], len(d["peers"])


def _git(*args):
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="변경 있으면 커밋·push까지 수행")
    args = ap.parse_args()
    today = date.today().isoformat()
    print(f"[refresh] 오늘={today} · (국내 IP 필요)")

    try:
        cd, n = refresh_ytm(today)
        print(f"[YTM] OK  기준일={cd} 구간={n}개")
    except Exception as e:  # noqa: BLE001
        print(f"[YTM] 실패: {type(e).__name__}: {e}")
        print("  → 국내(한국) IP에서 실행했는지 확인하세요. SEIBRO는 해외 IP를 차단합니다.")
        sys.exit(1)

    try:
        mv, npeer = refresh_peer_vol(today)
        print(f"[PEER VOL] OK  평균변동성={mv:.4f} 피어={npeer}개")
    except Exception as e:  # noqa: BLE001
        print(f"[PEER VOL] 실패: {type(e).__name__}: {e}")
        sys.exit(1)

    if not args.push:
        print("[done] 파일 갱신 완료 (--push 미지정 → 커밋 안 함).")
        return

    files = ["data/fallback_ytm_curve.json", "data/fallback_peer_vol.json"]
    if not _git("status", "--porcelain", *files).stdout.strip():
        print("[git] 변경 없음 (스냅샷 그대로) — 커밋 생략.")
        return
    _git("add", *files)
    _git("commit", "-m", f"chore: 폴백 스냅샷 갱신 ({today}) — 국고채 곡선·피어 변동성")
    p = _git("push", "origin", "HEAD")
    print("[git push]", (p.stdout or p.stderr).strip()[-200:])
    print("[done] 커밋·push 완료 → Render/Streamlit 자동 재배포됨.")


if __name__ == "__main__":
    main()
