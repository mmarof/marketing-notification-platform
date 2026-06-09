import pytest


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Known analytics authentication issue", strict=False)
class TestAnalyticsAPI:
    ...
