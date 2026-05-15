import os
import re
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
from ..models import (
    InventoryItem, InventoryTransaction, TransactionType,
    MenuItem, MenuItemIngredient,
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=2)
FAST_MODEL  = "claude-haiku-4-5-20251001"
SMART_MODEL = "claude-sonnet-4-6"


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


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation/sizes for fuzzy name matching."""
    s = s.lower().strip()
    # Remove common size suffixes like "6oz", "22oz", "8oz" for broader matching
    s = re.sub(r'\b\d+\s*oz\b', '', s)
    s = re.sub(r'\b\d+\s*g\b', '', s)
    return re.sub(r'[^a-z0-9 ]', '', s).strip()


# ── CSV type detection & preprocessing ───────────────────────────────────────

DATA_TYPE_LABELS = {
    "pos_sales":        "POS / Sales Data",
    "inventory_count":  "Monthly Inventory Count",
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
    """Detect file type and condense CSV. Returns (processed_text, data_type)."""
    try:
        reader = csv_mod.DictReader(StringIO(text[:8000]))
        headers = {(h or "").lower().strip() for h in (reader.fieldnames or [])}
    except Exception:
        return text[:60_000], "supplier_invoice"

    data_type = _detect_csv_type(headers)

    if data_type == "pos_sales":
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
        rows = text.splitlines()
        if len(rows) > 300:
            text = "\n".join(rows[:300]) + f"\n[showing 300 of {len(rows)} rows]"
        return text, "inventory_count"

    else:
        rows = text.splitlines()
        if len(rows) > 500:
            text = "\n".join(rows[:500]) + f"\n[showing 500 of {len(rows)} rows]"
        return text, "supplier_invoice"


# ── POS → menu item → ingredient expansion (no AI tokens needed) ─────────────

def _expand_pos_via_menu(aggregated_csv: str, db: Session) -> tuple[list[dict], list[dict]]:
    """
    Parse aggregated POS sales and expand via menu item → ingredient mappings.

    Returns:
      expanded  — ingredient-level usage lines ready to import
      unmatched — POS items with no menu item match (passed to Claude fallback)
    """
    # Parse the aggregated CSV back to dicts
    sales = []
    try:
        for row in csv_mod.DictReader(StringIO(aggregated_csv)):
            name     = row.get("item_name", "").strip()
            qty_sold = float(row.get("total_qty_sold") or 0)
            date_range = row.get("date_range", "")
            # Use end date of range for the transaction date
            date = date_range.split(" to ")[-1][:10] if " to " in date_range else date_range[:10]
            if name and qty_sold > 0:
                sales.append({"name": name, "qty_sold": qty_sold, "date": date})
    except Exception:
        return [], []

    # Load all active menu items with their ingredient links
    menu_items = (
        db.query(MenuItem)
        .filter(MenuItem.is_active == True)
        .all()
    )
    menu_by_norm = {_normalize(m.name): m for m in menu_items}

    expanded  = []
    unmatched = []

    for sale in sales:
        norm      = _normalize(sale["name"])
        menu_item = menu_by_norm.get(norm)

        # Fuzzy fallback: one name contained in the other
        if not menu_item:
            for mn, mi in menu_by_norm.items():
                if mn and norm and (mn in norm or norm in mn):
                    menu_item = mi
                    break

        if menu_item:
            # Load ingredients for this menu item
            ingredient_links = (
                db.query(MenuItemIngredient)
                .filter(MenuItemIngredient.menu_item_id == menu_item.id)
                .all()
            )

            if ingredient_links:
                for link in ingredient_links:
                    inv = db.query(InventoryItem).filter(
                        InventoryItem.id == link.inventory_item_id
                    ).first()
                    if not inv:
                        continue
                    usage = sale["qty_sold"] * link.quantity_per_serving
                    expanded.append({
                        "item_name":           inv.name,
                        "quantity":            -usage,          # negative = stock out
                        "unit":                inv.unit,
                        "unit_cost":           None,
                        "total_cost":          None,
                        "supplier":            None,
                        "date":                sale["date"],
                        "confidence":          0.95,
                        "matched_inventory_id": inv.id,
                        "transaction_type":    "usage",
                        "source_menu_item":    menu_item.name,
                        "servings_sold":       sale["qty_sold"],
                    })
            else:
                # Menu item exists but no ingredients set up yet
                unmatched.append({
                    **sale,
                    "_reason": f"Menu item '{menu_item.name}' has no ingredients — add them in Menu settings",
                })
        else:
            unmatched.append({**sale, "_reason": "No matching menu item"})

    return expanded, unmatched


def _match_unmatched_pos_to_inventory(unmatched: list[dict], db: Session) -> list[dict]:
    """
    For POS items with no menu match, use Claude to try direct inventory matching.
    These are typically simple items (bottled water, bread basket) that are
    tracked directly in inventory without a recipe.
    """
    inventory_items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    if not inventory_items or not unmatched:
        return []

    inv_list = "\n".join(f"{i.id}:{i.name}({i.unit})" for i in inventory_items[:300])
    sales_list = json.dumps([{"item_name": u["name"], "qty_sold": u["qty_sold"]} for u in unmatched], indent=2)

    system = f"""Match POS sales items to raw inventory (for items sold directly without a recipe).
Existing inventory: {inv_list}

Return JSON array — one entry per input item:
{{"item_name":"<original name>","matched_inventory_id":<id or null>,"confidence":<0-1>}}

Only match when confident it's the same product. Most items won't match (they need menu setup)."""

    try:
        raw = _call(
            FAST_MODEL, system,
            [{"role": "user", "content": f"POS items:\n{sales_list}\nReturn matches."}],
            max_tokens=1024,
        )
        matches = {m["item_name"]: m.get("matched_inventory_id") for m in _parse_json(raw)}
    except Exception:
        matches = {}

    result = []
    for sale in unmatched:
        inv_id = matches.get(sale["name"])
        if inv_id:
            inv = db.query(InventoryItem).filter(InventoryItem.id == inv_id).first()
            result.append({
                "item_name":           sale["name"],
                "quantity":            -sale["qty_sold"],
                "unit":                inv.unit if inv else "unit",
                "unit_cost":           None,
                "total_cost":          None,
                "supplier":            None,
                "date":                sale.get("date"),
                "confidence":          0.7,
                "matched_inventory_id": inv_id,
                "transaction_type":    "usage",
                "source_menu_item":    None,
                "servings_sold":       sale["qty_sold"],
            })
        # Items with no match are dropped — user must set up menu items first
    return result


# ── File import — main entry point ────────────────────────────────────────────

_TYPE_INSTRUCTIONS = {
    "inventory_count": (
        "This is a physical inventory count / monthly stock take.\n"
        "- Set transaction_type = \"adjustment\" on every line\n"
        "- quantity = the COUNTED amount on hand (positive)\n"
        "- This will SET the stock level to the counted value\n"
        "- Fill unit_cost if present, otherwise null"
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
    Detect file type, extract lines, match/expand to inventory.
    POS sales:        Python menu→ingredient expansion (no AI unless unmatched items)
    Inventory count:  Claude extraction + inventory matching
    Supplier invoice: Claude extraction + inventory matching
    Returns (lines, data_type).
    """
    is_pdf   = mime_type == "application/pdf" or filename.lower().endswith(".pdf")
    is_image = mime_type.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg"))

    if is_pdf or is_image:
        # PDFs/images are almost always supplier invoices
        data_type = "supplier_invoice"
    else:
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("latin-1")
        _, data_type = _preprocess_csv(raw_text)

    # ── POS sales: expand via menu items (no AI for matched items) ────────────
    if data_type == "pos_sales":
        aggregated_csv, _ = _preprocess_csv(raw_text)
        expanded, unmatched = _expand_pos_via_menu(aggregated_csv, db)

        # For unmatched items, try direct inventory match via Claude
        direct_matches = _match_unmatched_pos_to_inventory(unmatched, db)
        all_lines = expanded + direct_matches

        # If nothing matched at all, return a helpful placeholder
        if not all_lines:
            return [], data_type

        return all_lines, data_type

    # ── Inventory count & supplier invoice: Claude extraction ─────────────────
    inventory_items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    inv_section = (
        "Existing inventory (id:name(unit)):\n" +
        "\n".join(f"{i.id}:{i.name}({i.unit})" for i in inventory_items[:300])
        if inventory_items else "Existing inventory: none yet."
    )

    if is_pdf or is_image:
        encoded    = base64.standard_b64encode(file_bytes).decode("utf-8")
        media_type = mime_type if (is_image and mime_type.startswith("image/")) else "application/pdf"
        content = [
            {
                "type": "document" if is_pdf else "image",
                "source": {"type": "base64", "media_type": media_type, "data": encoded},
            },
            {"type": "text", "text": "Extract all line items, match to inventory, return JSON array."},
        ]
    else:
        processed_text, _ = _preprocess_csv(raw_text)
        content = [{"type": "text", "text": f"File: {filename}\n\n{processed_text}\n\nReturn JSON array."}]

    type_instructions = _TYPE_INSTRUCTIONS[data_type]
    system = f"""{inv_section}

{type_instructions}

Return a JSON array only — no markdown. Each element:
{{"item_name":"<str>","quantity":<number>,"unit":"<str|null>","unit_cost":<number|null>,"total_cost":<number|null>,"supplier":"<str|null>","date":"<YYYY-MM-DD|null>","confidence":<0-1>,"matched_inventory_id":<id|null>,"transaction_type":"<historical_import|adjustment>"}}

Match inventory_id only when confident (allow abbreviations/brands). Otherwise null."""

    raw   = _call(FAST_MODEL, system, [{"role": "user", "content": content}], max_tokens=8192)
    lines = _parse_json(raw)

    # Enforce sign
    for line in lines:
        if data_type == "inventory_count" and line.get("quantity", 0) < 0:
            line["quantity"] = abs(line["quantity"])

    return lines, data_type


# ── Menu file import ─────────────────────────────────────────────────────────

def parse_menu_file(file_bytes: bytes, filename: str, mime_type: str) -> list[dict]:
    """
    Extract menu items from any format (PDF, image, CSV, text).
    Returns list of {name, category, price, description, ingredients_hint}.
    """
    is_pdf   = mime_type == "application/pdf" or filename.lower().endswith(".pdf")
    is_image = mime_type.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg"))

    system = """You extract menu items from restaurant menus.
Return a JSON array only — no markdown. Each item:
{"name":"<dish name>","category":"<section e.g. Starters|Mains|Seafood|Steaks|Sides|Desserts|Cocktails|Wine|Beer|NA Bev>","price":<number or 0>,"description":"<brief description or null>","ingredients_hint":"<raw ingredients text if listed on the menu, otherwise null>"}

Rules:
- Extract EVERY dish, drink, and item
- Infer category from the menu section heading
- price should be a number (no $ sign); use 0 if not shown
- ingredients_hint captures any ingredient list printed on the menu (e.g. "wagyu, truffle butter, roasted garlic jus")"""

    if is_pdf or is_image:
        encoded    = base64.standard_b64encode(file_bytes).decode("utf-8")
        media_type = mime_type if (is_image and mime_type.startswith("image/")) else "application/pdf"
        content = [
            {
                "type": "document" if is_pdf else "image",
                "source": {"type": "base64", "media_type": media_type, "data": encoded},
            },
            {"type": "text", "text": "Extract all menu items and return as JSON array."},
        ]
    else:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")
        content = [{"type": "text", "text": f"Menu file: {filename}\n\n{text}\n\nExtract all items as JSON array."}]

    raw = _call(FAST_MODEL, system, [{"role": "user", "content": content}], max_tokens=8192)
    return _parse_json(raw)


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
            .limit(10).all()
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
        weekly_avg = use30 / 4.0
        if weekly_avg > 0:
            trend = f"{(use7 - weekly_avg) / weekly_avg * 100:+.0f}%"
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
            f"use_7d={use7:.1f},use_30d={use30:.1f},trend={trend},"
            f"purchases=[{purchases_str}])"
        )
    return "\n".join(lines)


def get_reorder_suggestions(db: Session) -> dict:
    context = _build_inventory_context(db)
    today   = datetime.utcnow().strftime("%Y-%m-%d")

    system = """You are a restaurant inventory AI. Analyze stock and recent sales trends to suggest reorders.

Key rules:
- use_7d = ingredient units consumed last 7 days (derived from actual dish sales via recipes)
- use_30d = last 30 days; trend compares last week to the 30-day weekly average
- Positive trend (e.g. +40%) = selling MORE than usual → order sooner / order more
- Negative trend (e.g. -30%) = selling LESS than usual → may not need to reorder yet
- Respect manual rules (min, reorder_qty, lead days) when present
- urgency: critical=out/≤1 day, high=≤3 days, medium=≤7 days, low=approaching min

Respond with valid JSON only:
{"summary":"<str>","suggestions":[{"inventory_item_id":<int>,"item_name":"<str>","current_stock":<float>,"unit":"<str>","suggested_quantity":<float>,"estimated_cost":<float>,"urgency":"critical|high|medium|low","reason":"<str>","days_until_stockout":<int|null>}]}"""

    raw  = _call(SMART_MODEL, system, [{"role": "user", "content": f"Today:{today}\n\n{context}\n\nReturn JSON."}])
    data = _parse_json(raw)
    data["generated_at"] = datetime.utcnow().isoformat()
    return data
