from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from ..database import get_db
from ..models import PurchaseOrder, PurchaseOrderItem, InventoryItem, OrderStatus
from ..schemas import PurchaseOrderCreate, PurchaseOrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/", response_model=List[PurchaseOrderOut])
def list_orders(status: str = None, db: Session = Depends(get_db)):
    q = db.query(PurchaseOrder)
    if status:
        q = q.filter(PurchaseOrder.status == status)
    return q.order_by(PurchaseOrder.created_at.desc()).all()


@router.post("/", response_model=PurchaseOrderOut, status_code=201)
def create_order(payload: PurchaseOrderCreate, db: Session = Depends(get_db)):
    order = PurchaseOrder(
        supplier_id=payload.supplier_id,
        notes=payload.notes,
        ai_generated=False,
    )
    db.add(order)
    db.flush()

    total = 0.0
    for item_data in payload.items:
        inv = db.query(InventoryItem).filter(InventoryItem.id == item_data.inventory_item_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Inventory item {item_data.inventory_item_id} not found")
        oi = PurchaseOrderItem(
            order_id=order.id,
            inventory_item_id=item_data.inventory_item_id,
            quantity=item_data.quantity,
            unit_cost=item_data.unit_cost or inv.cost_per_unit,
        )
        total += oi.quantity * oi.unit_cost
        db.add(oi)

    order.total_cost = total
    db.commit()
    db.refresh(order)
    return order


@router.get("/{order_id}", response_model=PurchaseOrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.patch("/{order_id}/status")
def update_order_status(order_id: int, status: str, db: Session = Depends(get_db)):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        new_status = OrderStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    order.status = new_status
    if new_status == OrderStatus.ordered:
        order.ordered_at = datetime.utcnow()
    elif new_status == OrderStatus.received:
        order.received_at = datetime.utcnow()
        # Update inventory stock when order is marked as received
        for oi in order.items:
            inv = db.query(InventoryItem).filter(InventoryItem.id == oi.inventory_item_id).first()
            if inv:
                inv.current_stock += oi.quantity

    db.commit()
    return {"id": order_id, "status": status}


@router.delete("/{order_id}", status_code=204)
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(PurchaseOrder).filter(PurchaseOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status in (OrderStatus.received,):
        raise HTTPException(status_code=400, detail="Cannot cancel a received order")
    order.status = OrderStatus.cancelled
    db.commit()
