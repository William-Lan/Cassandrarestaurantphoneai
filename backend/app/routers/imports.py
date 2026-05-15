from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime

from ..database import get_db, SessionLocal
from ..models import ImportRecord, InventoryItem, InventoryTransaction, TransactionType, Supplier
from ..schemas import ImportConfirm, ImportedPurchaseLine
from ..services.ai_service import parse_and_match_file, DATA_TYPE_LABELS

router = APIRouter(prefix="/import", tags=["import"])

MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB

_TX_MAP = {
    "purchase":         TransactionType.purchase,
    "usage":            TransactionType.usage,
    "adjustment":       TransactionType.adjustment,
    "historical_import": TransactionType.historical_import,
}


@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File is {len(content)//1024//1024}MB — max 25MB. Try splitting into smaller date ranges.",
        )

    record = ImportRecord(
        filename=file.filename,
        file_type=file.content_type or "application/octet-stream",
        status="processing",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    background_tasks.add_task(
        _process_import, record.id, content, file.filename,
        file.content_type or "application/octet-stream",
    )
    return {"import_id": record.id, "status": "processing", "filename": file.filename}


def _process_import(import_id: int, content: bytes, filename: str, mime_type: str):
    db = SessionLocal()
    try:
        record = db.query(ImportRecord).filter(ImportRecord.id == import_id).first()
        if not record:
            return
        try:
            lines, data_type = parse_and_match_file(content, filename, mime_type, db)

            suppliers = list({l.get("supplier") for l in lines if l.get("supplier")})
            dates     = sorted([l.get("date") for l in lines if l.get("date")])
            date_range = (
                f"{dates[0]} — {dates[-1]}" if len(dates) > 1 else (dates[0] if dates else None)
            )

            record.rows_extracted = len(lines)
            record.supplier_name  = suppliers[0] if suppliers else None
            record.extracted_data = {
                "lines":            lines,
                "data_type":        data_type,
                "supplier_detected": suppliers[0] if suppliers else None,
                "date_range":        date_range,
                "unmatched_items":  [l["item_name"] for l in lines if not l.get("matched_inventory_id")],
            }
            record.status = "pending_review"
        except Exception as exc:
            record.status = "error"
            record.error_message = str(exc)
        db.commit()
    finally:
        db.close()


@router.get("/{import_id}/status")
def get_import_status(import_id: int, db: Session = Depends(get_db)):
    record = db.query(ImportRecord).filter(ImportRecord.id == import_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Import not found")

    result = {
        "import_id":     record.id,
        "status":        record.status,
        "filename":      record.filename,
        "error_message": record.error_message,
    }

    if record.status == "pending_review" and record.extracted_data:
        d = record.extracted_data
        dt = d.get("data_type", "supplier_invoice")
        result["preview"] = {
            "import_id":        record.id,
            "filename":         record.filename,
            "data_type":        dt,
            "data_type_label":  DATA_TYPE_LABELS.get(dt, dt),
            "supplier_detected": d.get("supplier_detected"),
            "date_range":        d.get("date_range"),
            "lines":             d.get("lines", []),
            "unmatched_items":   d.get("unmatched_items", []),
        }
    return result


@router.post("/confirm")
def confirm_import(payload: ImportConfirm, db: Session = Depends(get_db)):
    record = db.query(ImportRecord).filter(ImportRecord.id == payload.import_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Import record not found")

    imported = 0
    for line in payload.lines:
        if not line.matched_inventory_id and not payload.create_missing_items:
            continue

        inv_item_id = line.matched_inventory_id

        # Auto-create inventory item for unmatched lines
        if not inv_item_id and payload.create_missing_items and line.item_name:
            supplier_obj = None
            if line.supplier:
                supplier_obj = db.query(Supplier).filter(Supplier.name == line.supplier).first()
                if not supplier_obj:
                    supplier_obj = Supplier(name=line.supplier)
                    db.add(supplier_obj)
                    db.flush()

            new_item = InventoryItem(
                name=line.item_name,
                unit=line.unit or "unit",
                cost_per_unit=line.unit_cost or 0.0,
                current_stock=0.0,
                supplier_id=supplier_obj.id if supplier_obj else None,
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
                pass

        # Determine transaction type from line metadata
        tx_type_str = line.transaction_type or "historical_import"
        tx_type     = _TX_MAP.get(tx_type_str, TransactionType.historical_import)

        item = db.query(InventoryItem).filter(InventoryItem.id == inv_item_id).first()

        if tx_type == TransactionType.adjustment:
            # Inventory count: set stock to the counted value
            old_stock       = item.current_stock if item else 0.0
            quantity_change = line.quantity - old_stock
            notes = f"Inventory count: counted {line.quantity}, was {old_stock:.2f} | {record.filename}"
        else:
            quantity_change = line.quantity
            notes = f"Imported from {record.filename}"

        tx = InventoryTransaction(
            inventory_item_id=inv_item_id,
            quantity_change=quantity_change,
            transaction_type=tx_type,
            unit_cost=line.unit_cost,
            supplier_name=line.supplier,
            source_file=record.filename,
            transaction_date=tx_date or datetime.utcnow(),
            notes=notes,
        )
        db.add(tx)

        if item:
            if tx_type == TransactionType.adjustment:
                item.current_stock = line.quantity   # set to counted value
            else:
                item.current_stock += quantity_change
            if line.unit_cost and tx_type not in (TransactionType.usage,):
                item.cost_per_unit = line.unit_cost

        imported += 1

    record.rows_imported = imported
    record.status        = "completed"
    db.commit()
    return {"imported": imported, "import_id": record.id, "status": "completed"}


@router.get("/history")
def import_history(db: Session = Depends(get_db)):
    records = db.query(ImportRecord).order_by(ImportRecord.created_at.desc()).limit(50).all()
    return [
        {
            "id":             r.id,
            "filename":       r.filename,
            "file_type":      r.file_type,
            "data_type":      (r.extracted_data or {}).get("data_type", "supplier_invoice"),
            "data_type_label": DATA_TYPE_LABELS.get((r.extracted_data or {}).get("data_type", ""), ""),
            "supplier_name":  r.supplier_name,
            "rows_extracted": r.rows_extracted,
            "rows_imported":  r.rows_imported,
            "status":         r.status,
            "error_message":  r.error_message,
            "created_at":     r.created_at,
        }
        for r in records
    ]
