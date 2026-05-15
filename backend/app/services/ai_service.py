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
        text, is_sales = _preprocess_csv(text)
        prompt_suffix = (
            "This is aggregated sales/POS data. Treat quantities as items sold (usage), not purchased. "
            "Set quantity to a NEGATIVE number (stock going out). Return JSON array."
            if is_sales else
            "Extract all purchase line items and match to inventory. Return JSON array."
        )
        content = [{"type": "text", "text": f"File: {filename}\n\n{text}\n\n{prompt_suffix}"}]

    raw = _call(system, [{"role": "user", "content": content}], max_tokens=8192)
    return _parse_json(raw)


def _preprocess_csv(text: str) -> tuple[str, bool]:
    """
    Aggregate raw CSV before sending to Claude.
    - POS/sales files (table_number, server_id, order_id columns): group by item, sum qty → ~50 rows
    - Supplier invoices: trim to 500 rows (enough for any realistic invoice)
    Returns (processed_text, is_sales_data).
    """
    import csv as csv_mod
    from io import StringIO
    from collections import defaultdict

    try:
        sample = text[:4000]
        reader = csv_mod.DictReader(StringIO(sample))
        headers = {h.lower().strip() for h in (reader.fieldnames or [])}
    except Exception:
        return text[:60000], False  # fallback: hard char limit

    pos_signals = {"table_number", "table_no", "server_id", "server", "order_id",
                   "check_number", "check_id", "ticket_number", "pos_id"}
    is_sales = bool(headers & pos_signals)

    if is_sales:
        # Aggregate: sum quantities and revenue by item name
        totals = defaultdict(lambda: {"quantity": 0.0, "revenue": 0.0, "dates": set()})
        try:
            for row in csv_mod.DictReader(StringIO(text)):
                name = (row.get("item_name") or row.get("item") or row.get("product_name")
                        or row.get("description") or "").strip()
                qty  = float(row.get("quantity") or row.get("qty") or 1)
                rev  = float(row.get("line_total") or row.get("total") or
                             row.get("unit_price") or 0)
                date = (row.get("order_date") or row.get("date") or
                        row.get("order_datetime") or "")[:10]
                if name:
                    totals[name]["quantity"] += qty
                    totals[name]["revenue"]  += rev
                    if date:
                        totals[name]["dates"].add(date)
        except Exception:
            pass

        lines = ["item_name,total_qty_sold,total_revenue,date_range"]
        for name, d in sorted(totals.items(), key=lambda x: -x[1]["quantity"]):
            dates = sorted(d["dates"])
            dr = f"{dates[0]} to {dates[-1]}" if len(dates) > 1 else (dates[0] if dates else "")
            lines.append(f"{name},{d['quantity']:.0f},{d['revenue']:.2f},{dr}")
        return "\n".join(lines), True

    else:
        # Regular invoice/purchase file — just cap rows
        rows = text.splitlines()
        if len(rows) > 500:
            text = "\n".join(rows[:500]) + f"\n[showing first 500 of {len(rows)} rows]"
        return text, False
