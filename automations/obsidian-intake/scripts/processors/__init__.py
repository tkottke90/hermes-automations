from urllib.parse import urlparse


def classify_url(url: str, source_key_map: dict, default_source_key: str) -> str:
    """
    Determine content type from URL hostname using sourceKeyMap.
    Returns the matching key or default_source_key.
    """
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return default_source_key

    for content_type, domains in source_key_map.items():
        for domain in domains:
            if domain in hostname:
                return content_type

    return default_source_key
