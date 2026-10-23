PRODUCT_URL = "https://silpo.ua/product/"


def product_url(slug: object) -> str | None:
    text = str(slug or "").strip()
    return f"{PRODUCT_URL}{text}" if text else None


__all__ = ["PRODUCT_URL", "product_url"]
