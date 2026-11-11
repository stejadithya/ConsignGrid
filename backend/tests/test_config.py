import pytest

from app.core.config import DEV_SECRET, Settings


@pytest.mark.parametrize("url", ["postgres://u:p@h/db?sslmode=require", "postgresql://u:p@h/db?sslmode=require"])
def test_provider_database_urls_use_psycopg(url):
    assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@h/db?sslmode=require"


def test_staging_and_production_require_strong_secret():
    for env in ("staging", "production"):
        with pytest.raises(ValueError):
            Settings(app_env=env, jwt_secret=DEV_SECRET)
        with pytest.raises(ValueError):
            Settings(app_env=env, jwt_secret="short")
        assert Settings(app_env=env, jwt_secret="x" * 40).app_env == env
