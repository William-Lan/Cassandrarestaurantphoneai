from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from ..database import get_db
from ..schemas import AIReorderResponse, ReorderSuggestion
from ..services.ai_service import get_reorder_suggestions
from ..models import PurchaseOrder, PurchaseOrderItem, InventoryItem, OrderStatus

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/reorder-suggestions", response_model=AIReorderResponse)
def reorder_suggestions(db: Session = Depends(get_db)):
    """Get AI-powered reorder suggestions based on current stock and purchase history."""
    try:
        data = get_reorder_suggestions(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI service error: {exc}")

    suggestions = [ReorderSuggestion(**s) for s in data.get("suggestions", [])]
    return AIReorderResponse(
        suggestions=suggestions,
        summary=data.get("summary", ""),
        generated_at=datetime.fromisoformat(data["generated_at"]),
    )


@router.post("/create-order-from-suggestions")
def create_order_from_suggestions(db: Session = Depends(get_db)):
    """Run AI suggestions and immediately create a pending purchase order from them."""
    try:
        data = get_reorder_suggestions(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI service error: {exc}")

    suggestions = data.get("suggestions", [])
    if not suggestions:
        return {"message": "No reorder suggestions — inventory looks healthy", "order_id": None}

    order = PurchaseOrder(
        ai_generated=True,
        status=OrderStatus.pending,
        notes=f"AI-generated order: {data.get('summary', '')}",
    )
    db.add(order)
    db.flush()

    total = 0.0
    for s in suggestions:
        inv = db.query(InventoryItem).filter(InventoryItem.id == s["inventory_item_id"]).first()
        if not inv:
            continue
        unit_cost = inv.cost_per_unit
        oi = PurchaseOrderItem(
            order_id=order.id,
            inventory_item_id=inv.id,
            quantity=s["suggested_quantity"],
            unit_cost=unit_cost,
        )
        total += oi.quantity * unit_cost
        db.add(oi)

    order.total_cost = total
    db.commit()
    db.refresh(order)
    return {"message": "Purchase order created from AI suggestions", "order_id": order.id, "total_cost": total}
