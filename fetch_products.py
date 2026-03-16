#!/usr/bin/env python3
"""
fetch_products.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Obtiene todos los productos de Tienda Nube y
genera products.json para el catálogo mayorista.

Variables de entorno necesarias:
  TIENDANUBE_STORE_ID     — ID numérico de tu tienda
  TIENDANUBE_ACCESS_TOKEN — Token de acceso de la API

Uso local:
  export TIENDANUBE_STORE_ID=5053574
  export TIENDANUBE_ACCESS_TOKEN=tu_token_aqui
  python fetch_products.py
"""

import os
import json
import time
import requests
from datetime import datetime, timezone

# ─── Config ────────────────────────────────────────────────────
STORE_ID     = os.environ.get("TIENDANUBE_STORE_ID", "5053574")
ACCESS_TOKEN = os.environ.get("TIENDANUBE_ACCESS_TOKEN", "")
BASE_URL     = f"https://api.tiendanube.com/v1/{STORE_ID}"
HEADERS      = {
    "Authentication": f"bearer {ACCESS_TOKEN}",
    "User-Agent":     "Fressia-Mayorista/1.0 (tomaschaufan@gmail.com)",
    "Content-Type":   "application/json",
}
OUTPUT_FILE  = "products.json"
PER_PAGE     = 200   # máximo permitido por Tienda Nube
# ───────────────────────────────────────────────────────────────


def get_all_products():
    """Pagina por la API hasta traer todos los productos publicados."""
    products = []
    page = 1
    while True:
        url = f"{BASE_URL}/products"
        params = {
            "per_page": PER_PAGE,
            "page":     page,
            "published": "true",
        }
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        print(f"  Página {page}: {len(batch)} productos (total parcial: {len(products)})")
        if len(batch) < PER_PAGE:
            break
        page += 1
        time.sleep(0.5)   # respetar rate limit de Tienda Nube
    return products


def parse_color(name: str) -> str:
    """Mapea nombre de color a hex aproximado para los dots."""
    MAP = {
        "negro": "#1a1a1a", "blanco": "#ffffff", "beige": "#d4b896",
        "crema": "#f5f0e8", "marfil": "#fffde7", "gris": "#9e9e9e",
        "gris oscuro": "#616161", "gris claro": "#e0e0e0",
        "bordo": "#7b1a2c", "bordó": "#7b1a2c", "burgundy": "#7b1a2c",
        "rojo": "#d32f2f", "rosa": "#e91e8c", "rosa palo": "#f8bbd0",
        "nude": "#d4a77a", "camel": "#c19a6b", "marrón": "#795548",
        "chocolate": "#4e342e", "azul": "#1565c0", "marino": "#0d1b3e",
        "verde": "#2e7d32", "verde agua": "#80cbc4", "lila": "#ce93d8",
        "mostaza": "#f9a825", "naranja": "#e64a19", "animal print": "#a0522d",
    }
    key = name.lower().strip()
    for k, v in MAP.items():
        if k in key:
            return v
    return "#cccccc"


def transform_product(raw: dict) -> dict:
    """Convierte un producto de la API de TN al formato del catálogo."""
    # Nombre
    name = raw.get("name", {})
    name_es = name.get("es") or name.get("pt") or (list(name.values())[0] if name else "Sin nombre")

    # Descripción
    desc = raw.get("description", {})
    desc_es = desc.get("es") or desc.get("pt") or ""
    # Quitar HTML básico
    import re
    desc_clean = re.sub(r"<[^>]+>", " ", desc_es).strip()
    desc_clean = re.sub(r"\s+", " ", desc_clean)[:400]

    # Precio (usamos el de la primera variante disponible)
    price = 0.0
    variants = raw.get("variants", [])
    for v in variants:
        p = v.get("price") or v.get("promotional_price")
        if p:
            try:
                price = float(p)
                break
            except ValueError:
                pass

    # Imagen principal
    images = raw.get("images", [])
    image_url = ""
    if images:
        src = images[0].get("src", "")
        # Tienda Nube devuelve URLs con //{width}x{height}
        image_url = "https:" + src if src.startswith("//") else src
        # Pedir versión mediana
        image_url = image_url.replace("{width}", "600").replace("{height}", "800")

    # SKU / número de artículo
    sku = raw.get("variants", [{}])[0].get("sku") or str(raw.get("id", ""))

    # Talles y colores desde atributos de variantes
    sizes = set()
    colors_raw = set()
    for v in variants:
        if not v.get("stock_management") or v.get("stock", 0) != 0 or not v.get("stock_management"):
            # incluir si no hay gestión de stock o si tiene stock
            pass
        for attr in v.get("values", []):
            val = attr.get("es") or attr.get("pt") or (list(attr.values())[0] if attr else "")
            # heurística: si parece talle (XS, S, M, L, XL, número)
            if val.upper() in ("XS", "S", "M", "L", "XL", "XXL", "XXXL") or val.isdigit() or \
               (len(val) <= 4 and val.replace(".", "").isdigit()):
                sizes.add(val.upper())
            else:
                colors_raw.add(val)

    colors = [{"name": c, "hex": parse_color(c)} for c in sorted(colors_raw) if c]

    # Categorías
    categories = []
    for cat in raw.get("categories", []):
        n = cat.get("name", {})
        c = n.get("es") or n.get("pt") or ""
        if c:
            categories.append(c)

    return {
        "id":          str(raw.get("id", "")),
        "sku":         sku,
        "name":        name_es.upper(),
        "description": desc_clean,
        "price":       price,
        "image":       image_url,
        "sizes":       sorted(sizes),
        "colors":      colors,
        "categories":  categories,
        "url":         raw.get("canonical_url", ""),
    }


def main():
    if not ACCESS_TOKEN:
        print("⚠️  TIENDANUBE_ACCESS_TOKEN no definido.")
        print("   Generá un token en tu panel de Tienda Nube y configurá la variable de entorno.")
        print("   Generando products.json de DEMO para previsualizar la página...")
        generate_demo_json()
        return

    print(f"🔄  Conectando con Tienda Nube (store {STORE_ID})...")
    raw_products = get_all_products()
    print(f"✅  {len(raw_products)} productos obtenidos.")

    products = [transform_product(p) for p in raw_products]
    # Filtrar los sin precio
    products = [p for p in products if p["price"] > 0]

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "store_id":   STORE_ID,
        "count":      len(products),
        "products":   products,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"💾  {OUTPUT_FILE} guardado con {len(products)} productos.")


def generate_demo_json():
    """Genera un JSON de demo con productos de ejemplo."""
    demo = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "store_id":   STORE_ID,
        "count":      4,
        "products": [
            {
                "id": "1", "sku": "REM-EVA-001",
                "name": "REMERA EVA",
                "description": "Remera de algodón premium con manga corta. Corte recto y moderno.",
                "price": 6000,
                "image": "https://d1a9qnv764bsoo.cloudfront.net/stores/005/053/574/products/img-placeholder-fressia.jpg",
                "sizes": ["S", "M", "L", "XL"],
                "colors": [{"name": "Negro", "hex": "#1a1a1a"}, {"name": "Blanco", "hex": "#f5f5f5"}, {"name": "Bordo", "hex": "#7b1a2c"}],
                "categories": ["Remeras y Musculosas"],
            },
            {
                "id": "2", "sku": "BUZ-AIRY-001",
                "name": "BUZO AIRY",
                "description": "Buzo oversize con capucha desmontable. Tela francesa premium.",
                "price": 20000,
                "image": "https://d1a9qnv764bsoo.cloudfront.net/stores/005/053/574/products/img-placeholder-fressia.jpg",
                "sizes": ["S", "M", "L"],
                "colors": [{"name": "Gris", "hex": "#9e9e9e"}, {"name": "Negro", "hex": "#1a1a1a"}],
                "categories": ["Buzos y Camperas"],
            },
            {
                "id": "3", "sku": "REM-ZOE-001",
                "name": "REMERA ZOE",
                "description": "Remera cropped con detalles en las mangas.",
                "price": 8000,
                "image": "https://d1a9qnv764bsoo.cloudfront.net/stores/005/053/574/products/img-placeholder-fressia.jpg",
                "sizes": ["XS", "S", "M", "L"],
                "colors": [{"name": "Beige", "hex": "#d4b896"}, {"name": "Rosa palo", "hex": "#f8bbd0"}],
                "categories": ["Remeras y Musculosas"],
            },
            {
                "id": "4", "sku": "PAN-WIDE-001",
                "name": "PANTALON WIDE LEG",
                "description": "Pantalón de corte ancho con cintura elástica. Tela fluída.",
                "price": 15000,
                "image": "https://d1a9qnv764bsoo.cloudfront.net/stores/005/053/574/products/img-placeholder-fressia.jpg",
                "sizes": ["S", "M", "L", "XL"],
                "colors": [{"name": "Negro", "hex": "#1a1a1a"}, {"name": "Camel", "hex": "#c19a6b"}],
                "categories": ["Pantalones"],
            },
        ]
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(demo, f, ensure_ascii=False, indent=2)
    print(f"💾  {OUTPUT_FILE} de DEMO generado.")


if __name__ == "__main__":
    main()
