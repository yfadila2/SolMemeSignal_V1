import os
import time
import json
import html
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests

# =========================
# CONFIG FROM ENVIRONMENT
# =========================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
MAX_TOKENS_PER_CYCLE = int(os.getenv("MAX_TOKENS_PER_CYCLE", "25"))

# New coin filter
NEW_MAX_AGE_MINUTES = int(os.getenv("NEW_MAX_AGE_MINUTES", "360"))  # 6 jam
NEW_MIN_LIQUIDITY_USD = float(os.getenv("NEW_MIN_LIQUIDITY_USD", "10000"))
NEW_MIN_VOLUME_M5_USD = float(os.getenv("NEW_MIN_VOLUME_M5_USD", "3000"))
NEW_MIN_TXNS_M5 = int(os.getenv("NEW_MIN_TXNS_M5", "30"))
NEW_MIN_BUY_SELL_RATIO = float(os.getenv("NEW_MIN_BUY_SELL_RATIO", "1.4"))
NEW_MIN_PRICE_CHANGE_M5 = float(os.getenv("NEW_MIN_PRICE_CHANGE_M5", "3"))
NEW_MAX_PRICE_CHANGE_M5 = float(os.getenv("NEW_MAX_PRICE_CHANGE_M5", "45"))
NEW_MAX_MARKET_CAP_USD = float(os.getenv("NEW_MAX_MARKET_CAP_USD", "1500000"))

# Accumulation filter
ACC_MIN_AGE_HOURS = float(os.getenv("ACC_MIN_AGE_HOURS", "24"))
ACC_MIN_LIQUIDITY_USD = float(os.getenv("ACC_MIN_LIQUIDITY_USD", "20000"))
ACC_MIN_VOLUME_H1_USD = float(os.getenv("ACC_MIN_VOLUME_H1_USD", "10000"))
ACC_MIN_VOLUME_SPIKE_RATIO = float(os.getenv("ACC_MIN_VOLUME_SPIKE_RATIO", "1.7"))
ACC_MIN_BUY_SELL_RATIO = float(os.getenv("ACC_MIN_BUY_SELL_RATIO", "1.3"))
ACC_MIN_PRICE_CHANGE_H1 = float(os.getenv("ACC_MIN_PRICE_CHANGE_H1", "0"))
ACC_MAX_PRICE_CHANGE_H1 = float(os.getenv("ACC_MAX_PRICE_CHANGE_H1", "30"))
ACC_MIN_LIQUIDITY_STABILITY = float(os.getenv("ACC_MIN_LIQUIDITY_STABILITY", "0.85"))

STATE_FILE = Path("state.json")
DEX_BASE = "https://api.dexscreener.com"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {"seen_alerts": {}, "snapshots": {}}
    return {"seen_alerts": {}, "snapshots": {}}


def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def get_json(url: str, timeout: int = 20) -> Any:
    headers = {"User-Agent": "solana-memecoin-telegram-screener/1.0"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def send_telegram(text: str, chart_url: Optional[str] = None) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID belum diisi.")
        print(text)
        return

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    if chart_url:
        payload["reply_markup"] = json.dumps({
            "inline_keyboard": [[
                {"text": "Open Dexscreener", "url": chart_url}
            ]]
        })

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, data=payload, timeout=20)
    if not r.ok:
        print("[TELEGRAM ERROR]", r.status_code, r.text)
    r.raise_for_status()


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(float(x))
    except Exception:
        return default


def pair_age_minutes(pair: Dict[str, Any]) -> Optional[float]:
    created = pair.get("pairCreatedAt")
    if not created:
        return None
    # Dexscreener generally returns milliseconds.
    if created > 10_000_000_000:
        created = created / 1000
    return max(0, (time.time() - float(created)) / 60)


def metric(pair: Dict[str, Any]) -> Dict[str, float]:
    txns = pair.get("txns") or {}
    volume = pair.get("volume") or {}
    pc = pair.get("priceChange") or {}
    liq = pair.get("liquidity") or {}

    m5 = txns.get("m5") or {}
    h1 = txns.get("h1") or {}

    buys_m5 = safe_int(m5.get("buys"))
    sells_m5 = safe_int(m5.get("sells"))
    buys_h1 = safe_int(h1.get("buys"))
    sells_h1 = safe_int(h1.get("sells"))

    return {
        "price_usd": safe_float(pair.get("priceUsd")),
        "liquidity_usd": safe_float(liq.get("usd")),
        "volume_m5": safe_float(volume.get("m5")),
        "volume_h1": safe_float(volume.get("h1")),
        "volume_h24": safe_float(volume.get("h24")),
        "price_change_m5": safe_float(pc.get("m5")),
        "price_change_h1": safe_float(pc.get("h1")),
        "price_change_h24": safe_float(pc.get("h24")),
        "buys_m5": buys_m5,
        "sells_m5": sells_m5,
        "buys_h1": buys_h1,
        "sells_h1": sells_h1,
        "txns_m5": buys_m5 + sells_m5,
        "txns_h1": buys_h1 + sells_h1,
        "buy_sell_ratio_m5": buys_m5 / max(sells_m5, 1),
        "buy_sell_ratio_h1": buys_h1 / max(sells_h1, 1),
        "market_cap": safe_float(pair.get("marketCap")) or safe_float(pair.get("fdv")),
        "fdv": safe_float(pair.get("fdv")),
    }


def choose_best_pair(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not sol_pairs:
        return None
    # Pick pair with highest liquidity. This avoids illiquid duplicate pairs.
    return max(sol_pairs, key=lambda p: safe_float((p.get("liquidity") or {}).get("usd")))


def fetch_latest_solana_tokens() -> List[str]:
    data = get_json(f"{DEX_BASE}/token-profiles/latest/v1")
    if isinstance(data, dict):
        data = [data]
    tokens = []
    for item in data:
        if item.get("chainId") == "solana" and item.get("tokenAddress"):
            tokens.append(item["tokenAddress"])
    # Unique, preserve order
    return list(dict.fromkeys(tokens))[:MAX_TOKENS_PER_CYCLE]


def fetch_pairs_for_token(token: str) -> List[Dict[str, Any]]:
    data = get_json(f"{DEX_BASE}/token-pairs/v1/solana/{token}")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("pairs"), list):
        return data["pairs"]
    return []


def score_new_coin(pair: Dict[str, Any], m: Dict[str, float], age_min: Optional[float]) -> Dict[str, Any]:
    score = 0
    reasons = []

    if age_min is not None and age_min <= NEW_MAX_AGE_MINUTES:
        score += 15
        reasons.append(f"age {age_min:.0f} menit")
    if m["liquidity_usd"] >= NEW_MIN_LIQUIDITY_USD:
        score += 20
        reasons.append(f"liq ${m['liquidity_usd']:,.0f}")
    if m["volume_m5"] >= NEW_MIN_VOLUME_M5_USD:
        score += 20
        reasons.append(f"vol 5m ${m['volume_m5']:,.0f}")
    if m["txns_m5"] >= NEW_MIN_TXNS_M5:
        score += 15
        reasons.append(f"txns 5m {m['txns_m5']:.0f}")
    if m["buy_sell_ratio_m5"] >= NEW_MIN_BUY_SELL_RATIO:
        score += 15
        reasons.append(f"buy/sell 5m {m['buy_sell_ratio_m5']:.2f}x")
    if NEW_MIN_PRICE_CHANGE_M5 <= m["price_change_m5"] <= NEW_MAX_PRICE_CHANGE_M5:
        score += 10
        reasons.append(f"price 5m {m['price_change_m5']:.1f}%")
    if 0 < m["market_cap"] <= NEW_MAX_MARKET_CAP_USD:
        score += 5
        reasons.append(f"mcap ${m['market_cap']:,.0f}")

    passed = (
        age_min is not None and age_min <= NEW_MAX_AGE_MINUTES and
        m["liquidity_usd"] >= NEW_MIN_LIQUIDITY_USD and
        m["volume_m5"] >= NEW_MIN_VOLUME_M5_USD and
        m["txns_m5"] >= NEW_MIN_TXNS_M5 and
        m["buy_sell_ratio_m5"] >= NEW_MIN_BUY_SELL_RATIO and
        NEW_MIN_PRICE_CHANGE_M5 <= m["price_change_m5"] <= NEW_MAX_PRICE_CHANGE_M5 and
        (m["market_cap"] == 0 or m["market_cap"] <= NEW_MAX_MARKET_CAP_USD)
    )

    return {"passed": passed, "score": score, "reasons": reasons}


def score_accumulation(pair: Dict[str, Any], m: Dict[str, float], prev: Optional[Dict[str, float]], age_min: Optional[float]) -> Dict[str, Any]:
    if not prev or age_min is None:
        return {"passed": False, "score": 0, "reasons": []}

    age_hours = age_min / 60
    prev_vol_h1 = max(float(prev.get("volume_h1", 0)), 1)
    prev_liq = max(float(prev.get("liquidity_usd", 0)), 1)
    vol_spike = m["volume_h1"] / prev_vol_h1
    liq_stability = m["liquidity_usd"] / prev_liq

    score = 0
    reasons = []

    if age_hours >= ACC_MIN_AGE_HOURS:
        score += 10
        reasons.append(f"age {age_hours:.1f} jam")
    if m["liquidity_usd"] >= ACC_MIN_LIQUIDITY_USD:
        score += 15
        reasons.append(f"liq ${m['liquidity_usd']:,.0f}")
    if m["volume_h1"] >= ACC_MIN_VOLUME_H1_USD:
        score += 15
        reasons.append(f"vol 1h ${m['volume_h1']:,.0f}")
    if vol_spike >= ACC_MIN_VOLUME_SPIKE_RATIO:
        score += 25
        reasons.append(f"volume spike {vol_spike:.2f}x")
    if m["buy_sell_ratio_h1"] >= ACC_MIN_BUY_SELL_RATIO:
        score += 20
        reasons.append(f"buy/sell 1h {m['buy_sell_ratio_h1']:.2f}x")
    if ACC_MIN_PRICE_CHANGE_H1 <= m["price_change_h1"] <= ACC_MAX_PRICE_CHANGE_H1:
        score += 10
        reasons.append(f"price 1h {m['price_change_h1']:.1f}%")
    if liq_stability >= ACC_MIN_LIQUIDITY_STABILITY:
        score += 5
        reasons.append(f"liq stable {liq_stability:.2f}x")

    passed = (
        age_hours >= ACC_MIN_AGE_HOURS and
        m["liquidity_usd"] >= ACC_MIN_LIQUIDITY_USD and
        m["volume_h1"] >= ACC_MIN_VOLUME_H1_USD and
        vol_spike >= ACC_MIN_VOLUME_SPIKE_RATIO and
        m["buy_sell_ratio_h1"] >= ACC_MIN_BUY_SELL_RATIO and
        ACC_MIN_PRICE_CHANGE_H1 <= m["price_change_h1"] <= ACC_MAX_PRICE_CHANGE_H1 and
        liq_stability >= ACC_MIN_LIQUIDITY_STABILITY
    )

    return {"passed": passed, "score": score, "reasons": reasons}


def format_alert(kind: str, pair: Dict[str, Any], m: Dict[str, float], score: int, reasons: List[str], age_min: Optional[float]) -> str:
    base = pair.get("baseToken") or {}
    symbol = html.escape(base.get("symbol") or "UNKNOWN")
    name = html.escape(base.get("name") or "")
    token_address = html.escape(base.get("address") or "")
    pair_address = html.escape(pair.get("pairAddress") or "")
    dex_id = html.escape(pair.get("dexId") or "")
    url = html.escape(pair.get("url") or "")

    age_text = "-" if age_min is None else (f"{age_min:.0f} menit" if age_min < 180 else f"{age_min/60:.1f} jam")
    reason_text = "\n".join([f"• {html.escape(r)}" for r in reasons])

    title = "🚨 NEW COIN SIGNAL" if kind == "new" else "🟢 ACCUMULATION SIGNAL"

    return f"""{title}

<b>{symbol}</b> {name}
DEX: <b>{dex_id}</b>
Age: <b>{age_text}</b>
Score: <b>{score}/100</b>

Price: <b>${m['price_usd']:.10f}</b>
Liquidity: <b>${m['liquidity_usd']:,.0f}</b>
Market Cap/FDV: <b>${m['market_cap']:,.0f}</b>

Vol 5m: <b>${m['volume_m5']:,.0f}</b> | Vol 1h: <b>${m['volume_h1']:,.0f}</b>
Buy/Sell 5m: <b>{m['buys_m5']:.0f}/{m['sells_m5']:.0f}</b>
Buy/Sell 1h: <b>{m['buys_h1']:.0f}/{m['sells_h1']:.0f}</b>
Change 5m: <b>{m['price_change_m5']:.1f}%</b> | 1h: <b>{m['price_change_h1']:.1f}%</b>

<b>Reasons:</b>
{reason_text}

Token:
<code>{token_address}</code>

Pair:
<code>{pair_address}</code>

Chart: {url}

⚠️ Ini sinyal scanner, bukan ajakan beli. Cek chart, liquidity, holder, dan risiko rug sebelum entry."""


def process_cycle() -> None:
    state = load_state()
    seen_alerts = state.setdefault("seen_alerts", {})
    snapshots = state.setdefault("snapshots", {})

    tokens = fetch_latest_solana_tokens()
    print(f"[{now_iso()}] Checking {len(tokens)} Solana tokens...")

    alerts_sent = 0

    for token in tokens:
        try:
            pairs = fetch_pairs_for_token(token)
            pair = choose_best_pair(pairs)
            if not pair:
                continue

            pair_id = pair.get("pairAddress") or token
            age_min = pair_age_minutes(pair)
            m = metric(pair)
            prev = snapshots.get(pair_id)

            new_result = score_new_coin(pair, m, age_min)
            acc_result = score_accumulation(pair, m, prev, age_min)

            # Prevent repeated alerts too often.
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            if new_result["passed"]:
                alert_key = f"new:{pair_id}:{today}"
                if not seen_alerts.get(alert_key):
                    text = format_alert("new", pair, m, new_result["score"], new_result["reasons"], age_min)
                    send_telegram(text, pair.get("url"))
                    seen_alerts[alert_key] = now_iso()
                    alerts_sent += 1
                    print(f"  Sent NEW alert: {pair_id}")

            if acc_result["passed"]:
                # Only alert accumulation once every 6 hours for the same pair.
                bucket = int(time.time() // (6 * 3600))
                alert_key = f"acc:{pair_id}:{bucket}"
                if not seen_alerts.get(alert_key):
                    text = format_alert("acc", pair, m, acc_result["score"], acc_result["reasons"], age_min)
                    send_telegram(text, pair.get("url"))
                    seen_alerts[alert_key] = now_iso()
                    alerts_sent += 1
                    print(f"  Sent ACC alert: {pair_id}")

            snapshots[pair_id] = {
                "price_usd": m["price_usd"],
                "liquidity_usd": m["liquidity_usd"],
                "volume_m5": m["volume_m5"],
                "volume_h1": m["volume_h1"],
                "volume_h24": m["volume_h24"],
                "buys_h1": m["buys_h1"],
                "sells_h1": m["sells_h1"],
                "timestamp": time.time(),
            }

            time.sleep(0.15)  # gentle pacing for API
        except Exception as e:
            print(f"[ERROR token={token}] {e}")
            traceback.print_exc()

    # Keep state file from growing forever.
    if len(seen_alerts) > 5000:
        keys = list(seen_alerts.keys())[-2500:]
        state["seen_alerts"] = {k: seen_alerts[k] for k in keys}

    save_state(state)
    print(f"[{now_iso()}] Cycle done. Alerts sent: {alerts_sent}")


def main() -> None:
    print("Solana Memecoin Telegram Screener started")
    print(f"Interval: {CHECK_INTERVAL_SECONDS}s | Max tokens/cycle: {MAX_TOKENS_PER_CYCLE}")
    send_telegram("✅ Solana Memecoin Screener aktif. Bot mulai memantau token Solana dari Dexscreener.")

    while True:
        try:
            process_cycle()
        except Exception as e:
            print("[FATAL CYCLE ERROR]", e)
            traceback.print_exc()
            try:
                send_telegram(f"⚠️ Screener error:\n<code>{html.escape(str(e))}</code>")
            except Exception:
                pass
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
