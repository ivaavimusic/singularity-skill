#!/usr/bin/env python3
"""
consume_product.py - Purchase and optionally download digital products from x402

Safer defaults:
- resolves only exact marketplace slug matches
- accepts only platform-hosted product URLs
- supports AWAL as well as local private-key signing
- downloads only from trusted storage hosts
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

from awal_bridge import awal_pay_url
from wallet_signing import is_awal_mode, load_payment_signer

API_BASE = "https://api.x402layer.cc"
STUDIO_BASE = "https://studio.x402layer.cc"
MARKETPLACE_URL = f"{API_BASE}/marketplace"
TRUSTED_PRODUCT_HOSTS = {
    "api.x402layer.cc",
    "studio.x402layer.cc",
}
TRUSTED_DOWNLOAD_SUFFIXES = (
    ".supabase.co",
    ".supabase.in",
    ".supabase.net",
)


def _print_usage() -> None:
    print("Usage: python consume_product.py <product-slug-or-url> [--download]")
    print("\nExamples:")
    print("  python consume_product.py pussio")
    print("  python consume_product.py https://studio.x402layer.cc/pay/pussio")
    print("  python consume_product.py pussio --download")


def _validate_product_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Product URL must use https")
    if parsed.netloc not in TRUSTED_PRODUCT_HOSTS:
        raise ValueError("Product URL must be hosted on x402layer.cc")
    if not parsed.path.startswith("/storage/product/"):
        raise ValueError("Product URL must use the /storage/product/ path")
    return url


def _is_trusted_download_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = parsed.netloc.lower()
    if host in TRUSTED_PRODUCT_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in TRUSTED_DOWNLOAD_SUFFIXES)


def resolve_product_url(product_input: str) -> str:
    if product_input.startswith("http"):
        parsed = urlparse(product_input)
        if parsed.netloc == "api.x402layer.cc":
            return _validate_product_url(product_input)
        if parsed.netloc == "studio.x402layer.cc" and parsed.path.startswith("/pay/"):
            slug = parsed.path.removeprefix("/pay/").strip("/")
            return resolve_slug_to_api_url(slug)
        raise ValueError("Unknown product URL format")

    return resolve_slug_to_api_url(product_input)


def resolve_slug_to_api_url(slug: str) -> str:
    response = requests.get(
        MARKETPLACE_URL,
        params={"type": "product", "search": slug},
        timeout=30,
        headers={"Accept": "application/json"},
    )
    if response.status_code != 200:
        raise ValueError(f"Failed to query marketplace: {response.status_code}")

    payload = response.json()
    items = payload.get("items") or payload.get("listings") or []
    exact_matches = [item for item in items if item.get("slug") == slug]
    if not exact_matches:
        raise ValueError(
            f"Product not found for exact slug '{slug}'. Use the exact marketplace slug."
        )
    if len(exact_matches) > 1:
        raise ValueError(
            f"Multiple products matched slug '{slug}'. Use the full product URL instead."
        )

    product_id = exact_matches[0].get("id")
    if not product_id:
        raise ValueError(f"Product ID not found for slug '{slug}'")

    return _validate_product_url(f"{API_BASE}/storage/product/{product_id}")


def _request_product(url: str, headers: Optional[Dict[str, str]] = None) -> requests.Response:
    merged_headers = {"Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    return requests.get(url, headers=merged_headers, timeout=45)


def _download_file(result: Dict[str, Any]) -> None:
    download_url = result.get("downloadUrl")
    if not download_url:
        print("No download URL returned")
        return
    if not _is_trusted_download_url(download_url):
        raise ValueError("Refusing to download from a non-trusted host")

    raw_filename = result.get("fileName", "downloaded_product")
    filename = os.path.basename(raw_filename)
    if not filename or filename in {".", ".."}:
        filename = "downloaded_product"

    print(f"\nDownloading file to: {filename}")
    file_response = requests.get(download_url, timeout=60)
    if file_response.status_code != 200:
        raise ValueError(f"Download failed: {file_response.status_code}")

    with open(filename, "wb") as handle:
        handle.write(file_response.content)
    print(f"Downloaded: {filename} ({len(file_response.content)} bytes)")


def _pay_with_private_key(api_url: str) -> Dict[str, Any]:
    signer = load_payment_signer()

    response = _request_product(api_url)
    if response.status_code == 200:
        return response.json()
    if response.status_code != 402:
        raise ValueError(f"Unexpected response: {response.status_code} - {response.text}")

    payment_info = response.json().get("payment", {})
    recipient = payment_info.get("recipient")
    price = payment_info.get("amount")
    currency = payment_info.get("currency", "USDC")
    network = payment_info.get("network", "base")

    print("Payment required:")
    print(f"  Recipient: {recipient}")
    print(f"  Amount: {price} {currency}")
    print(f"  Network: {network}")

    if network != "base":
        raise ValueError(f"This script only supports Base network. Product requires: {network}")
    if currency not in {"USDC", "USD"}:
        raise ValueError(f"This script only supports USDC. Product requires: {currency}")

    amount = int(float(price) * 1e6)
    payment_payload = signer.create_x402_payment_payload(pay_to=recipient, amount=amount)

    print("\nSubmitting payment and requesting download...")
    paid = _request_product(api_url, headers={"X-Payment": json.dumps(payment_payload)})
    if paid.status_code != 200:
        raise ValueError(f"Payment failed: {paid.status_code} - {paid.text}")

    return paid.json()


def consume_product(product_input: str, download_file: bool = False) -> Dict[str, Any]:
    print(f"Resolving product: {product_input}")
    api_url = resolve_product_url(product_input)
    print(f"API URL: {api_url}")

    if is_awal_mode():
        print("Using AWAL to authorize the product purchase")
        result = awal_pay_url(api_url, method="GET", headers={"Accept": "application/json"})
        if result.get("error"):
            raise ValueError(result["error"])
    else:
        result = _pay_with_private_key(api_url)

    print("\nProduct purchased successfully")
    print(f"Download URL: {result.get('downloadUrl', 'N/A')}")
    print(f"File Name: {result.get('fileName', 'N/A')}")

    if download_file:
        _download_file(result)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Purchase a product from x402 Singularity Layer")
    parser.add_argument("product", help="Exact product slug or trusted x402 product URL")
    parser.add_argument("--download", action="store_true", help="Download the returned file after purchase")
    args = parser.parse_args()

    try:
        result = consume_product(args.product, download_file=args.download)
        print("\nResult:")
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"\nError: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
