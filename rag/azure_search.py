import hashlib
import json
import os
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
)
from dotenv import load_dotenv

load_dotenv()

SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "").rstrip("/")
SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "").strip()
BATCH_SIZE = 500


def _require_search_settings():
    if not SEARCH_ENDPOINT or not SEARCH_INDEX:
        raise ValueError(
            "Configura AZURE_SEARCH_ENDPOINT y AZURE_SEARCH_INDEX."
        )


def _document_id(record):
    identity = "\0".join((
        record["repository"].casefold(),
        record["file_path"],
        str(record["chunk_index"]),
    ))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _index_definition(embedding_dimensions):
    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
        ),
        SearchableField(
            name="repository",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="branch",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="commit_sha",
            type=SearchFieldDataType.String,
        ),
        SimpleField(
            name="file_sha",
            type=SearchFieldDataType.String,
        ),
        SearchableField(
            name="file_path",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),
        SearchableField(
            name="text",
            type=SearchFieldDataType.String,
        ),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(
                SearchFieldDataType.Single
            ),
            searchable=True,
            vector_search_dimensions=embedding_dimensions,
            vector_search_profile_name="vector-profile",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw",
                parameters=HnswParameters(
                    metric=VectorSearchAlgorithmMetric.COSINE,
                ),
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw",
            )
        ],
    )
    return SearchIndex(
        name=SEARCH_INDEX,
        fields=fields,
        vector_search=vector_search,
    )


def ensure_index(embedding_dimensions):
    _require_search_settings()
    credential = DefaultAzureCredential()
    index_client = SearchIndexClient(
        endpoint=SEARCH_ENDPOINT,
        credential=credential,
    )
    try:
        try:
            index = index_client.get_index(SEARCH_INDEX)
        except ResourceNotFoundError:
            index = index_client.create_index(
                _index_definition(embedding_dimensions)
            )
        else:
            vector_field = next(
                (
                    field
                    for field in index.fields
                    if field.name == "embedding"
                ),
                None,
            )
            if (
                vector_field is None
                or vector_field.vector_search_dimensions
                != embedding_dimensions
            ):
                raise ValueError(
                    f"El índice {SEARCH_INDEX} no coincide con la "
                    f"dimensión de embedding {embedding_dimensions}."
                )
        return index
    finally:
        index_client.close()
        credential.close()


def _check_upload_results(results):
    failures = [result for result in results if not result.succeeded]
    if failures:
        details = "; ".join(
            f"{item.key}: {item.error_message}"
            for item in failures[:5]
        )
        raise RuntimeError(
            f"Azure AI Search rechazó {len(failures)} documentos: "
            f"{details}"
        )


def _documents_for_repository(client, repository):
    escaped_repository = repository.replace("'", "''")
    results = client.search(
        search_text="*",
        filter=f"repository eq '{escaped_repository}'",
        select=["id"],
    )
    return {result["id"] for result in results}


def sync_repository(records):
    if not records:
        raise ValueError(
            "El repositorio no produjo fragmentos; no se modificó el índice."
        )

    repository = records[0].get("repository")
    if not repository or any(
        record.get("repository") != repository
        for record in records
    ):
        raise ValueError(
            "sync_repository requiere fragmentos de un único repositorio."
        )

    dimensions = len(records[0].get("embedding", []))
    if not dimensions or any(
        len(record.get("embedding", [])) != dimensions
        for record in records
    ):
        raise ValueError(
            "Los documentos no tienen embeddings válidos y consistentes."
        )

    ensure_index(dimensions)
    credential = DefaultAzureCredential()
    client = SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX,
        credential=credential,
    )
    new_ids = set()

    try:
        documents = []
        for record in records:
            document = {
                **record,
                "id": _document_id(record),
            }
            new_ids.add(document["id"])
            documents.append(document)

        previous_ids = _documents_for_repository(client, repository)

        for start in range(0, len(documents), BATCH_SIZE):
            results = client.merge_or_upload_documents(
                documents=documents[start:start + BATCH_SIZE]
            )
            _check_upload_results(results)

        stale_ids = sorted(previous_ids - new_ids)
        for start in range(0, len(stale_ids), BATCH_SIZE):
            results = client.delete_documents(
                documents=[
                    {"id": document_id}
                    for document_id in stale_ids[start:start + BATCH_SIZE]
                ]
            )
            _check_upload_results(results)

        print(
            f"Azure AI Search actualizado: {repository} "
            f"({len(documents)} fragmentos; "
            f"{len(stale_ids)} fragmentos antiguos eliminados)."
        )
    finally:
        client.close()
        credential.close()


def load_existing_embeddings(path):
    embeddings_path = Path(path)
    if not embeddings_path.is_file():
        raise FileNotFoundError(
            f"No se encontró {embeddings_path}. "
            "Ejecuta la ingesta y generación de embeddings primero."
        )

    repositories = {}
    required_fields = (
        "repository",
        "file_path",
        "chunk_index",
        "text",
        "embedding",
    )
    with embeddings_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"JSON inválido en {embeddings_path}, "
                    f"línea {line_number}."
                ) from error

            if not all(field in record for field in required_fields):
                raise ValueError(
                    f"Faltan campos requeridos en {embeddings_path}, "
                    f"línea {line_number}."
                )
            repositories.setdefault(record["repository"], []).append(record)

    if not repositories:
        raise ValueError(f"No hay embeddings en {embeddings_path}.")
    return repositories
