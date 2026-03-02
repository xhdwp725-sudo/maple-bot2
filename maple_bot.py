import os
import time
import json
import requests
from typing import Any, Dict, List, Optional, Tuple

# ✅ Railway Variables에서 TRADE_URL을 넣으면 그걸 사용, 없으면 아래 기본값 사용
DEFAULT_TRADE_URL = (
    "https://api.mapleland.gg/trade?"
    "itemCode=1050018&lowPrice=&highPrice=9999999999&lowincPDD=&highincPDD="
    "&lowUpgrade=&highUpgrade=10&lowTuc=10&highTuc=10&hapStatsName=&lowHapStatsValue=0&highHapStatsValue=100"
)
TRADE_URL = os.getenv("TRADE_URL", DEFAULT_TRADE_URL).strip()

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
PRICE_THRESHOLD = int(os.getenv("PRICE_THRESHOLD", "950000"))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

STATE_FILE = "state.json"


def load_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"notified_keys": []}


def save_state(state: Dict[str, Any]) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def tg_send(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=20)
    r.raise_for_status()


def fetch_trades() -> List[Dict[str, Any]]:
    r = requests.get(TRADE_URL, timeout=20)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("result", "data", "items"):
            if k in data and isinstance(data[k], list):
                return data[k]
    raise ValueError(f"Unexpected response shape: {type(data)}")


def extract_side_price(item: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    # mapleland 응답 기준: tradeType("buy"/"sell"), itemPrice
    side_candidates = ["tradeType", "side", "type", "orderType", "direction", "isBuy"]
    price_candidates = ["itemPrice", "price", "min_price", "minPrice", "meso", "amount", "value"]

    side_val = None
    for k in side_candidates:
        if k in item:
            side_val = item.get(k)
            break

    price_val = None
    for k in price_candidates:
        if k in item:
            price_val = item.get(k)
            break

    side_norm = None
    if isinstance(side_val, str):
        s = side_val.lower()
        if s == "buy" or "buy" in s:
            side_norm = "buy"
        elif s == "sell" or "sell" in s:
            side_norm = "sell"
    elif isinstance(side_val, bool):
        side_norm = "buy" if side_val else None

    price_int = None
    if isinstance(price_val, (int, float)):
        price_int = int(price_val)
    elif isinstance(price_val, str):
        digits = "".join(ch for ch in price_val if ch.isdigit())
        if digits:
            price_int = int(digits)

    return side_norm, price_int


def make_key(item: Dict[str, Any]) -> str:
    if "id" in item:
        return f"id:{item['id']}"
    try:
        return "hash:" + str(hash(json.dumps(item, sort_keys=True, ensure_ascii=False)))
    except Exception:
        return "hash:fallback:" + str(time.time())


def format_message(item: Dict[str, Any], price: int) -> str:
    title = "메랜지지 알림: 삽니다 조건 감지"
    item_name = item.get("itemName") or item.get("name") or ""
    trade_type = item.get("tradeType") or item.get("side") or item.get("type") or ""
    comment = item.get("comment") or ""
    created = item.get("created_at") or item.get("createdAt") or item.get("created") or ""
    _id = item.get("id", "")

    lines = [
        title,
        f"아이템: {item_name}",
        f"종류: {trade_type}",
        f"가격: {price:,} 메소",
    ]
    if _id != "":
        lines.append(f"id: {_id}")
    if created:
        lines.append(f"created: {created}")
    if comment:
        lines.append(f"메모: {comment}")

    return "\n".join(lines)


def main():
    state = load_state()
    notified = set(state.get("notified_keys", []))

    tg_send("✅ 메랜 감시 봇 시작됨 (Railway)")

    while True:
        try:
            items = fetch_trades()

            for it in items:
                side, price = extract_side_price(it)
                if side != "buy" or price is None:
                    continue
                if price < PRICE_THRESHOLD:
                    continue

                key = make_key(it)
                if key in notified:
                    continue

                tg_send(format_message(it, price))
                notified.add(key)

            if len(notified) > 1000:
                notified = set(list(notified)[-1000:])
            state["notified_keys"] = list(notified)
            save_state(state)

        except Exception as e:
            try:
                tg_send(f"⚠️ 에러: {type(e).__name__}: {e}")
            except Exception:
                pass

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
