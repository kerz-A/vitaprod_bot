"""
Script to check product data in Qdrant.
Run: python -m scripts.check_qdrant
"""

import sys
sys.path.insert(0, '.')

from qdrant_client import QdrantClient

def main():
    client = QdrantClient(host="localhost", port=6333)
    collection_name = "vitaprod_products"
    
    # Get all products
    result = client.scroll(
        collection_name=collection_name,
        limit=200,
        with_payload=True,
    )
    
    points = result[0]
    
    print(f"Total products: {len(points)}\n")
    
    # Find chestnut
    print("=" * 50)
    print("SEARCHING FOR 'каштан':")
    print("=" * 50)
    
    for point in points:
        payload = point.payload
        name = payload.get("name", "").lower()
        if "каштан" in name:
            print(f"Name: {payload.get('name')}")
            print(f"Category: {payload.get('category')}")
            print(f"Form: {payload.get('product_form')}")
            print(f"Price: {payload.get('price')}")
            print(f"Available: {payload.get('is_available')}")
            print("-" * 30)
    
    # Show all categories
    print("\n" + "=" * 50)
    print("ALL CATEGORIES IN DATABASE:")
    print("=" * 50)
    
    categories = {}
    for point in points:
        payload = point.payload
        cat = payload.get("category", "Unknown")
        form = payload.get("product_form", "Unknown")
        key = f"{cat} ({form})"
        if key not in categories:
            categories[key] = []
        categories[key].append(payload.get("name"))
    
    for cat, products in sorted(categories.items()):
        print(f"\n{cat}: {len(products)} products")
        for p in sorted(products)[:5]:
            print(f"  - {p}")
        if len(products) > 5:
            print(f"  ... and {len(products) - 5} more")


if __name__ == "__main__":
    main()