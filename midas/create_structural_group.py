from midas.midas_api import MidasAPI


# Function to create a structural group for the given element list
def create_structural_group(element_list, Structural_group_name):
    """Create a new structural group in MIDAS Civil NX with the specified elements.
    Will not overwrite existing groups with the same name.
    """

    if not element_list:
        print(" Element list is empty. Cannot create structural group.")
        return

    if not Structural_group_name.strip():
        print(" Structural group name is required.")
        return

    # Fetch existing group data
    existing_groups = MidasAPI("GET", "/db/GRUP")
    if not existing_groups:
        print(" Failed to retrieve existing group data.")
        return

    # Check for name conflict
    for group in existing_groups.get("GRUP", {}).values():
        if group.get("NAME") == Structural_group_name:
            print(f" Structural group name '{Structural_group_name}' already exists. Cannot create duplicate.")
            return

    # Determine next available key
    existing_keys = existing_groups.get("GRUP", {})
    next_key = str(max(map(int, existing_keys.keys()), default=0) + 1)

    # Define the structural group
    structural_group = {
        "Assign": {
            next_key: {
                "NAME": Structural_group_name,
                "E_LIST": element_list
            }
        }
    }

    # Send to MIDAS Civil NX
    response = MidasAPI("PUT", "/db/GRUP", structural_group)
    if response:
        print(f"✅ Structural group '{Structural_group_name}' created with elements: {element_list}")
    else:
        print(" Failed to create structural group.")