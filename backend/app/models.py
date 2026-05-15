from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from .database import Base


class TransactionType(str, enum.Enum):
    purchase = "purchase"
    usage = "usage"
    waste = "waste"
    adjustment = "adjustment"
    historical_import = "historical_import"


class OrderStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    ordered = "ordered"
    received = "received"
    cancelled = "cancelled"


class ReorderRuleType(str, enum.Enum):
    ai_driven = "ai_driven"
    manual_threshold = "manual_threshold"
    hybrid = "hybrid"


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    contact_email = Column(String)
    contact_phone = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    inventory_items = relationship("InventoryItem", back_populates="supplier")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="General")
    unit = Column(String, default="unit")
    current_stock = Column(Float, default=0.0)
    min_stock = Column(Float, default=0.0)
    max_stock = Column(Float, default=100.0)
    cost_per_unit = Column(Float, default=0.0)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    supplier = relationship("Supplier", back_populates="inventory_items")
    transactions = relationship("InventoryTransaction", back_populates="item")
    menu_links = relationship("MenuItemIngredient", back_populates="inventory_item")
    reorder_rule = relationship("ReorderRule", back_populates="item", uselist=False)
    purchase_order_items = relationship("PurchaseOrderItem", back_populates="inventory_item")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="General")
    description = Column(Text)
    price = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ingredients = relationship("MenuItemIngredient", back_populates="menu_item")


class MenuItemIngredient(Base):
    __tablename__ = "menu_item_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    quantity_per_serving = Column(Float, nullable=False)

    menu_item = relationship("MenuItem", back_populates="ingredients")
    inventory_item = relationship("InventoryItem", back_populates="menu_links")


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    quantity_change = Column(Float, nullable=False)
    transaction_type = Column(SAEnum(TransactionType), nullable=False)
    unit_cost = Column(Float, nullable=True)
    supplier_name = Column(String, nullable=True)
    notes = Column(Text)
    source_file = Column(String, nullable=True)
    transaction_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("InventoryItem", back_populates="transactions")


class ReorderRule(Base):
    __tablename__ = "reorder_rules"

    id = Column(Integer, primary_key=True, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), unique=True, nullable=False)
    rule_type = Column(SAEnum(ReorderRuleType), default=ReorderRuleType.hybrid)
    manual_min_stock = Column(Float, nullable=True)
    manual_reorder_quantity = Column(Float, nullable=True)
    lead_time_days = Column(Integer, default=2)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)

    item = relationship("InventoryItem", back_populates="reorder_rule")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    status = Column(SAEnum(OrderStatus), default=OrderStatus.pending)
    total_cost = Column(Float, default=0.0)
    ai_generated = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ordered_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)

    supplier = relationship("Supplier", back_populates="purchase_orders")
    items = relationship("PurchaseOrderItem", back_populates="order")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_cost = Column(Float, default=0.0)

    order = relationship("PurchaseOrder", back_populates="items")
    inventory_item = relationship("InventoryItem", back_populates="purchase_order_items")


class ImportRecord(Base):
    __tablename__ = "import_records"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    supplier_name = Column(String, nullable=True)
    rows_extracted = Column(Integer, default=0)
    rows_imported = Column(Integer, default=0)
    status = Column(String, default="pending")
    error_message = Column(Text, nullable=True)
    extracted_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OwnerPreference(Base):
    __tablename__ = "owner_preferences"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(JSON, nullable=False)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
