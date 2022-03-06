from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar, Union

from pydantic import BaseModel

if TYPE_CHECKING:
    from pydantic.typing import AbstractSetIntStr, MappingIntStrAny, DictStrAny

from kapla.core.io import dumps_toml, dumps_yaml

ModelT = TypeVar("ModelT", bound=BaseModel)


class AliasedModel(BaseModel):
    def dict(
        self,
        *,
        include: Union[AbstractSetIntStr, MappingIntStrAny, None] = None,
        exclude: Union[AbstractSetIntStr, MappingIntStrAny, None] = None,
        by_alias: bool = True,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
    ) -> DictStrAny:
        return super().dict(
            include=include,  # type: ignore[arg-type]
            exclude=exclude,  # type: ignore[arg-type]
            by_alias=by_alias,
            skip_defaults=skip_defaults,  # type: ignore[arg-type]
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

    def json(
        self,
        *,
        include: Union[AbstractSetIntStr, MappingIntStrAny, None] = None,
        exclude: Union[AbstractSetIntStr, MappingIntStrAny, None] = None,
        by_alias: bool = True,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
        encoder: Optional[Callable[[Any], Any]] = None,
        models_as_dict: bool = True,
        **dumps_kwargs: Any,
    ) -> str:
        return super().json(
            include=include,  # type: ignore[arg-type]
            exclude=exclude,  # type: ignore[arg-type]
            by_alias=by_alias,
            skip_defaults=skip_defaults,  # type: ignore[arg-type]
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
            encoder=encoder,
            models_as_dict=models_as_dict,
            **dumps_kwargs,
        )

    def toml(
        self,
        *,
        include: Union[AbstractSetIntStr, MappingIntStrAny, None] = None,
        exclude: Union[AbstractSetIntStr, MappingIntStrAny, None] = None,
        by_alias: bool = True,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
    ) -> str:
        """Generate a TOML representation of the model

        by_alias, skip_defaults, include and exclude arguments as per dict().
        """
        doc = self.dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )
        return dumps_toml(doc)

    def yaml(
        self,
        *,
        include: Union[AbstractSetIntStr, MappingIntStrAny, None] = None,
        exclude: Union[AbstractSetIntStr, MappingIntStrAny, None] = None,
        by_alias: bool = True,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
    ) -> str:
        """Generate a YAML representation of the model

        by_alias, skip_defaults, include and exclude arguments as per dict().
        """
        doc = self.dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )
        return dumps_yaml(doc)

    class Config:
        allow_population_by_field_name = True
        extra = "forbid"
