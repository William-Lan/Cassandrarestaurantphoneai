import os
import json
import base64
from datetime import datetime, timedelta
from typing import Optional
import anthropic
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from ..models import InventoryItem, InventoryTransaction, TransactionType, ReorderRule, ReorderRuleType

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"


def _build_inventory_context(db: Session) -> str:
    items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    lines = []
    for item in items:
        # Last 90 days of purchase history
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
            .limit(20)
            .all()
        )
        usage = (
            db.query(func.sum(InventoryTransaction.quantity_change))
            .filter(
                InventoryTransaction.inventory_item_id == item.id,
                InventoryTransaction.transaction_type == TransactionType.usage,
                InventoryTransaction.created_at >= datetime.utcnow() - timedelta(days=30),
            )
            .scalar()
            or 0
        )
        rule = item.reorder_rule
        rule_info = ""
        if rule:
            rule_info = (
                f", rule={rule.rule_type.value}"
                f", manual_min={rule.manual_min_stock}"
                f", manual_qty={rule.manual_reorder_quantity}"
                f", lead_days={rule.lead_time_days}"
            )

        purchase_summary = []
        for p in purchases:
            date_str = p.transaction_date.strftime("%Y-%m-%d") if p.transaction_date else "unknown date"
            purchase_summary.append(f"{date_str}: +{p.quantity_change}{item.unit} @ ${p.unit_cost or 0:.2f}")

        lines.append(
            f"- {item.name} (id={item.id}, category={item.category}): "
            f"stock={item.current_stock}{item.unit}, min={item.min_stock}, max={item.max_stock}, "
            f"cost=${item.cost_per_unit:.2f}/{item.unit}"
            f"{rule_info}, "
            f"30d_usage={abs(usage):.1f}{item.unit}, "
            f"recent_purchases=[{'; '.join(purchase_summary[:5])}]"
        )
    return "\n".join(lines)


def get_reorder_suggestions(db: Session) -> dict:
    inventory_context = _build_inventory_context(db)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    system_prompt = """You are an expert restaurant inventory manager AI.
Analyze current stock levels, purchase history, and usage patterns to recommend reorders.
You must respond with valid JSON only — no markdown, no explanation outside the JSON.

Your response must be:
{
  "summary": "brief overall status",
  "suggestions": [
    {
      "inventory_item_id": <int>,
      "item_name": "<string>",
      "current_stock": <float>,
      "unit": "<string>",
      "suggested_quantity": <float>,
      "estimated_cost": <float>,
      "urgency": "critical|high|medium|low",
      "reason": "<concise reason>",
      "days_until_stockout": <int or null>
    }
  ]
}

Rules:
- Only suggest items that actually need reordering (low stock relative to usage)
- For items with manual rules, respect the manual_min_stock and manual_reorder_quantity thresholds
- For items with ai_driven or hybrid rules, use usage patterns and purchase history to decide
- If an item has no rule, use general judgment based on min_stock setting
- urgency=critical means stock is at or below 0 or will run out within 1 day
- urgency=high means will run out within 3 days
- urgency=medium means will run out within 7 days
- urgency=low means approaching minimum but not urgent
- suggested_quantity should account for lead time days
- estimated_cost = suggested_quantity * cost_per_unit"""

    user_message = f"""Today is {today}.

Current inventory status:
{inventory_context}

Analyze this data and return reorder suggestions as JSON."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    data["generated_at"] = datetime.utcnow().isoformat()
    return data


def parse_file_for_purchases(file_bytes: bytes, filename: str, mime_type: str) -> list[dict]:
    """Use Claude to extract purchase line items from any file format."""

    system_prompt = """You are an expert at reading restaurant supplier invoices, receipts, and purchase orders.
Extract all line items and return them as a JSON array only — no markdown, no explanation.

Each item in the array must have:
{
  "item_name": "<product name>",
  "quantity": <number>,
  "unit": "<unit of measure, e.g. lb, oz, case, each, kg>",
  "unit_cost": <cost per unit or null>,
  "total_cost": <line total or null>,
  "supplier": "<supplier/vendor name or null>",
  "date": "<YYYY-MM-DD or null>",
  "confidence": <0.0 to 1.0 — how confident you are in this extraction>
}

Extract EVERY product line. Do not skip items even if data is incomplete — use null for missing fields.
If dates appear at the header level, apply them to all items."""

    is_pdf = mime_type == "application/pdf" or filename.lower().endswith(".pdf")
    is_image = mime_type.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg"))

    if is_pdf or is_image:
        encoded = base64.standard_b64encode(file_bytes).decode("utf-8")
        media_type = mime_type if (is_image and mime_type.startswith("image/")) else "application/pdf"
        content = [
            {
                "type": "document" if is_pdf else "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": encoded,
                },
            },
            {"type": "text", "text": "Extract all purchase line items from this document as JSON."},
        ]
    else:
        # CSV/Excel — decode as text
        try:
            text_content = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text_content = file_bytes.decode("latin-1")
        content = [
            {
                "type": "text",
                "text": f"File name: {filename}\n\nFile contents:\n{text_content}\n\nExtract all purchase line items as JSON.",
            }
        ]

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def match_items_to_inventory(extracted_lines: list[dict], db: Session) -> list[dict]:
    """Use Claude to fuzzy-match extracted item names to existing inventory items."""
    inventory_items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    if not inventory_items:
        return extracted_lines

    inventory_list = "\n".join(
        f"id={item.id}: {item.name} (unit={item.unit}, category={item.category})"
        for item in inventory_items
    )
    extracted_names = json.dumps([{"item_name": l["item_name"]} for l in extracted_lines], indent=2)

    system_prompt = """You match supplier invoice item names to a restaurant's existing inventory.
Return a JSON object mapping each item_name to its best matching inventory_id, or null if no good match exists.
Format: {"<item_name>": <inventory_id or null>, ...}
Only match if you are reasonably confident (same product, accounting for abbreviations and brand names).
No markdown, no explanation — JSON only."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": (
                f"Existing inventory:\n{inventory_list}\n\n"
                f"Items from invoice:\n{extracted_names}\n\n"
                "Return the mapping JSON."
            ),
        }],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    mapping = json.loads(raw)

    for line in extracted_lines:
        matched_id = mapping.get(line["item_name"])
        line["matched_inventory_id"] = matched_id
    return extracted_lines
