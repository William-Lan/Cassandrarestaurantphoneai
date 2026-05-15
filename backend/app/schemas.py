from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from .models import TransactionType, OrderStatus, ReorderRuleType


# ── Supplier ──────────────────────────────────────────────────────────────────

class SupplierBase(BaseModel):
    name: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None

class SupplierCreate(SupplierBase):
    pass

class SupplierOut(SupplierBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True


# ── Inventory Item ────────────────────────────────────────────────────────────

class InventoryItemBase(BaseModel):
    name: str
    category: str = "General"
    unit: str = "unit"
    current_stock: float = 0.0
    min_stock: float = 0.0
    max_stock: float = 100.0
    cost_per_unit: float = 0.0
    supplier_id: Optional[int] = None

class InventoryItemCreate(InventoryItemBase):
    pass

class InventoryItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    current_stock: Optional[float] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None
    cost_per_unit: Optional[float] = None
    supplier_id: Optional[int] = None
    is_active: Optional[bool] = None

class InventoryItemOut(InventoryItemBase):
    id: int
    is_active: bool
    created_at: datetime
    supplier: Optional[SupplierOut] = None
    stock_status: str = "ok"

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_status(cls, obj):
        out = cls.model_validate(obj)
        if obj.current_stock <= 0:
            out.stock_status = "critical"
        elif obj.min_stock > 0 and obj.current_stock <= obj.min_stock:
            out.stock_status = "low"
        elif obj.max_stock > 0 and obj.current_stock >= obj.max_stock * 0.9:
            out.stock_status = "full"
        else:
            out.stock_status = "ok"
        return out


# ── Inventory Transaction ─────────────────────────────────────────────────────

class TransactionCreate(BaseModel):
    inventory_item_id: int
    quantity_change: float
    transaction_type: TransactionType
    unit_cost: Optional[float] = None
    supplier_name: Optional[str] = None
    notes: Optional[str] = None
    transaction_date: Optional[datetime] = None

class TransactionOut(TransactionCreate):
    id: int
    created_at: datetime
    item: Optional[InventoryItemOut] = None
    class Config:
        from_attributes = True


# ── Menu ──────────────────────────────────────────────────────────────────────

class MenuIngredientBase(BaseModel):
    inventory_item_id: int
    quantity_per_serving: float

class MenuItemBase(BaseModel):
    name: str
    category: str = "General"
    description: Optional[str] = None
    price: float = 0.0

class MenuItemCreate(MenuItemBase):
    ingredients: List[MenuIngredientBase] = []

class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    is_active: Optional[bool] = None
    ingredients: Optional[List[MenuIngredientBase]] = None

class MenuIngredientOut(MenuIngredientBase):
    id: int
    inventory_item: Optional[InventoryItemOut] = None
    class Config:
        from_attributes = True

class MenuItemOut(MenuItemBase):
    id: int
    is_active: bool
    created_at: datetime
    ingredients: List[MenuIngredientOut] = []
    class Config:
        from_attributes = True


# ── Reorder Rule ──────────────────────────────────────────────────────────────

class ReorderRuleBase(BaseModel):
    rule_type: ReorderRuleType = ReorderRuleType.hybrid
    manual_min_stock: Optional[float] = None
    manual_reorder_quantity: Optional[float] = None
    lead_time_days: int = 2
    notes: Optional[str] = None

class ReorderRuleCreate(ReorderRuleBase):
    inventory_item_id: int

class ReorderRuleOut(ReorderRuleBase):
    id: int
    inventory_item_id: int
    is_active: bool
    class Config:
        from_attributes = True


# ── Purchase Order ────────────────────────────────────────────────────────────

class PurchaseOrderItemBase(BaseModel):
    inventory_item_id: int
    quantity: float
    unit_cost: float = 0.0

class PurchaseOrderCreate(BaseModel):
    supplier_id: Optional[int] = None
    items: List[PurchaseOrderItemBase]
    notes: Optional[str] = None

class PurchaseOrderItemOut(PurchaseOrderItemBase):
    id: int
    inventory_item: Optional[InventoryItemOut] = None
    class Config:
        from_attributes = True

class PurchaseOrderOut(BaseModel):
    id: int
    supplier_id: Optional[int] = None
    supplier: Optional[SupplierOut] = None
    status: OrderStatus
    total_cost: float
    ai_generated: bool
    notes: Optional[str] = None
    created_at: datetime
    ordered_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    items: List[PurchaseOrderItemOut] = []
    class Config:
        from_attributes = True


# ── Import ────────────────────────────────────────────────────────────────────

class ImportedPurchaseLine(BaseModel):
    item_name: str
    quantity: float
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    total_cost: Optional[float] = None
    supplier: Optional[str] = None
    date: Optional[str] = None
    matched_inventory_id: Optional[int] = None
    confidence: float = 0.0

class ImportPreview(BaseModel):
    import_id: int
    filename: str
    supplier_detected: Optional[str]
    date_range: Optional[str]
    lines: List[ImportedPurchaseLine]
    unmatched_items: List[str] = []

class ImportConfirm(BaseModel):
    import_id: int
    lines: List[ImportedPurchaseLine]
    create_missing_items: bool = True


# ── AI ────────────────────────────────────────────────────────────────────────

class ReorderSuggestion(BaseModel):
    inventory_item_id: int
    item_name: str
    current_stock: float
    unit: str
    suggested_quantity: float
    estimated_cost: float
    urgency: str
    reason: str
    days_until_stockout: Optional[int] = None

class AIReorderResponse(BaseModel):
    suggestions: List[ReorderSuggestion]
    summary: str
    generated_at: datetime


# ── Alerts ────────────────────────────────────────────────────────────────────

class Alert(BaseModel):
    item_id: int
    item_name: str
    current_stock: float
    min_stock: float
    unit: str
    severity: str
    message: str


# ── Owner Preferences ─────────────────────────────────────────────────────────

class PreferenceUpdate(BaseModel):
    value: Any
    description: Optional[str] = None

class PreferenceOut(BaseModel):
    key: str
    value: Any
    description: Optional[str] = None
    class Config:
        from_attributes = True
