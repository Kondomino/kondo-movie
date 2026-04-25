"""
Smoke tests for the Cloudflare R2 storage adapter.

We deliberately avoid importing `storage_manager` here — that module bootstraps
a singleton at import time which would require env vars / config to actually
connect. These tests cover only the R2 adapter module + the CloudPath model.
"""

import pytest


def test_r2_module_imports_cleanly():
    """Module can be imported without env vars (no module-level boto3 calls)."""
    import cloudflare.r2_storage as mod

    assert hasattr(mod, "CloudflareR2StorageManager")
    assert callable(mod.CloudflareR2StorageManager)


def test_r2_setup_raises_without_env_vars(monkeypatch):
    """
    Constructing the adapter without R2 env vars must raise ValueError with
    a message naming the missing var names — guards against a silent fail-open
    where credentials are expected but absent.
    """
    monkeypatch.delenv("CLOUDFLARE_R2_KEY_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_R2_ACCESS_KEY", raising=False)
    monkeypatch.delenv("CLOUDFLARE_R2_ENDPOINT", raising=False)

    from cloudflare.r2_storage import CloudflareR2StorageManager

    # Reset singleton so __new__ runs setup() instead of returning a cached instance.
    CloudflareR2StorageManager._instance = None

    with pytest.raises(ValueError, match="Missing Cloudflare R2 credentials"):
        CloudflareR2StorageManager()


def test_cloudpath_full_path():
    from pathlib import Path
    from cloudflare.storage_model import CloudPath

    cp = CloudPath(bucket_id="kondo-properties", path=Path("foo/bar.jpg"))
    assert cp.full_path() == "s3://kondo-properties/foo/bar.jpg"


def test_cloudpath_public_url_strips_trailing_slash():
    from pathlib import Path
    from cloudflare.storage_model import CloudPath

    cp = CloudPath(bucket_id="b", path=Path("img/1.png"))
    assert cp.public_url("https://cdn.kondomino.com.br/") == "https://cdn.kondomino.com.br/img/1.png"


def test_cloudpath_origin_url_virtual_hosted():
    from pathlib import Path
    from cloudflare.storage_model import CloudPath

    cp = CloudPath(bucket_id="b", path=Path("img/1.png"))
    assert cp.origin_url("https://accountid.r2.cloudflarestorage.com") == \
        "https://b.accountid.r2.cloudflarestorage.com/img/1.png"
