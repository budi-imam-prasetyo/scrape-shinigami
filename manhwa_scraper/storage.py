"""Penyimpanan hasil scraping: schema, validasi, dan penulisan atomic.

Version: 0.2.0
"""

import json
import logging
import os
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from .normalize import section_id

LOGGER = logging.getLogger(__name__)

ITEM_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "judul": {"type": "string", "minLength": 1},
        "url_img": {"type": "string", "format": "uri"},
        "sinopsis": {"type": "string"},
        "detail_url": {"type": "string", "format": "uri"},
        "section": {"type": "string", "minLength": 1},
        "section_title": {"type": "string", "minLength": 1},
        "rank": {"type": "integer", "minimum": 1},
        "sub_section": {"type": "string", "minLength": 1},
        "kategori": {"type": "string", "minLength": 1},
    },
    "required": ["judul", "url_img", "sinopsis", "detail_url", "section"],
    "additionalProperties": False,
}

DOCUMENT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schema_version", "generated_at", "source", "sections"],
    "properties": {
        "schema_version": {"const": "0.2.0"},
        "generated_at": {"type": "string", "format": "date-time"},
        "source": {"type": "string", "format": "uri"},
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "title", "items"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
                    "title": {"type": "string", "minLength": 1},
                    "items": {"type": "array", "items": {"$ref": "#/$defs/item"}},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
    "$defs": {"item": ITEM_SCHEMA},
}


def validate_document(document):
    validator = Draft202012Validator(
        DOCUMENT_SCHEMA,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(
            f"{list(error.path)}: {error.message}" for error in errors[:5]
        )
        raise ValueError(f"Dokumen tidak valid ({len(errors)} error): {details}")
    return document


def save_atomic(document, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, output_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def build_document(sections, generated_at, source):
    document = {
        "schema_version": "0.2.0",
        "generated_at": generated_at,
        "source": source,
        "sections": [
            {
                "id": section_id(section["title"]),
                "title": section["title"],
                "items": section["items"],
            }
            for section in sections
        ],
    }
    return validate_document(document)
