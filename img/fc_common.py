"""Fulfilment-centre (FC) variant of the parcel cell: one outbound check after packing, before sorter induction (doc 28 sec. 8, scope 1).
Generic FC-style label (order-number barcode + camp code); no company branding."""
OUTPUTS = {
    "OK": "ship it: label readable and matches the order, carton intact, measured weight within +-5% of the order's expected weight, packing fits the items",
    "RELABEL": "the shipping label is damaged, obscured or unreadable (barcode smudged/torn/missing, label unreadable) - reprint and relabel",
    "DAMAGED": "the carton is damaged or leaking (wet stain, torn hole, crushed corner, oil/liquid stain)",
    "SPEC_OUT": "measured weight differs from the order's expected weight by more than 5% (likely wrong item or count)",
    "PACK_UNFIT": "the order contains fragile items but the carton has no fragile / handle-with-care sticker",
    "MANUAL": "needs a person: the label belongs to a different order than this one, or the evidence conflicts",
}
EXC = set(OUTPUTS) - {"OK"}
POLICY = ("Check the parcel against its order before it is inducted to the sorter. Priority if several apply: MANUAL (label of another order) > "
          "DAMAGED > SPEC_OUT > RELABEL > PACK_UNFIT. A fragile sticker can be in English or Korean (e.g. FRAGILE, 취급주의, 깨짐주의) in any colour. "
          "Letting a faulty parcel ship costs about $35; an unnecessary human check costs about 55 KRW.")


def criteria():
    return OUTPUTS


def order_text(z):
    o = z["order"]
    items = "; ".join(f"{it['name']} x{it['qty']} ({it['unit_kg']} kg each{', fragile' if it['fragile'] else ''})" for it in o["items"])
    return (f"Order {o['order_no']} for camp {o['camp']}: {items}. Expected weight {o['expected_kg']} kg. "
            f"Fragile items in order: {'yes' if o['fragile'] else 'no'}. Measured weight on the scale: {z['weight']} kg.")
