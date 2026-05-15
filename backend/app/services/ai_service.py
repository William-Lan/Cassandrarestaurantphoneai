import os
import json
import base64
import time
from datetime import datetime, timedelta
import anthropic
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from ..models import InventoryItem, InventoryTransaction, TransactionType, ReorderRule, ReorderRuleType

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=2)
MODEL = "claude-haiku-4-5-20251001"   # fast + cheap for parsing; saves tokens vs Sonnet


def _parse_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _call(system: str, messages: list, max_tokens: int = 4096) -> str:
    """Call Claude with simple retry on rate-limit (waits 60 s then retries once)."""
    for attempt in range(2):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return resp.content[0].text
        except anthropic.RateLimitError:
            if attempt == 0:
                time.sleep(62)   # wait out the 1-minute token window
            else:
                raise


# ── Reorder suggestions ───────────────────────────────────────────────────────

def _build_inventory_context(db: Session) -> str:
    items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    lines = []
    for item in items:
        purchases = (
            db.query(InventoryTransaction)
            .filter(
                InventoryTransaction.inventory_item_id == item.id,
                InventoryTransaction.transaction_type.in_([
                    TransactionType.purchase,
                    TransactionType.historical_import,
                ]),
            )
            .order_by(desc(InventoryTransaction.transaction_date))
            .limit(10)
            .all()
        )
        usage = (
            db.query(func.sum(InventoryTransaction.quantity_change))
            .filter(
                InventoryTransaction.inventory_item_id == item.id,
                InventoryTransaction.transaction_type == TransactionType.usage,
                InventoryTransaction.created_at >= datetime.utcnow() - timedelta(days=30),
            )
            .scalar() or 0
        )
        rule = item.reorder_rule
        rule_info = (
            f",rule={rule.rule_type.value},min={rule.manual_min_stock},qty={rule.manual_reorder_quantity},lead={rule.lead_time_days}d"
            if rule else ""
        )
        purchases_str = ";".join(
            f"{(p.transaction_date.strftime('%Y-%m-%d') if p.transaction_date else '?')}:+{p.quantity_change}@${p.unit_cost or 0:.2f}"
            for p in purchases[:5]
        )
        lines.append(
            f"{item.name}(id={item.id},cat={item.category},stock={item.current_stock}{item.unit},"
            f"min={item.min_stock},cost=${item.cost_per_unit:.2f}{rule_info},"
            f"30d_use={abs(usage):.1f},purchases=[{purchases_str}])"
        )
    return "\n".join(lines)


def get_reorder_suggestions(db: Session) -> dict:
    inventory_context = _build_inventory_context(db)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    system = """Restaurant inventory AI. Analyze stock and suggest reorders.
Respond with valid JSON only:
{"summary":"<string>","suggestions":[{"inventory_item_id":<int>,"item_name":"<str>","current_stock":<float>,"unit":"<str>","suggested_quantity":<float>,"estimated_cost":<float>,"urgency":"critical|high|medium|low","reason":"<str>","days_until_stockout":<int|null>}]}
Only suggest items that genuinely need reordering. Respect manual rules where present."""

    raw = _call(system, [{"role": "user", "content": f"Today:{today}\n\n{inventory_context}\n\nReturn JSON."}])
    data = _parse_json(raw)
    data["generated_at"] = datetime.utcnow().isoformat()
    return data


# ── File import (single combined call) ───────────────────────────────────────

def parse_and_match_file(file_bytes: bytes, filename: str, mime_type: str, db: Session) -> list[dict]:
    """
    Single Claude call: extract purchase lines from file AND match to existing inventory.
    Replaces the old two-call approach (parse then match) to halve token usage.
    """
    inventory_items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()

    # Keep inventory list compact — id + name + unit only
    if inventory_items:
        inv_list = "\n".join(f"{i.id}:{i.name}({i.unit})" for i in inventory_items[:300])
        inv_section = f"Existing inventory (id:name(unit)):\n{inv_list}"
    else:
        inv_section = "Existing inventory: none yet."

    system = f"""You read restaurant supplier invoices and return structured data.
{inv_section}

Return a JSON array only — no markdown. Each element:
{{"item_name":"<str>","quantity":<number>,"unit":"<str or null>","unit_cost":<number|null>,"total_cost":<number|null>,"supplier":"<str|null>","date":"<YYYY-MM-DD|null>","confidence":<0-1>,"matched_inventory_id":<inventory id|null>}}

Rules:
- Extract EVERY product line; use null for missing fields
- For matched_inventory_id: match to the inventory list if you are confident it is the same product (allow for abbreviations/brand names); null otherwise
- Apply header-level dates to all line items"""

    is_pdf = mime_type == "application/pdf" or filename.lower().endswith(".pdf")
    is_image = mime_type.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg"))

    if is_pdf or is_image:
        encoded = base64.standard_b64encode(file_bytes).decode("utf-8")
        media_type = mime_type if (is_image and mime_type.startswith("image/")) else "application/pdf"
        content = [
            {
                "type": "document" if is_pdf else "image",
                "source": {"type": "base64", "media_type": media_type, "data": encoded},
            },
            {"type": "text", "text": "Extract all purchase line items and match to inventory. Return JSON array."},
        ]
    else:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")
        rows = text.splitlines()
        if len(rows) > 1500:
            text = "\n".join(rows[:1500]) + f"\n[truncated: {len(rows)} rows total]"
        content = [{"type": "text", "text": f"File: {filename}\n\n{text}\n\nReturn JSON array."}]

    raw = _call(system, [{"role": "user", "content": content}], max_tokens=8192)
    return _parse_json(raw)
