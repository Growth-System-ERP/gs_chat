import re
from typing import List, Dict
from .schema import SchemaLayer

class EntityExtractor:
    def __init__(self):
        self.schema_layer = SchemaLayer()

    def extract_entities(self, query: str) -> Dict[str, List[str]]:
        tokens = re.findall(r'\w+', query.lower())
        matched_doctypes = set()
        matched_terms = []

        for token in tokens:
            if token in self.schema_layer.TERM_TO_DOCTYPE_MAP:
                matched_terms.append(token)
                matched_doctypes.add(self.schema_layer.TERM_TO_DOCTYPE_MAP[token])

        return {
            "terms": matched_terms,
            "doctypes": list(matched_doctypes)
        }

# Test it
if __name__ == "__main__":
    ee = EntityExtractor()
    result = ee.extract_entities("Show me top selling items from last month with customer details")
    print(result)
