from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import OwnerPreference, ReorderRule, ReorderRuleType
from ..schemas import PreferenceUpdate, PreferenceOut, ReorderRuleCreate, ReorderRuleOut

router = APIRouter(prefix="/preferences", tags=["preferences"])

DEFAULT_PREFERENCES = {
    "restaurant_name": {"value": "My Restaurant", "description": "Restaurant name"},
    "auto_suggest_reorders": {"value": True, "description": "Automatically show AI reorder suggestions"},
    "alert_email": {"value": "", "description": "Email for low stock alerts"},
    "default_lead_time_days": {"value": 2, "description": "Default supplier lead time in days"},
    "currency": {"value": "USD", "description": "Currency for cost display"},
}


@router.get("/", response_model=List[PreferenceOut])
def list_preferences(db: Session = Depends(get_db)):
    prefs = db.query(OwnerPreference).all()
    pref_map = {p.key: p for p in prefs}

    results = []
    for key, defaults in DEFAULT_PREFERENCES.items():
        if key in pref_map:
            results.append(PreferenceOut.model_validate(pref_map[key]))
        else:
            results.append(PreferenceOut(key=key, **defaults))
    # Include any custom prefs not in defaults
    for p in prefs:
        if p.key not in DEFAULT_PREFERENCES:
            results.append(PreferenceOut.model_validate(p))
    return results


@router.put("/{key}", response_model=PreferenceOut)
def set_preference(key: str, payload: PreferenceUpdate, db: Session = Depends(get_db)):
    pref = db.query(OwnerPreference).filter(OwnerPreference.key == key).first()
    if pref:
        pref.value = payload.value
        if payload.description:
            pref.description = payload.description
    else:
        pref = OwnerPreference(key=key, value=payload.value, description=payload.description)
        db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


@router.get("/reorder-rules/", response_model=List[ReorderRuleOut])
def list_reorder_rules(db: Session = Depends(get_db)):
    return db.query(ReorderRule).filter(ReorderRule.is_active == True).all()


@router.post("/reorder-rules/", response_model=ReorderRuleOut, status_code=201)
def create_or_update_reorder_rule(payload: ReorderRuleCreate, db: Session = Depends(get_db)):
    existing = db.query(ReorderRule).filter(
        ReorderRule.inventory_item_id == payload.inventory_item_id
    ).first()
    if existing:
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing

    rule = ReorderRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/reorder-rules/{rule_id}", status_code=204)
def delete_reorder_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ReorderRule).filter(ReorderRule.id == rule_id).first()
    if rule:
        rule.is_active = False
        db.commit()
