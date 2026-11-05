"""Tools exposed to the LLM.

Each tool's docstring is what the model reads to decide when to call it, so it
describes the "when" and not only the "what". Tools return JSON so the model can
read the fields unambiguously.
"""

from __future__ import annotations

import json
from typing import Literal

from langchain.tools import tool

import data
import policies


SEARCH_PAGE_SIZE = 10


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@tool
def search_products(
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    include_unavailable: bool = False,
    offset: int = 0,
) -> str:
    """Searches the store's instrument catalog.

    Use when the customer wants options or recommendations: "violões até R$ 1000",
    "tem guitarra Fender?", "ukulele para iniciante". Results are sorted from cheapest
    to most expensive and already include list price, PIX price or active promotion.
    At most 10 results come per call. If "remaining" is above 0, tell the customer how many
    more options exist, and call again with "next_offset" to get them.

    Args:
        query: words from the product name or description (brand, model, feature). E.g. "fender", "7 cordas", "nylon".
        category: one of Guitarras, Baixos, Baterias e Percussão, Teclados e Pianos, Violões,
            Instrumentos de Sopro (Madeiras), Instrumentos de Sopro (Metais), Cordas Orquestrais, Ukuleles.
        max_price: maximum price in BRL (uses the promotional price when there is one).
        min_price: minimum price in BRL.
        include_unavailable: True to also list out-of-stock, discontinued or coming-soon items.
        offset: how many results to skip (use "next_offset" from the previous call).
    """
    result = data.search_products(
        query=query,
        category=category,
        max_price=max_price,
        min_price=min_price,
        available_only=not include_unavailable,
    )
    if not result:
        return _json({"results": [], "message": "No products found with these filters."})
    page = result[offset : offset + SEARCH_PAGE_SIZE]
    remaining = max(len(result) - offset - len(page), 0)
    response = {"total_found": len(result), "remaining": remaining, "results": page}
    if remaining:
        response["next_offset"] = offset + len(page)
    return _json(response)


@tool
def get_product_details(name_or_id: str) -> str:
    """Returns price, availability, active promotion and specs of ONE product.

    Use whenever the customer asks about the price, stock or details of a specific
    model ("quanto custa o Takamine GD20?", "o Yamaha C40 tem em estoque?").
    If the product is unavailable, the result already includes similar alternatives.
    If the result has "ambiguous": true, ask the customer which option they mean.

    Args:
        name_or_id: product name (or part of it), or its numeric ID.
    """
    result = data.get_product(name_or_id)
    if result is None:
        return _json({"error": "Product not found in the catalog."})
    return _json(result)


@tool
def get_order_status(order_id: str, email_or_phone: str) -> str:
    """Looks up the status, items, tracking code and estimated delivery of an order.

    Only call it once you have BOTH pieces of information from the customer: the order
    number and the e-mail or phone used in the purchase. If either is missing, ask first.
    The tool verifies the customer's identity (LGPD) and only returns the order if the
    contact matches.

    Args:
        order_id: order number given by the customer.
        email_or_phone: e-mail or phone registered in the purchase.
    """
    return _json(data.get_order_status(order_id, email_or_phone))


@tool
def get_store_policy(
    section: Literal[
        "about_store",
        "opening_hours",
        "payment",
        "returns_and_exchanges",
        "shipping",
        "promotions",
        "customer_service",
        "warranty",
        "privacy",
    ],
) -> str:
    """Looks up the store's official policy manual (in Portuguese).

    Use it for any rule or institutional information instead of answering from memory:
    - about_store: address, phone, e-mail, what the store sells (and does NOT sell)
    - opening_hours: opening hours
    - payment: payment methods, PIX discount, installments
    - returns_and_exchanges: right of withdrawal, defects, exchanges, non-eligible items
    - shipping: shipping fees and times, carriers, tracking
    - promotions: promotion calendar and rules (stacking, stock)
    - customer_service: how to handle out-of-stock, discontinued, expired promotion, complaints
    - warranty: legal and manufacturer warranty, what is not covered
    - privacy: use of personal data (LGPD)
    """
    return policies.get_policy(section)


TOOLS = [search_products, get_product_details, get_order_status, get_store_policy]


if __name__ == "__main__":
    print(search_products.invoke({"category": "ukulele", "max_price": 300}))
    print()
    print(get_product_details.invoke({"name_or_id": "takamine gd20"}))
    print()
    print(get_order_status.invoke({"order_id": "17", "email_or_phone": "(67) 99999-0000"}))
    print()
    print(get_store_policy.invoke({"section": "returns_and_exchanges"})[:300])
    print()
    for t in TOOLS:
        print(t.name, "->", list(t.args))
