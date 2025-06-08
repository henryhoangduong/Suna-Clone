import inspect
import json
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from utils.logger import logger


class SchemaType(Enum):
    """Enumeration of supported schema types for tool definitions."""

    OPENAPI = "openapi"
    XML = "xml"
    CUSTOM = "custom"


@dataclass
class XMLNodeMapping:
    param_name: str
    node_type: str = "element"
    path: str = "."
    required: bool = True


@dataclass
class XMLTagSchema:
    tag_name: str
    mappings: List[XMLNodeMapping] = field(default_factory=list)
    example: Optional[str] = None

    def add_mapping(
        self,
        param_name: str,
        node_type: str = "element",
        path: str = ".",
        required: bool = True,
    ) -> None:
        self.mappings.append(
            XMLNodeMapping(
                param_name=param_name, node_type=node_type, path=path, required=required
            )
        )
        logger.debug(
            f"Added XML mapping for parameter '{param_name}' with type '{node_type}' at path '{path}', required={required}"
        )


@dataclass
class ToolSchema:
    schema_type: SchemaType
    schema: Dict[str, Any]
    xml_schema: Optional[XMLTagSchema] = None


@dataclass
class ToolResult:
    success: bool
    output: str


class Tool(ABC):
    def __init__(self):
        self._schemas: Dict[str, List[ToolSchema]] = {}
        logger.debug(f"Initializing tool class: {self.__class__.__name__}")
        self._register_schemas()

    def _register_schemas(self):
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if hasattr(method, "tool_schemas"):
                self._schemas[name] = method.tool_schemas
                logger.debug(
                    f"Registered schemas for method '{name}' in {self.__class__.__name__}"
                )

    def get_schemas(self) -> Dict[str, List[ToolSchema]]:
        return self._schemas

    def success_response(self, data: Union[Dict[str, Any], str]) -> ToolResult:
        if isinstance(data, str):
            text = data
        else:
            text = json.dumps(data, indent=2)
        logger.debug(f"Created success response for {self.__class__.__name__}")
        return ToolResult(success=True, output=text)

    def fail_response(self, msg: str) -> ToolResult:
        logger.debug(f"Tool {self.__class__.__name__} returned failed result: {msg}")
        return ToolResult(success=False, output=msg)


def _add_schema(func, schema: ToolSchema):
    if not hasattr(func, "tool_schemas"):
        func.tool_schemas = []
    func.tool_schemas.append(schema)
    logger.debug(f"Added {schema.schema_type.value} schema to function {func.__name__}")
    return func


def openai_schema(schema: Dict[str, Any]):
    def decorator(func):
        logger.debug(f"Applying OpenAPI schema to function {func.__name__}")
        return _add_schema(
            func, ToolSchema(schema_type=SchemaType.OPENAPI, schema=schema)
        )

    return decorator


def xml_schema(
    tag_name: str, mappings: List[Dict[str, Any]] = None, example: str = None
):
    def decorator(func):
        logger.debug(
            f"Applying XML schema with tag '{tag_name}' to function {func.__name__}"
        )
        xml_schema = XMLTagSchema(tag_name=tag_name, example=example)

        # Add mappings
        if mappings:
            for mapping in mappings:
                xml_schema.add_mapping(
                    param_name=mapping["param_name"],
                    node_type=mapping.get("node_type", "element"),
                    path=mapping.get("path", "."),
                    required=mapping.get("required", True),
                )

        return _add_schema(
            func,
            ToolSchema(
                schema_type=SchemaType.XML,
                schema={},  # OpenAPI schema could be added here if needed
                xml_schema=xml_schema,
            ),
        )

    return decorator


def custom_schema(schema: Dict[str, Any]):
    """Decorator for custom schema tools."""

    def decorator(func):
        logger.debug(f"Applying custom schema to function {func.__name__}")
        return _add_schema(
            func, ToolSchema(schema_type=SchemaType.CUSTOM, schema=schema)
        )

    return decorator
