import sys
import os
sys.path.insert(0, os.path.abspath("."))

from adapters.nusmods_adapter import NusmodsAdapter

def test_adapter():
    adapter = NusmodsAdapter()
    kg_data = adapter.kg_data
    print(f"Loaded KG size: {len(kg_data)} modules")
    
    test_data = adapter.load_data()
    print(f"Loaded test dataset size: {len(test_data)} records")
    
    # Check entity linking
    linked_cs1010 = adapter.link_entity("CS1010")
    print(f"Linked entity 'CS1010': {linked_cs1010}")
    
    # Check relation mapping
    rel_credit = adapter.map_relation("has credit value")
    rel_prereq = adapter.map_relation("requires prerequisite")
    rel_dept = adapter.map_relation("offered by department")
    print(f"Mapped relation 'has credit value': {rel_credit}")
    print(f"Mapped relation 'requires prerequisite': {rel_prereq}")
    print(f"Mapped relation 'offered by department': {rel_dept}")

if __name__ == "__main__":
    test_adapter()
