import os
import json
import base64
import time
import csv as csv_mod
from io import StringIO
from collections import defaultdict
from datetime import datetime, timedelta
import anthropic
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from ..models import InventoryItem, InventoryTransaction, TransactionType

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=2)
FAST_MODEL   = "claude-haiku-4-5-20251001"   # file parsing — cheap & fast
SMART_MODEL  = "claude-sonnet-4-6"            # reorder suggestions — needs reasoning


# ── Shared helpers ────────────────────────────────────────────────────────────

def _parse_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _call(model: str, system: str, messages: list, max_tokens: int = 4096) -> str:
    for attempt in range(2):
        try:
            resp = client.messages.create(
                model=model, max_tokens=max_tokens,
                system=system, messages=messages,
            )
            return resp.content[0].text
        except anthropic.RateLimitError:
            if attempt == 0:
                time.sleep(62)
            else:
                raise


# ── CSV type detection & preprocessing ───────────────────────────────────────

DATA_TYPE_LABELS = {
    "pos_sales":       "POS / Sales Data",
    "inventory_count": "Monthly Inventory Count",
    "supplier_invoice": "Supplier Invoice / Purchase Order",
}

def _detect_csv_type(headers: set) -> str:
    pos_signals = {
        "table_number", "table_no", "server_id", "server", "order_id",
        "check_number", "check_id", "ticket_number", "guest_count", "covers",
        "cashier", "register", "shift", "seat",
    }
    count_signals = {
        "on_hand", "on_hand_qty", "physical_count", "actual_count", "count_qty",
        "inventory_date", "count_date", "par_level", "par", "variance",
        "beginning_inventory", "ending_inventory", "stock_count",
        "counted_qty", "counted", "on hand", "qty_on_hand",
    }
    if headers & pos_signals:
        return "pos_sales"
    if headers & count_signals:
        return "inventory_count"
    return "supplier_invoice"


def _preprocess_csv(text: str) -> tuple[str, str]:
    """
    Detect file type and preprocess CSV before sending to Claude.
    Returns (condensed_text, data_type).
    """
    try:
        reader = csv_mod.DictReader(StringIO(text[:8000]))
        headers = {(h or "").lower().strip() for h in (reader.fieldnames or [])}
    except Exception:
        return text[:60_000], "supplier_invoice"

    data_type = _detect_csv_type(headers)

    if data_type == "pos_sales":
        # Aggregate by menu item — 6000 rows → ~60 rows
        totals: dict = defaultdict(lambda: {"quantity": 0.0, "revenue": 0.0, "dates": set()})
        try:
            for row in csv_mod.DictReader(StringIO(text)):
                name = (
                    row.get("item_name") or row.get("item") or
                    row.get("product_name") or row.get("description") or ""
                ).strip()
                qty  = float(row.get("quantity") or row.get("qty") or 1)
                rev  = float(row.get("line_total") or row.get("total") or row.get("unit_price") or 0)
                date = (row.get("order_date") or row.get("date") or row.get("order_datetime") or "")[:10]
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
        return "\n".join(lines), "pos_sales"

    elif data_type == "inventory_count":
        # Usually already compact — just cap rows
        rows = text.splitlines()
        if len(rows) > 300:
            text = "\n".join(rows[:300]) + f"\n[showing 300 of {len(rows)} rows]"
        return text, "inventory_count"

    else:
        # Supplier invoice — cap rows
        rows = text.splitlines()
        if len(rows) > 500:
            text = "\n".join(rows[:500]) + f"\n[showing 500 of {len(rows)} rows]"
        return text, "supplier_invoice"


# ── File import — single combined Claude call ─────────────────────────────────

_TYPE_INSTRUCTIONS = {
    "pos_sales": (
        "This is aggregated POS/sales data showing menu items sold to customers.\n"
        "- Set transaction_type = \"usage\" on every line\n"
        "- Set quantity to a NEGATIVE number (stock leaving the kitchen)\n"
        "- unit_cost and supplier should be null\n"
        "- date should be the end of the reported period"
    ),
    "inventory_count": (
        "This is a physical inventory count / monthly stock take.\n"
        "- Set transaction_type = \"adjustment\" on every line\n"
        "- quantity = the COUNTED amount currently on hand (positive)\n"
        "- This will overwrite the current stock level to the counted value\n"
        "- unit_cost and supplier can be filled if present, otherwise null"
    ),
    "supplier_invoice": (
        "This is a supplier invoice or purchase order.\n"
        "- Set transaction_type = \"historical_import\" on every line\n"
        "- quantity is POSITIVE (stock arriving)\n"
        "- Fill supplier, unit_cost, date from the document"
    ),
}


def parse_and_match_file(
    file_bytes: bytes, filename: str, mime_type: str, db: Session
) -> tuple[list[dict], str]:
    """
    Single Claude call: detect file type, extract lines, match to inventory.
    Returns (lines, data_type).
    """
    inventory_items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    inv_section = (
        "Existing inventory (id:name(unit)):\n" +
        "\n".join(f"{i.id}:{i.name}({i.unit})" for i in inventory_items[:300])
        if inventory_items else "Existing inventory: none yet."
    )

    is_pdf   = mime_type == "application/pdf" or filename.lower().endswith(".pdf")
    is_image = mime_type.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg"))

    if is_pdf or is_image:
        data_type = "supplier_invoice"   # PDFs are almost always invoices/receipts
        type_instructions = _TYPE_INSTRUCTIONS[data_type]
        encoded    = base64.standard_b64encode(file_bytes).decode("utf-8")
        media_type = mime_type if (is_image and mime_type.startswith("image/")) else "application/pdf"
        content = [
            {
                "type": "document" if is_pdf else "image",
                "source": {"type": "base64", "media_type": media_type, "data": encoded},
            },
            {"type": "text", "text": "Extract all purchase line items, match to inventory, return JSON array."},
        ]
    else:
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("latin-1")
        processed_text, data_type = _preprocess_csv(raw_text)
        type_instructions = _TYPE_INSTRUCTIONS[data_type]
        content = [{"type": "text", "text": f"File: {filename}\n\n{processed_text}\n\nExtract items, match to inventory, return JSON array."}]

    system = f"""{inv_section}

{type_instructions}

Return a JSON array only — no markdown. Each element must have exactly these fields:
{{"item_name":"<str>","quantity":<number>,"unit":"<str|null>","unit_cost":<number|null>,"total_cost":<number|null>,"supplier":"<str|null>","date":"<YYYY-MM-DD|null>","confidence":<0-1>,"matched_inventory_id":<id|null>,"transaction_type":"<purchase|usage|adjustment|historical_import>"}}

Matching rule: set matched_inventory_id only when you are confident it is the same product (allow abbreviations/brand variants). Otherwise null."""

    raw = _call(FAST_MODEL, system, [{"role": "user", "content": content}], max_tokens=8192)
    lines = _parse_json(raw)

    # Enforce correct quantity sign per type
    for line in lines:
        if data_type == "pos_sales" and line.get("quantity", 0) > 0:
            line["quantity"] = -abs(line["quantity"])
        elif data_type in ("inventory_count", "supplier_invoice") and line.get("quantity", 0) < 0:
            line["quantity"] = abs(line["quantity"])

    return lines, data_type


# ── Reorder suggestions ───────────────────────────────────────────────────────

def _build_inventory_context(db: Session) -> str:
    now   = datetime.utcnow()
    ago7  = now - timedelta(days=7)
    ago30 = now - timedelta(days=30)

    items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    lines = []
    for item in items:
        purchases = (
            db.query(InventoryTransaction)
            .filter(
                InventoryTransaction.inventory_item_id == item.id,
                InventoryTransaction.transaction_type.in_([
                    TransactionType.purchase, TransactionType.historical_import,
                ]),
            )
            .order_by(desc(InventoryTransaction.transaction_date))
            .limit(10)
            .all()
        )

        def usage_sum(since):
            return abs(
                db.query(func.sum(InventoryTransaction.quantity_change))
                .filter(
                    InventoryTransaction.inventory_item_id == item.id,
                    InventoryTransaction.transaction_type == TransactionType.usage,
                    InventoryTransaction.transaction_date >= since,
                )
                .scalar() or 0
            )

        use7  = usage_sum(ago7)
        use30 = usage_sum(ago30)

        # Trend: compare last-7-day rate vs 30-day average rate
        weekly_avg = use30 / 4.0
        if weekly_avg > 0:
            trend_pct = (use7 - weekly_avg) / weekly_avg * 100
            trend = f"{trend_pct:+.0f}%"
        else:
            trend = "no data"

        rule = item.reorder_rule
        rule_info = (
            f",rule={rule.rule_type.value},min={rule.manual_min_stock},"
            f"reorder_qty={rule.manual_reorder_quantity},lead={rule.lead_time_days}d"
            if rule else ""
        )
        purchases_str = ";".join(
            f"{(p.transaction_date.strftime('%Y-%m-%d') if p.transaction_date else '?')}:+{p.quantity_change}@${p.unit_cost or 0:.2f}"
            for p in purchases[:5]
        )
        lines.append(
            f"{item.name}(id={item.id},stock={item.current_stock}{item.unit},"
            f"min={item.min_stock},cost=${item.cost_per_unit:.2f}{rule_info},"
            f"use_7d={use7:.1f},use_30d={use30:.1f},trend_vs_avg={trend},"
            f"purchases=[{purchases_str}])"
        )
    return "\n".join(lines)


def get_reorder_suggestions(db: Session) -> dict:
    context = _build_inventory_context(db)
    today   = datetime.utcnow().strftime("%Y-%m-%d")

    system = """You are a restaurant inventory AI. Analyze stock and recent sales trends to suggest reorders.

Key rules:
- use_7d = units consumed in the last 7 days; use_30d = last 30 days
- trend_vs_avg compares last week to the average week over the last month
  → positive trend (e.g. +40%) means sales are UP recently → order more / sooner
  → negative trend (e.g. -30%) means sales are DOWN → may not need to reorder yet
- Respect manual rules (min, reorder_qty, lead days) when present
- urgency: critical=out of stock or <1 day, high=<3 days, medium=<7 days, low=approaching min

Respond with valid JSON only:
{"summary":"<str>","suggestions":[{"inventory_item_id":<int>,"item_name":"<str>","current_stock":<float>,"unit":"<str>","suggested_quantity":<float>,"estimated_cost":<float>,"urgency":"critical|high|medium|low","reason":"<str>","days_until_stockout":<int|null>}]}"""

    raw  = _call(SMART_MODEL, system, [{"role": "user", "content": f"Today:{today}\n\n{context}\n\nReturn JSON."}])
    data = _parse_json(raw)
    data["generated_at"] = datetime.utcnow().isoformat()
    return data
