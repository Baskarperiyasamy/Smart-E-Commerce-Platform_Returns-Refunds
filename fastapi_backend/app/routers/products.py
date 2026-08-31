from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc

from app.database import get_db
from app.dependencies import require_roles
from app import models, schemas

router = APIRouter(prefix="/products", tags=["Products"])

SORTABLE_FIELDS = {
    "price": models.Product.price,
    "popularity": models.Product.popularity,
    "name": models.Product.name,
}


def _apply_filters(query, category, min_price, max_price, in_stock, sort_by, order):
    if category:
        query = query.filter(models.Product.category == category)
    if min_price is not None:
        query = query.filter(models.Product.price >= min_price)
    if max_price is not None:
        query = query.filter(models.Product.price <= max_price)
    if in_stock:
        query = query.filter(models.Product.stock > 0)

    if sort_by and sort_by in SORTABLE_FIELDS:
        column = SORTABLE_FIELDS[sort_by]
        query = query.order_by(desc(column) if order == "desc" else asc(column))

    return query


@router.get("/", response_model=list[schemas.ProductOut])
def list_products(
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    sort_by: Optional[str] = None,
    order: Optional[str] = "asc",
    db: Session = Depends(get_db),
):
    query = _apply_filters(db.query(models.Product), category, min_price, max_price, in_stock, sort_by, order)
    return query.all()


@router.get("/category/{category}", response_model=list[schemas.ProductOut])
def list_products_by_category(
    category: str,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    sort_by: Optional[str] = None,
    order: Optional[str] = "asc",
    db: Session = Depends(get_db),
):
    query = _apply_filters(db.query(models.Product), category, min_price, max_price, in_stock, sort_by, order)
    return query.all()


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("/", response_model=schemas.ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin")),
):
    product = models.Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: str,
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin")),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    for field, value in payload.model_dump().items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("admin")),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    db.delete(product)
    db.commit()
    return None
