# main.py
import certifi
import os
import requests

def main():
    access_token = os.environ.get("SHOPIFY_ACCESS_TOKEN")
    shop_domain = os.environ.get("SHOPIFY_STORE_DOMAIN", "").strip().replace("https://", "").replace("http://", "")

    if not access_token or not shop_domain:
        print("❌ Missing SHOPIFY_ACCESS_TOKEN or SHOPIFY_STORE_DOMAIN")
        return

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    url = f"https://{shop_domain}/admin/api/2024-01/products.json?limit=50"

    try:
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ API request failed: {e}")
        return

    products = response.json().get("products", [])

    for product in products:
        product_id = product.get("id")
        title = product.get("title", "<no title>")
        is_on_sale = False

        for variant in product.get("variants", []):
            price = float(variant.get("price", 0))
            compare_at = float(variant.get("compare_at_price") or 0)
            if compare_at > price:
                is_on_sale = True
                break

        if is_on_sale:
            print(f"✅ Product {product_id} - '{title}' is ON SALE")
        else:
            print(f"❌ Product {product_id} - '{title}' is not on sale")

if __name__ == "__main__":
    main()
