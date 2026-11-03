"""Data layer for Empório da Música.

Loads the CSV files provided by the store and exposes deterministic query functions.
The agent never computes prices, discounts or availability on its own: it always calls
these functions (store manual, section 7.1: "never give information about prices, stock
or delivery times without checking the system").
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
FILE_PREFIX = "desafio_tecnico_ai_eng - "
PIX_DISCOUNT = 0.05

ORDER_STATUS = {
    "pending": "awaiting payment",
    "confirmed": "payment confirmed, being prepared",
    "shipped": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
}

PAYMENT_METHODS = {
    "pix": "PIX",
    "debit": "debit card",
    "boleto": "bank slip (boleto)",
}


def normalize(text: str) -> str:
    """Lowercase and strip accents, so customer input can be matched against the catalog."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def digits_only(text: str) -> str:
    return re.sub(r"\D", "", str(text))


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{FILE_PREFIX}{name}.csv")


@lru_cache(maxsize=1)
def load_data() -> dict[str, pd.DataFrame]:
    """Reads and prepares every table once."""
    categories = _read("categories")
    customers = _read("customers")
    orders = _read("orders")
    order_items = _read("order_items")
    products = _read("products")
    promotions = _read("promotions")

    # Only active promotions affect the price. If a product has more than one active
    # promotion, the biggest discount wins (promotions are not cumulative, manual 6.2).
    active_promotions = (
        promotions[promotions["is_active"] == 1]
        .sort_values("discount_percent", ascending=False)
        .drop_duplicates("product_id")
        .rename(columns={"description": "promotion_name"})
        [["product_id", "promotion_name", "discount_percent"]]
    )

    products = (
        products.merge(
            categories.rename(columns={"name": "category"})[["category_id", "category"]],
            on="category_id",
            how="left",
        )
        .merge(active_promotions, on="product_id", how="left")
    )
    products["promo_price"] = (products["price_brl"] * (1 - products["discount_percent"] / 100)).round(2)
    products["effective_price"] = products["promo_price"].fillna(products["price_brl"])
    products["available"] = (products["status"] == "active") & (products["stock_quantity"] > 0)
    products["specs"] = products["specs"].apply(_parse_specs)
    products["search_name"] = products["name"].map(normalize)
    products["search_text"] = (
        products["name"] + " " + products["category"].fillna("") + " " + products["description"].fillna("")
    ).map(normalize)

    categories["search"] = categories["name"].map(normalize)
    customers["phone_digits"] = customers["phone"].map(digits_only)
    customers["email_norm"] = customers["email"].map(normalize)

    return {
        "categories": categories,
        "customers": customers,
        "orders": orders,
        "order_items": order_items,
        "products": products,
    }


def _parse_specs(value) -> dict:
    try:
        return json.loads(value) if isinstance(value, str) else {}
    except json.JSONDecodeError:
        return {}


def _availability(row: pd.Series) -> str:
    if row["status"] == "discontinued":
        return "discontinued (no longer in the catalog)"
    if row["status"] == "coming_soon":
        return "coming soon (not yet for sale)"
    if row["stock_quantity"] <= 0:
        return "temporarily out of stock"
    return "available"


def _product_to_dict(row: pd.Series, full: bool = False) -> dict:
    item = {
        "id": int(row["product_id"]),
        "name": row["name"],
        "category": row["category"],
        "list_price": float(row["price_brl"]),
        "availability": _availability(row),
        "stock": int(row["stock_quantity"]),
    }
    if pd.notna(row["discount_percent"]):
        item["active_promotion"] = {
            "name": row["promotion_name"],
            "discount_percent": int(row["discount_percent"]),
            "promo_price": float(row["promo_price"]),
            "note": "The 5% PIX discount does not apply on top of the promotional price.",
        }
    else:
        item["pix_price"] = round(float(row["price_brl"]) * (1 - PIX_DISCOUNT), 2)
    if full:
        item["description"] = row["description"]
        item["specs"] = row["specs"]
    return item


def _stem(word: str) -> str:
    """Crude Portuguese stemmer for singular/plural matching (violão/violões, guitarra/guitarras)."""
    for suffix in ("oes", "aes", "ao"):
        if word.endswith(suffix):
            return word[: -len(suffix)]
    return word.removesuffix("s")


def _resolve_category(category: str) -> list[int]:
    """Accepts 'violão', 'violoes', 'sopro', etc. and returns the matching category IDs."""
    categories = load_data()["categories"]
    target = {_stem(w) for w in normalize(category).split() if len(w) > 2}
    mask = categories["search"].apply(lambda name: bool(target & {_stem(w) for w in re.findall(r"\w+", name)}))
    return categories.loc[mask, "category_id"].tolist()


def _match_all_words(series: pd.Series, words: list[str]) -> pd.Series:
    return series.apply(lambda text: all(w in text for w in words))


def search_products(
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    available_only: bool = True,
    limit: int = 10,
) -> list[dict]:
    """Searches products by words in the name/description, category and price range.

    The price filter uses the effective price (promotional price when a promotion is active).
    """
    df = load_data()["products"]

    if category:
        df = df[df["category_id"].isin(_resolve_category(category))]

    if query:
        words = normalize(query).split()
        # Match every word in the name first; if nothing matches, widen to the description.
        by_name = df[_match_all_words(df["search_name"], words)]
        df = by_name if not by_name.empty else df[_match_all_words(df["search_text"], words)]

    if max_price is not None:
        df = df[df["effective_price"] <= max_price]
    if min_price is not None:
        df = df[df["effective_price"] >= min_price]
    if available_only:
        df = df[df["available"]]

    df = df.sort_values("effective_price")
    return [_product_to_dict(row) for _, row in df.head(limit).iterrows()]


def get_product(name_or_id: str | int) -> dict | None:
    """Full details of a single product, looked up by ID or by (partial) name."""
    df = load_data()["products"]

    if str(name_or_id).strip().isdigit():
        found = df[df["product_id"] == int(name_or_id)]
    else:
        found = df[_match_all_words(df["search_name"], normalize(str(name_or_id)).split())]

    if found.empty:
        return None
    if len(found) > 1:
        return {
            "ambiguous": True,
            "message": "More than one product matches; ask the customer which one they mean.",
            "options": [_product_to_dict(row) for _, row in found.head(5).iterrows()],
        }

    row = found.iloc[0]
    result = _product_to_dict(row, full=True)
    if not row["available"]:
        result["alternatives"] = _alternatives(row)
    return result


def _alternatives(row: pd.Series, limit: int = 3) -> list[dict]:
    """Available products in the same category with the closest price (manual 7.3)."""
    df = load_data()["products"]
    candidates = df[
        (df["category_id"] == row["category_id"]) & df["available"] & (df["product_id"] != row["product_id"])
    ]
    distance = (candidates["price_brl"] - row["price_brl"]).abs()
    closest = candidates.loc[distance.sort_values().index].head(limit)
    return [_product_to_dict(r) for _, r in closest.iterrows()]


def get_order_status(order_id: int | str, email_or_phone: str) -> dict:
    """Order status, released only if the contact matches the order's customer (LGPD)."""
    tables = load_data()
    orders, customers = tables["orders"], tables["customers"]

    if not str(order_id).strip().isdigit():
        return {"error": "Invalid order number."}
    order = orders[orders["order_id"] == int(order_id)]
    if order.empty:
        return {"error": "Order not found."}
    order = order.iloc[0]
    customer = customers[customers["customer_id"] == order["customer_id"]].iloc[0]

    contact = str(email_or_phone).strip()
    if "@" in contact:
        verified = normalize(contact) == customer["email_norm"]
    else:
        digits = digits_only(contact)
        verified = len(digits) >= 8 and customer["phone_digits"].endswith(digits)  # with or without area code
    if not verified:
        # Generic message: does not reveal whether the order exists for someone else.
        return {"error": "Could not verify the customer's identity with the information provided."}

    items = tables["order_items"][tables["order_items"]["order_id"] == order["order_id"]].merge(
        tables["products"][["product_id", "name"]], on="product_id", how="left"
    )

    result = {
        "order_id": int(order["order_id"]),
        "customer_first_name": customer["name"].split()[0],
        "order_date": order["order_date"],
        "status": ORDER_STATUS.get(order["status"], order["status"]),
        "total": float(order["total_brl"]),
        "payment": _payment_method(order["payment_method"]),
        "items": [
            {
                "product": r["name"] if pd.notna(r["name"]) else f"product {r['product_id']}",
                "quantity": int(r["quantity"]),
            }
            for _, r in items.iterrows()
        ],
    }
    optional_fields = {
        "tracking_code": "tracking_code",
        "estimated_delivery": "estimated_delivery",
        "notes": "notes",
    }
    for column, key in optional_fields.items():
        if pd.notna(order[column]):
            result[key] = order[column]
    return result


def _payment_method(code: str) -> str:
    if code in PAYMENT_METHODS:
        return PAYMENT_METHODS[code]
    installments = re.match(r"credit_(\d+)x", str(code))
    if installments:
        return f"credit card in {installments.group(1)} installments"
    return str(code)


if __name__ == "__main__":
    from pprint import pprint

    print("== Available acoustic guitars up to R$ 1,000 ==")
    pprint(search_products(category="violões", max_price=1000))
    print("\n== Takamine GD20 ==")
    pprint(get_product("takamine gd20"))
    print("\n== Out of stock (Giannini GF-3D) ==")
    pprint(get_product(96))
    print("\n== Active promotion (id 94) ==")
    pprint(get_product(94))
    print("\n== Order 8, correct phone ==")
    pprint(get_order_status(8, "(67) 99654-7821"))
    print("\n== Order 8, wrong e-mail ==")
    pprint(get_order_status(8, "someone@jmail.com"))
