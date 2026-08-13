"""Current Lidl Czech Republic marketing-promotion adapter."""

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from core.promotions import DailyPromotion, PromotionError
from infrastructure.http import HttpClientError, TextHttpClient

_HOME_PAGE = "https://www.lidl.cz/"
_LABEL_CLASS = "n-navigation__marketing-message--label"
_ALLOWED_HOSTS = frozenset({"lidl.cz", "www.lidl.cz"})


class LidlMarketingPromotionSource:
    """Retrieve the current global marketing banner from Lidl Czech Republic."""

    def __init__(self, http_client: TextHttpClient) -> None:
        """Configure the injected text HTTP boundary."""
        if not callable(getattr(http_client, "get", None)):
            raise TypeError("http_client must expose a callable get method")
        self._http_client = http_client

    def current(self) -> DailyPromotion | None:
        """Return the first current Lidl marketing banner when published."""
        try:
            html = self._http_client.get(_HOME_PAGE)
        except HttpClientError as error:
            raise PromotionError("failed to retrieve Lidl promotion") from error
        if not isinstance(html, str):
            raise PromotionError("Lidl promotion response must be text")
        try:
            parsed = _parse_promotion(html)
            if parsed is None:
                return None
            text, href = parsed
            normalized_text = " ".join(text.split())
            if not normalized_text:
                raise ValueError("promotion text cannot be blank")
            return DailyPromotion(normalized_text, _normalize_url(href))
        except (ValueError, TypeError) as error:
            raise PromotionError("invalid Lidl promotion data") from error


class _MarketingMessageParser(HTMLParser):
    """Extract the first marketing label and its nearest anchor link."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.promotion: tuple[str, str | None] | None = None
        self.incomplete_label = False
        self._anchor_stack: list[str | None] = []
        self._collecting = False
        self._nested_depth = 0
        self._chunks: list[str] = []
        self._href: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        attributes = {name.casefold(): value for name, value in attrs}
        if normalized_tag == "a":
            self._anchor_stack.append(attributes.get("href"))
        if self._collecting:
            self._nested_depth += 1
            return
        classes = (attributes.get("class") or "").split()
        if (
            self.promotion is None
            and normalized_tag == "span"
            and _LABEL_CLASS in classes
        ):
            self._collecting = True
            self.incomplete_label = True
            self._chunks = []
            self._href = self._anchor_stack[-1] if self._anchor_stack else None

    def handle_data(self, data: str) -> None:
        if self._collecting:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if self._collecting:
            if self._nested_depth:
                self._nested_depth -= 1
            elif normalized_tag == "span":
                self.promotion = ("".join(self._chunks), self._href)
                self._collecting = False
                self.incomplete_label = False
        if normalized_tag == "a" and self._anchor_stack:
            self._anchor_stack.pop()


def _parse_promotion(html: str) -> tuple[str, str | None] | None:
    parser = _MarketingMessageParser()
    parser.feed(html)
    parser.close()
    if parser.incomplete_label:
        raise ValueError("marketing label is incomplete")
    return parser.promotion


def _normalize_url(href: str | None) -> str | None:
    if href is None:
        return None
    if not isinstance(href, str) or not href.strip():
        raise ValueError("marketing link must be non-blank")
    url = urljoin(_HOME_PAGE, href)
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("marketing link has an invalid port") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ValueError("marketing link must use the Lidl Czech Republic host")
    return url
