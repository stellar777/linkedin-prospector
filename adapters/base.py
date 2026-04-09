"""Base storage adapter interface."""

from abc import ABC, abstractmethod


class StorageAdapter(ABC):
    @abstractmethod
    def save_tracking(self, records: list[dict]) -> None:
        pass

    @abstractmethod
    def save_leads(self, niche: str, sub_niche: str, leads: list[dict]) -> None:
        pass

    @abstractmethod
    def get_scraped(self) -> list[dict]:
        pass
