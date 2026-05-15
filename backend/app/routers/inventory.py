from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models import InventoryItem, InventoryTransaction, TransactionType
from ..schemas import (
    InventoryItemCreate, InventoryItemUpdate, InventoryItemOut,
    TransactionCreate, TransactionOut, Alert,
)
from datetime import datetime

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _status(item: InventoryItem) -> str:
    if item.current_stock <= 0:
        return "critical"
    if item.min_stock > 0 and item.current_stock <= item.min_stock:
        return "low"
    if item.max_stock > 0 and item.current_stock >= item.max_stock * 0.9:
        return "full"
    return "ok"


@router.get("/", response_model=List[InventoryItemOut])
def list_items(
    category: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(InventoryItem).filter(InventoryItem.is_active == True)
    if category:
        q = q.filter(InventoryItem.category == category)
    items = q.order_by(InventoryItem.category, InventoryItem.name).all()

    results = []
    for item in items:
        out = InventoryItemOut.model_validate(item)
        out.stock_status = _status(item)
        if status and out.stock_status != status:
            continue
        results.append(out)
    return results


@router.post("/", response_model=InventoryItemOut, status_code=201)
def create_item(payload: InventoryItemCreate, db: Session = Depends(get_db)):
    item = InventoryItem(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    out = InventoryItemOut.model_validate(item)
    out.stock_status = _status(item)
    return out


@router.get("/alerts", response_model=List[Alert])
def get_alerts(db: Session = Depends(get_db)):
    items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    alerts = []
    for item in items:
        st = _status(item)
        if st in ("critical", "low"):
            severity = "critical" if st == "critical" else "warning"
            msg = (
                f"{item.name} is OUT OF STOCK" if item.current_stock <= 0
                else f"{item.name} is below minimum ({item.current_stock:.1f} {item.unit} remaining, min {item.min_stock})"
            )
            alerts.append(Alert(
                item_id=item.id,
                item_name=item.name,
                current_stock=item.current_stock,
                min_stock=item.min_stock,
                unit=item.unit,
                severity=severity,
                message=msg,
            ))
    return sorted(alerts, key=lambda a: (0 if a.severity == "critical" else 1))


@router.get("/{item_id}", response_model=InventoryItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    out = InventoryItemOut.model_validate(item)
    out.stock_status = _status(item)
    return out


@router.patch("/{item_id}", response_model=InventoryItemOut)
def update_item(item_id: int, payload: InventoryItemUpdate, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    out = InventoryItemOut.model_validate(item)
    out.stock_status = _status(item)
    return out


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.is_active = False
    db.commit()


@router.post("/transactions/", response_model=TransactionOut, status_code=201)
def add_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == payload.inventory_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    tx = InventoryTransaction(**payload.model_dump())
    if not tx.transaction_date:
        tx.transaction_date = datetime.utcnow()
    db.add(tx)

    item.current_stock += payload.quantity_change
    db.commit()
    db.refresh(tx)
    return tx


@router.get("/{item_id}/transactions", response_model=List[TransactionOut])
def get_transactions(item_id: int, limit: int = 50, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    txs = (
        db.query(InventoryTransaction)
        .filter(InventoryTransaction.inventory_item_id == item_id)
        .order_by(InventoryTransaction.transaction_date.desc())
        .limit(limit)
        .all()
    )
    return txs
