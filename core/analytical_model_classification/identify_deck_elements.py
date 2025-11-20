# core/analytical_model_classification/identify_deck_elements.py

def identify_deck_elements(filtered_elements, superstructure_sections):
    """Identify deck elements by matching SECT property with superstructure section IDs."""

    # Normalise all section IDs to strings so comparison is consistent
    super_ids = {str(sid) for sid in superstructure_sections}

    deck_elements = {
        eid: elem
        for eid, elem in filtered_elements.items()
        if str(elem.get("SECT")) in super_ids
    }

    # --- DEBUG: print summary + one sample if available ---
    print("\n[identify_deck_elements]")
    print(f"  Filtered elements count : {len(filtered_elements)}")
    print(f"  Supersection IDs count  : {len(super_ids)}")
    print(f"  Deck elements count     : {len(deck_elements)}")

    if super_ids:
        print("  First few super IDs     :", list(super_ids)[:10])

    if deck_elements:
        sample_eid = next(iter(deck_elements))
        sample_elem = deck_elements[sample_eid]
        print(f"  Sample deck element     : EID={sample_eid}, SECT={sample_elem.get('SECT')}")
    else:
        # Helpful when things are empty – show what one *non*-deck element looks like
        if filtered_elements:
            feid = next(iter(filtered_elements))
            felem = filtered_elements[feid]
            print("  Sample filtered element :",
                  f"EID={feid}, SECT={felem.get('SECT')}, TYPE={felem.get('TYPE')}")
    # ------------------------------------------------------

    return deck_elements
