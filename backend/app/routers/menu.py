from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import MenuItem, MenuItemIngredient, InventoryItem
from ..schemas import MenuItemCreate, MenuItemUpdate, MenuItemOut

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("/", response_model=List[MenuItemOut])
def list_menu_items(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(MenuItem)
    if active_only:
        q = q.filter(MenuItem.is_active == True)
    return q.order_by(MenuItem.category, MenuItem.name).all()


@router.post("/", response_model=MenuItemOut, status_code=201)
def create_menu_item(payload: MenuItemCreate, db: Session = Depends(get_db)):
    item = MenuItem(
        name=payload.name,
        category=payload.category,
        description=payload.description,
        price=payload.price,
    )
    db.add(item)
    db.flush()

    for ing in payload.ingredients:
        inv = db.query(InventoryItem).filter(InventoryItem.id == ing.inventory_item_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Inventory item {ing.inventory_item_id} not found")
        link = MenuItemIngredient(
            menu_item_id=item.id,
            inventory_item_id=ing.inventory_item_id,
            quantity_per_serving=ing.quantity_per_serving,
        )
        db.add(link)

    db.commit()
    db.refresh(item)
    return item


@router.get("/{item_id}", response_model=MenuItemOut)
def get_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return item


@router.patch("/{item_id}", response_model=MenuItemOut)
def update_menu_item(item_id: int, payload: MenuItemUpdate, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    for field in ("name", "category", "description", "price", "is_active"):
        val = getattr(payload, field, None)
        if val is not None:
            setattr(item, field, val)

    if payload.ingredients is not None:
        db.query(MenuItemIngredient).filter(MenuItemIngredient.menu_item_id == item_id).delete()
        for ing in payload.ingredients:
            link = MenuItemIngredient(
                menu_item_id=item.id,
                inventory_item_id=ing.inventory_item_id,
                quantity_per_serving=ing.quantity_per_serving,
            )
            db.add(link)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def deactivate_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    item.is_active = False
    db.commit()
