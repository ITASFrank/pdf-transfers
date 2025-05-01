# main.py

import os
import requests

def tag_product(product_id, access_token, shop_domain):
    url = f"https://{shop_domain}/admin/api/2024-01/products/{product_id}.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    product = requests.get(url, headers=headers).json()["product"]

    existing_tags = product.get("tags", "").split(", ")
    if "On Sale" not in existing_tags:
        existing_tags.append("On Sale")

    payload = {
        "product": {
            "id": product_id,
            "tags": ", ".join(existing_tags)
        }
    }
    response = requests.put(url, headers=headers, json=payload)
    print(f"Tagged product {product_id}: {response.status_code}")

def main():
    access_token = os.environ.get("SHOPIFY_ACCESS_TOKEN")
    shop_domain = os.environ.get("SHOPIFY_STORE_DOMAIN")

    if not access_token or not shop_domain:
        print("Missing environment variables")
        return

    # TEMP: simple product fetch (not bulk yet)
    url = f"https://{shop_domain}/admin/api/2024-01/products.json?limit=50"
    headers = {
        "X-Shopify-Access-Token": access_token
    }
    response = requests.get(url, headers=headers)
    products = response.json().get("products", [])

    for product in products:
        should_tag = False
        for variant in product.get("variants", []):
            price = float(variant.get("price", 0))
            compare_at = float(variant.get("compare_at_price") or 0)
            if compare_at > price:
                should_tag = True
                break

        if should_tag:
            tag_product(product["id"], access_token, shop_domain)
        else:
            print(f"No sale for product {product['id']}")

if __name__ == "__main__":
    main()
