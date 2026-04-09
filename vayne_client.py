#!/usr/bin/env python3
"""
Vayne API client — check URLs, create scrape orders, poll status, download CSVs.

Standalone module. No external dependencies (stdlib only).

Usage:
    from vayne_client import VayneClient

    client = VayneClient(token="your-vayne-api-token")
    count = client.check_url(sales_nav_url)
    order = client.create_order(sales_nav_url, name="HR Tech")
    order = client.poll_until_done(order["id"])
    csv_text = client.download_csv(order["id"])
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

BASE_URL = "https://www.vayne.io"


class VayneClient:
    def __init__(self, token: str = None):
        self.token = token or os.environ.get("VAYNE_API_TOKEN")
        if not self.token:
            raise ValueError("VAYNE_API_TOKEN required — pass token= or set env var")

    def _request(self, method: str, path: str, data: dict = None, params: dict = None) -> tuple[int, dict]:
        url = f"{BASE_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                result = json.loads(e.read().decode())
            except Exception:
                result = {"error": str(e)}
            return e.code, result

    def credits(self) -> dict:
        status, data = self._request("GET", "/api/credits")
        return data

    def check_url(self, url: str) -> int:
        status, data = self._request("POST", "/api/url_checks", {"url": url})
        if status == 200 and "total" in data:
            return data["total"]
        print(f"  URL check error ({status}): {data}")
        return -1

    def create_order(self, url: str, name: str = None, limit: int = None,
                     export_format: str = "simple") -> dict:
        payload = {"url": url, "export_format": export_format}
        if name:
            payload["name"] = name
        if limit:
            payload["limit"] = limit
        status, data = self._request("POST", "/api/orders", payload)
        if status in (200, 201):
            return data.get("order", data)
        raise RuntimeError(f"Create order failed ({status}): {data}")

    def order_status(self, order_id: int) -> dict:
        status, data = self._request("GET", f"/api/orders/{order_id}")
        return data.get("order", data)

    def poll_until_done(self, order_id: int, interval: int = 10, timeout: int = 600) -> dict:
        start = time.time()
        while time.time() - start < timeout:
            order = self.order_status(order_id)
            s = order.get("scraping_status", "unknown")
            total = order.get("total", "?")
            print(f"  Order {order_id}: {s} ({total} leads)")
            if s == "finished":
                return order
            if s == "failed":
                raise RuntimeError(f"Order {order_id} failed: {order}")
            time.sleep(interval)
        raise TimeoutError(f"Order {order_id} timed out after {timeout}s")

    def download_csv(self, order_id: int, export_format: str = "simple") -> str:
        order = self.order_status(order_id)
        exports = order.get("exports", {})
        export_data = exports.get(export_format, {})
        file_url = export_data.get("file_url")
        if not file_url:
            self._request("POST", f"/api/orders/{order_id}/export",
                         {"export_format": export_format})
            for _ in range(30):
                time.sleep(5)
                order = self.order_status(order_id)
                exports = order.get("exports", {})
                export_data = exports.get(export_format, {})
                file_url = export_data.get("file_url")
                if file_url:
                    break
        if not file_url:
            raise RuntimeError(f"No export URL available for order {order_id}")
        req = urllib.request.Request(file_url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read().decode("utf-8-sig")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 vayne_client.py credits")
        print("  python3 vayne_client.py check '<sales_nav_url>'")
        print("  python3 vayne_client.py order <order_id>")
        sys.exit(1)
    client = VayneClient()
    cmd = sys.argv[1]
    if cmd == "credits":
        print(json.dumps(client.credits(), indent=2))
    elif cmd == "check":
        count = client.check_url(sys.argv[2])
        print(f"Result count: {count}")
    elif cmd == "order":
        print(json.dumps(client.order_status(int(sys.argv[2])), indent=2))
