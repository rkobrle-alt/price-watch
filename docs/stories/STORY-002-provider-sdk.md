# STORY-002 — Provider SDK

## Goal

Introduce the Provider SDK that allows external providers to integrate with the Price Watch platform without modifying the Core domain.

---

## Requirements

Create the following package:

core/provider/

The package must not depend on:

- Home Assistant
- aiohttp
- SQLAlchemy
- requests
- BeautifulSoup

Only Python standard library and Core packages may be used.

---

## Public API

Create:

Provider
ProviderMetadata
FetchResult
ProviderError
ProviderRegistry

Export everything from

core.provider

---

## Provider

The Provider interface represents a product source.

Every provider must expose:

- id
- display_name
- version

and implement:

fetch()

which returns

FetchResult

The interface must not expose transport-specific details.

---

## ProviderMetadata

Immutable dataclass.

Contains:

provider id

display name

version

country

homepage

---

## FetchResult

Immutable dataclass.

Contains:

products

started_at

finished_at

duration

errors

Products are instances of Product.

---

## ProviderError

Base exception for provider failures.

No HTTP-specific subclasses yet.

---

## ProviderRegistry

Responsible for:

register()

unregister()

get()

list()

Duplicate registration must raise ProviderError.

---

## Architecture Rules

Provider SDK belongs to Core.

Concrete providers belong outside Core.

Core must never import any concrete provider.

---

## Tests

Unit tests required.

Cover:

registration

duplicate registration

fetch contract

metadata

public exports

immutability

100% coverage required.