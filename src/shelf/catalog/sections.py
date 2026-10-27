"""Shop sections (Snacks, Cold drinks): made from item categories, then arranged by the seller.

Items without a section are put in the section for their category group, creating it at the end of
the list the first time that group appears. The seller can rename, reorder and add sections and move
items between them; those choices are never undone automatically.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shelf.db.models import Product, Section, Workspace

# category -> group key; group key -> (English name, Hindi name, category for items added by hand)
GROUP_OF: dict[str, str] = {
    "saree": "sarees",
    "womens_clothing": "clothing",
    "mens_clothing": "clothing",
    "scarf_dupatta": "clothing",
    "womens_sandals": "footwear",
    "womens_slippers": "footwear",
    "womens_flats": "footwear",
    "womens_shoes": "footwear",
    "mens_sandals": "footwear",
    "mens_shoes": "footwear",
    "mens_footwear": "footwear",
    "kids_shoes": "footwear",
    "footwear": "footwear",
    "bracelets_bangles": "jewellery",
    "home_decor": "home",
    "decorative_accents": "home",
    "baskets": "home",
    "arts_crafts": "home",
    "spices": "masala",
    "condiments_sauces": "masala",
    "snacks": "snacks",
    "grains": "staples",
    "tea_coffee": "tea",
    "dairy": "dairy",
    "food": "food",
    "bakery_bread": "bakery",
    "candy_chocolate": "sweets",
    "soda": "drinks",
    "juice": "drinks",
    "water": "drinks",
    "energy_drinks": "drinks",
    "beverages": "drinks",
    "disposable_diapers": "baby",
    "other": "other",
}
GROUPS: dict[str, tuple[str, str, str]] = {
    "sarees": ("Sarees", "साड़ियाँ", "saree"),
    "clothing": ("Clothing", "कपड़े", "womens_clothing"),
    "footwear": ("Footwear", "जूते-चप्पल", "footwear"),
    "jewellery": ("Bangles and jewellery", "चूड़ियाँ और गहने", "bracelets_bangles"),
    "home": ("Home and handicrafts", "घर और हस्तशिल्प", "home_decor"),
    "masala": ("Masala and sauces", "मसाले और सॉस", "spices"),
    "snacks": ("Snacks", "नमकीन और स्नैक्स", "snacks"),
    "staples": ("Atta, rice and dal", "आटा, चावल, दाल", "grains"),
    "tea": ("Tea and coffee", "चाय और कॉफ़ी", "tea_coffee"),
    "dairy": ("Dairy", "डेयरी", "dairy"),
    "food": ("Food", "खाने का सामान", "food"),
    "bakery": ("Bread and bakery", "ब्रेड और बेकरी", "bakery_bread"),
    "sweets": ("Chocolates and sweets", "चॉकलेट और टॉफ़ी", "candy_chocolate"),
    "drinks": ("Cold drinks", "ठंडे पेय", "beverages"),
    "baby": ("Baby care", "बच्चों का सामान", "disposable_diapers"),
    "other": ("More items", "और सामान", "other"),
}


def category_for(section: Section | None) -> str:
    """The category to give an item added by hand to this section."""
    if section is None or section.category not in GROUPS:
        return "other"
    return GROUPS[section.category][2]


def ensure_sections(db: Session, workspace: Workspace) -> list[Section]:
    """Put every item that has no section into its category group's section; return all sections."""
    sections = list(
        db.scalars(
            select(Section)
            .where(Section.workspace_id == workspace.id)
            .order_by(Section.position, Section.created_at)
        ).all()
    )
    loose = db.scalars(
        select(Product)
        .where(Product.workspace_id == workspace.id, Product.section_id.is_(None))
        .order_by(Product.created_at, Product.idx)
    ).all()
    if not loose:
        return sections
    by_group = {s.category: s for s in sections if s.category}
    next_position = (
        db.scalar(select(func.max(Section.position)).where(Section.workspace_id == workspace.id))
        or 0
    ) + 1
    for product in loose:
        group = GROUP_OF.get(product.category, "other")
        section = by_group.get(group)
        if section is None:
            name_en, name_hi, _ = GROUPS[group]
            section = Section(
                workspace_id=workspace.id,
                name_en=name_en,
                name_hi=name_hi,
                position=next_position,
                category=group,
            )
            next_position += 1
            db.add(section)
            db.flush()
            by_group[group] = section
            sections.append(section)
        product.section_id = section.id
    db.flush()
    return sections
