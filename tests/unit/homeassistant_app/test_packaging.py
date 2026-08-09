"""Static contract tests for Home Assistant App distribution files."""

from pathlib import Path


ROOT = Path(__file__).parents[3]
APP = ROOT / "homeassistant" / "price_watch"


def test_app_manifest_has_exact_runtime_identity_and_defaults() -> None:
    manifest = (APP / "config.yaml").read_text(encoding="utf-8")

    for required in (
        'version: "0.21.0"',
        "slug: price_watch",
        "  - aarch64",
        "  - amd64",
        "startup: application",
        "boot: auto",
        "homeassistant_api: true",
        "catalog_enabled: true",
        "catalog_batch_size: 25",
        "catalog_discovery_interval_cycles: 288",
        "product_urls: []",
        "notify_entity: notify.gmail_parkside_kobrle_fomei_com",
        "interval_seconds: 300",
        "daily_digest_enabled: true",
        'daily_digest_time: "08:00"',
        "individual_notifications_enabled: false",
        "image: ghcr.io/rkobrle-alt/price-watch",
    ):
        assert required in manifest
    for forbidden in (
        "hassio_api:",
        "docker_api:",
        "host_network:",
        "privileged:",
        "full_access:",
        "ingress:",
        "ports:",
        "map:",
        "SUPERVISOR_TOKEN",
        "password",
    ):
        assert forbidden not in manifest


def test_repository_container_and_operator_documents_are_complete() -> None:
    repository = (ROOT / "repository.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "https://github.com/rkobrle-alt/price-watch" in repository
    assert dockerfile.startswith("FROM python:3.13-")
    assert 'io.hass.type="app"' in dockerfile
    assert 'io.hass.arch="aarch64|amd64"' in dockerfile
    assert 'CMD ["python", "-m", "applications.homeassistant"]' in dockerfile
    assert 'tzdata==2026.3' in dockerfile
    assert "SUPERVISOR_TOKEN" not in dockerfile
    assert "tests" in dockerignore
    operator_docs = (APP / "DOCS.md").read_text(encoding="utf-8")
    assert "sensor.price_watch_status" in operator_docs
    assert "sensor.price_watch_product_<product UUID hex>" in operator_docs
    assert "sensor.price_watch_catalog" in operator_docs
    assert "sensor.price_watch_discounted_products" in operator_docs
    assert "sensor.price_watch_catalog_errors" in operator_docs
    assert "sensor.price_watch_last_checked" in operator_docs
    assert "last successful discovery and refresh attempt" in operator_docs
    assert "not entity-registry-backed" in operator_docs
    assert "/data/catalog.sqlite3" in operator_docs
    assert "catalog_batch_size" in operator_docs
    assert "daily_digest_enabled" in operator_docs
    assert "individual_notifications_enabled" in operator_docs
    for document in ("README.md", "DOCS.md", "CHANGELOG.md"):
        content = (APP / document).read_text(encoding="utf-8")
        assert content.strip()
        assert "TODO" not in content


def test_publish_workflow_is_tag_only_multiarchitecture_ghcr_delivery() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "publish-homeassistant.yml"
    ).read_text(encoding="utf-8")

    assert '      - "v*"' in workflow
    assert "platforms: linux/amd64,linux/arm64" in workflow
    assert "images: ghcr.io/rkobrle-alt/price-watch" in workflow
    assert "packages: write" in workflow
    assert "push: true" in workflow
    assert "pull_request:" not in workflow
    assert "workflow_dispatch:" not in workflow
    assert "SUPERVISOR_TOKEN" not in workflow
