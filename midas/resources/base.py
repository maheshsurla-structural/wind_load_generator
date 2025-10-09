# midas/resources/base.py
from typing import Dict, Any, Optional
from midas.midas_api import MidasAPI


class Resource:
    """
    Base class for all MIDAS /db/* resources.
    Provides consistent GET/PUT pattern and wrapping/unwrapping.
    """

    READ_KEY: str = ""
    PATH: str = ""
    GROUP_KEY: str = "1"

    @classmethod
    def _unwrap(cls, resp: Dict[str, Any]) -> Dict[str, Any]:
        return (resp or {}).get(cls.READ_KEY, {}).get(cls.GROUP_KEY, {}) or {}

    @classmethod
    def _wrap(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"Assign": {cls.GROUP_KEY: payload}}

    @classmethod
    def get_all(cls) -> Dict[str, Any]:
        return cls._unwrap(MidasAPI("GET", cls.PATH))

    @classmethod
    def set_all(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        return MidasAPI("PUT", cls.PATH, cls._wrap(payload))

    @classmethod
    def get(cls, key: str, default: Optional[Any] = None) -> Any:
        return cls.get_all().get(key, default)

    @classmethod
    def set(cls, key: str, value: Any) -> Dict[str, Any]:
        return cls.set_all({key: value})
