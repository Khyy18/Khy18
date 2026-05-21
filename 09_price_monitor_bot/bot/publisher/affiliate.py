"""Построение партнерских ссылок для маркетплейсов."""

from urllib.parse import urlencode, urlparse, urlunparse, parse_qs, urljoin


def build_affiliate_link(product_url: str, marketplace: str, affiliate_tag: str) -> str:
    """Построить партнерскую ссылку с UTM-параметрами.

    Args:
        product_url: исходная URL товара.
        marketplace: 'wildberries' или 'ozon'.
        affiliate_tag: тег партнерской программы.

    Returns:
        URL с добавленными партнерскими параметрами.
    """
    if marketplace.lower() in ("wildberries", "wb"):
        return _build_wb_link(product_url, affiliate_tag)
    elif marketplace.lower() == "ozon":
        return _build_ozon_link(product_url, affiliate_tag)
    else:
        return product_url


def _build_wb_link(product_url: str, affiliate_tag: str) -> str:
    """Партнерская ссылка для Wildberries."""
    parsed = urlparse(product_url)
    params = parse_qs(parsed.query)
    params["seller"] = [affiliate_tag]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _build_ozon_link(product_url: str, affiliate_tag: str) -> str:
    """Партнерская ссылка для Ozon с UTM-параметрами."""
    parsed = urlparse(product_url)
    params = parse_qs(parsed.query)
    params["utm_source"] = [affiliate_tag]
    params["utm_medium"] = ["cpc"]
    params["utm_campaign"] = [affiliate_tag]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))
