from dishka import Provider
from dishka.integrations.litestar import LitestarProvider

from backend.shared.di.providers.app import AppProvider, SessionProvider
from backend.shared.di.providers.domain import DomainProvider


class ProviderRegistry:
    @staticmethod
    def build() -> list[Provider]:
        return [AppProvider(), LitestarProvider(), SessionProvider(), DomainProvider()]
