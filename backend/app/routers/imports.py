from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import json

from ..database import get_db
from ..models import (
    ImportRecord, InventoryItem, InventoryTransaction,
    TransactionType, Supplier,
)
from ..schemas import ImportPreview, ImportedPurchaseLine, ImportConfirm
from ..services.ai_service import parse_file_for_purchases, match_items_to_inventory

router = APIRouter(prefix="/import", tags=["import"])

ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "text/plain",
}


@router.post("/upload", response_model=ImportPreview)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload any supplier invoice/receipt. Claude extracts and matches the data."""
    content = await file.read()
    mime = file.content_type or "application/octet-stream"

    record = ImportRecord(
        filename=file.filename,
        file_type=mime,
        status="processing",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        lines = parse_file_for_purchases(content, file.filename, mime)
        lines = match_items_to_inventory(lines, db)

        # Detect supplier and date range from extracted lines
        suppliers = list({l.get("supplier") for l in lines if l.get("supplier")})
        dates = sorted([l.get("date") for l in lines if l.get("date")])
        date_range = None
        if dates:
            date_range = f"{dates[0]} — {dates[-1]}" if dates[0] != dates[-1] else dates[0]

        unmatched = [l["item_name"] for l in lines if not l.get("matched_inventory_id")]

        record.rows_extracted = len(lines)
        record.extracted_data = lines
        record.supplier_name = suppliers[0] if suppliers else None
        record.status = "pending_review"
        db.commit()

        return ImportPreview(
            import_id=record.id,
            filename=file.filename,
            supplier_detected=suppliers[0] if suppliers else None,
            date_range=date_range,
            lines=[ImportedPurchaseLine(**l) for l in lines],
            unmatched_items=unmatched,
        )

    except Exception as exc:
        record.status = "error"
        record.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {exc}")


@router.post("/confirm")
def confirm_import(payload: ImportConfirm, db: Session = Depends(get_db)):
    """Commit the reviewed import lines into inventory transactions."""
    record = db.query(ImportRecord).filter(ImportRecord.id == payload.import_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Import record not found")

    imported = 0
    for line in payload.lines:
        if not line.matched_inventory_id and not payload.create_missing_items:
            continue

        inv_item_id = line.matched_inventory_id

        # Auto-create inventory item if needed
        if not inv_item_id and payload.create_missing_items and line.item_name:
            supplier = None
            if line.supplier:
                supplier = db.query(Supplier).filter(Supplier.name == line.supplier).first()
                if not supplier:
                    supplier = Supplier(name=line.supplier)
                    db.add(supplier)
                    db.flush()

            new_item = InventoryItem(
                name=line.item_name,
                unit=line.unit or "unit",
                cost_per_unit=line.unit_cost or 0.0,
                current_stock=0.0,
                supplier_id=supplier.id if supplier else None,
            )
            db.add(new_item)
            db.flush()
            inv_item_id = new_item.id

        if not inv_item_id:
            continue

        tx_date = None
        if line.date:
            try:
                tx_date = datetime.strptime(line.date, "%Y-%m-%d")
            except ValueError:
                tx_date = None

        tx = InventoryTransaction(
            inventory_item_id=inv_item_id,
            quantity_change=line.quantity,
            transaction_type=TransactionType.historical_import,
            unit_cost=line.unit_cost,
            supplier_name=line.supplier,
            source_file=record.filename,
            transaction_date=tx_date or datetime.utcnow(),
            notes=f"Imported from {record.filename}",
        )
        db.add(tx)

        # Update current stock for historical data
        item = db.query(InventoryItem).filter(InventoryItem.id == inv_item_id).first()
        if item:
            item.current_stock += line.quantity
            if line.unit_cost:
                item.cost_per_unit = line.unit_cost

        imported += 1

    record.rows_imported = imported
    record.status = "completed"
    db.commit()

    return {"imported": imported, "import_id": record.id, "status": "completed"}


@router.get("/history")
def import_history(db: Session = Depends(get_db)):
    records = (
        db.query(ImportRecord)
        .order_by(ImportRecord.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "file_type": r.file_type,
            "supplier_name": r.supplier_name,
            "rows_extracted": r.rows_extracted,
            "rows_imported": r.rows_imported,
            "status": r.status,
            "error_message": r.error_message,
            "created_at": r.created_at,
        }
        for r in records
    ]
