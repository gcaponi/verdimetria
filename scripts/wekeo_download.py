"""Download di un prodotto WEkEO via HDA API (token -> ordine -> download).

Uso: python scripts/wekeo_download.py <product_id> <location_url> <output_path>
Credenziali lette da .env (login/password). Solo requests, niente dipendenze extra:
gira identico in locale e sulla VPS.
"""

from __future__ import annotations

import os
import sys
import time

import requests
from dotenv import load_dotenv

BASE = "https://gateway.prod.wekeo2.eu/hda-broker"
DATASET_ID = "EO:EEA:DAT:CLC-PLUS"
TERMS_ID = "Copernicus_Land_Monitoring_Service_Data_Policy"
CHUNK = 1024 * 1024 * 8


def get_token() -> str:
    response = requests.post(
        f"{BASE}/gettoken",
        json={"username": os.environ["login"], "password": os.environ["password"]},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    product_id, location, output_path = sys.argv[1], sys.argv[2], sys.argv[3]

    load_dotenv(os.environ.get("ENV_FILE", ".env"))
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    requests.put(f"{BASE}/api/v1/termsaccepted/{TERMS_ID}", headers=headers, timeout=30)

    order = requests.post(
        f"{BASE}/api/v1/dataaccess/download",
        headers=headers,
        json={"dataset_id": DATASET_ID, "product_id": product_id, "location": location},
        timeout=60,
    )
    order.raise_for_status()
    download_id = order.json()["download_id"]
    print(f"ordine accettato: {download_id}", flush=True)

    with requests.get(
        f"{BASE}/api/v1/dataaccess/download/{download_id}",
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=(30, 600),
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        received = 0
        started = time.time()
        with open(output_path, "wb") as out:
            for chunk in response.iter_content(CHUNK):
                out.write(chunk)
                received += len(chunk)
                if total:
                    elapsed = max(time.time() - started, 1)
                    print(
                        f"\r{received / 1e9:.2f}/{total / 1e9:.2f} GB "
                        f"({received / elapsed / 1e6:.0f} MB/s)",
                        end="",
                        flush=True,
                    )
    print(f"\nsalvato: {output_path}")


if __name__ == "__main__":
    main()
