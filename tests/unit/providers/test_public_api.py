"""Public API tests for HTTP and Lidl provider Infrastructure packages."""

import inspect

import infrastructure.http as http_api
import infrastructure.providers.lidl as lidl_api
from core.provider import FetchResult
from infrastructure.http import HttpClientError, TextHttpClient, UrllibTextHttpClient
from infrastructure.providers.lidl import LidlParksideProvider


def test_http_public_api_is_explicit() -> None:
    assert http_api.__all__ == [
        "HttpClientError",
        "TextHttpClient",
        "UrllibTextHttpClient",
    ]
    assert http_api.HttpClientError is HttpClientError
    assert http_api.TextHttpClient is TextHttpClient
    assert http_api.UrllibTextHttpClient is UrllibTextHttpClient


def test_lidl_public_api_is_explicit() -> None:
    assert lidl_api.__all__ == ["LidlParksideProvider"]
    assert lidl_api.LidlParksideProvider is LidlParksideProvider


def test_public_objects_have_docstrings_and_annotations() -> None:
    assert inspect.getdoc(TextHttpClient)
    assert inspect.getdoc(TextHttpClient.get)
    assert inspect.getdoc(HttpClientError)
    assert inspect.getdoc(UrllibTextHttpClient)
    assert inspect.getdoc(UrllibTextHttpClient.__init__)
    assert inspect.getdoc(UrllibTextHttpClient.get)
    assert inspect.getdoc(LidlParksideProvider)
    assert inspect.getdoc(LidlParksideProvider.__init__)
    assert inspect.getdoc(LidlParksideProvider.fetch)
    assert inspect.signature(TextHttpClient.get).return_annotation is str
    assert inspect.signature(UrllibTextHttpClient.get).return_annotation is str
    assert inspect.signature(LidlParksideProvider.fetch).return_annotation is FetchResult
