# core/analytical_model_classification/check_classification.py

from pprint import pprint

from midas import nodes

from core.analytical_model_classification import (classify_elements, classify_substructure_elements)


def run_classification_diagnostics(
    *,
    pier_radius: float = 10.0,
    length_unit: str = "FT",
    suffix_above: str = "_SubAbove",
    pier_base_name: str = "Pier",
):
    """
    Run classify_elements and compare the substructure classification with a
    simple height-based baseline. Prints diagnostics to the console.

    Call this from a Python console or a small main script.
    """

    print("=== Running classify_elements() ===")
    result = classify_elements(
        pier_radius=pier_radius,
        length_unit=length_unit,
        suffix_above=suffix_above,
        pier_base_name=pier_base_name,
    )

    deck_elements = result["deck_elements"]
    substructure_elements = result["substructure_elements"]
    pier_clusters = result["pier_clusters"]
    reference_height = result["deck_reference_height"]
    model_unit = result["model_unit"]

    node_data = nodes.get_all()

    print()
    print("=== Basic summary ===")
    print(f"Model distance unit       : {model_unit}")
    print(f"Deck reference height (Z) : {reference_height!r}")
    print(f"Num deck elements         : {len(deck_elements)}")
    print(f"Num substructure elements : {len(substructure_elements)}")
    print(f"Num pier clusters         : {len(pier_clusters)}")

    if reference_height is None:
        print()
        print(
            "WARNING: reference_height is None – deck level could not be found.\n"
            "Substructure classification cannot work reliably in this case."
        )
        return

    # ------------------------------------------------------------------
    # Build a simple baseline classification based purely on max node Z
    # ------------------------------------------------------------------
    print()
    print("=== Building baseline classification (simple max-Z) ===")

    baseline_above = {}
    baseline_below = {}
    elements_without_heights = set()
    nodes_missing = set()
    nodes_with_none_z = set()

    for eid, elem in substructure_elements.items():
        node_heights = []
        for nid in elem["NODE"]:
            nd = node_data.get(str(nid))
            if nd is None:
                nodes_missing.add(nid)
                continue
            z = nd.get("Z")
            if z is None:
                nodes_with_none_z.add(nid)
                continue
            node_heights.append(z)

        if not node_heights:
            elements_without_heights.add(eid)
            continue

        max_z = max(node_heights)
        if max_z >= reference_height:
            baseline_above[eid] = max_z
        else:
            baseline_below[eid] = max_z

    print(f"Baseline ABOVE count      : {len(baseline_above)}")
    print(f"Baseline BELOW count      : {len(baseline_below)}")
    print(f"Elements with no Z data   : {len(elements_without_heights)}")
    print(f"Nodes missing in node_data: {len(nodes_missing)}")
    print(f"Nodes with Z=None         : {len(nodes_with_none_z)}")

    # ------------------------------------------------------------------
    # Use the actual classify_substructure_elements implementation
    # ------------------------------------------------------------------
    print()
    print("=== Running classify_substructure_elements() ===")
    impl_above, impl_below = classify_substructure_elements(
        substructure_elements,
        reference_height,
        node_data=node_data,
    )

    impl_above_ids = set(impl_above.keys())
    impl_below_ids = set(impl_below.keys())

    print(f"Implementation ABOVE count: {len(impl_above_ids)}")
    print(f"Implementation BELOW count: {len(impl_below_ids)}")

    # ------------------------------------------------------------------
    # Compare implementation vs baseline
    # ------------------------------------------------------------------
    print()
    print("=== Comparing baseline vs implementation ===")

    diff_above_only = impl_above_ids - baseline_above.keys()
    diff_below_only = impl_below_ids - baseline_below.keys()

    baseline_above_only = baseline_above.keys() - impl_above_ids
    baseline_below_only = baseline_below.keys() - impl_below_ids

    if not diff_above_only and not diff_below_only and \
       not baseline_above_only and not baseline_below_only:
        print("OK: Implementation matches baseline classification.")
    else:
        print("MISMATCHES detected between baseline and implementation:")

        if diff_above_only:
            print("\nElements classified ABOVE by implementation only:")
            pprint(sorted(diff_above_only)[:50])

        if diff_below_only:
            print("\nElements classified BELOW by implementation only:")
            pprint(sorted(diff_below_only)[:50])

        if baseline_above_only:
            print("\nElements classified ABOVE by baseline only:")
            pprint(sorted(baseline_above_only)[:50])

        if baseline_below_only:
            print("\nElements classified BELOW by baseline only:")
            pprint(sorted(baseline_below_only)[:50])

    # ------------------------------------------------------------------
    # Extra: show a small sample of pier cluster info (if available)
    # ------------------------------------------------------------------
    print()
    print("=== Sample pier cluster info (first few) ===")
    for name, cluster in list(pier_clusters.items())[:5]:
        print(f"- Cluster {name!r}:")
        # Try some generic introspection so this works even if cluster is
        # a dict or a dataclass / object
        if isinstance(cluster, dict):
            for k, v in cluster.items():
                if isinstance(v, dict):
                    print(f"    {k}: {len(v)} elements")
                else:
                    print(f"    {k}: {v!r}")
        else:
            # Fallback: show attributes that don't start with "_"
            attrs = {
                k: getattr(cluster, k)
                for k in dir(cluster)
                if not k.startswith("_")
            }
            for k, v in attrs.items():
                if isinstance(v, dict):
                    print(f"    {k}: {len(v)} elements")
                else:
                    print(f"    {k}: {v!r}")

    # Report any data quality issues
    print()
    print("=== Data quality notes ===")
    if elements_without_heights:
        print(f"- {len(elements_without_heights)} substructure elements have no usable node Z values.")
    if nodes_missing:
        print(f"- {len(nodes_missing)} node IDs referenced by elements are missing in node_data.")
    if nodes_with_none_z:
        print(f"- {len(nodes_with_none_z)} nodes in node_data have Z=None.")
    if not (elements_without_heights or nodes_missing or nodes_with_none_z):
        print("- No obvious node/Z-data issues detected.")

    print()
    print("Diagnostics complete.")
