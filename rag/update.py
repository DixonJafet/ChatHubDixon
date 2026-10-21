import argparse
import sys

from dotenv import load_dotenv

from rag.azure_search import load_existing_embeddings, sync_repository
from rag.embed import embed_records
from rag.ingest import ingest_repository

load_dotenv()


def parse_repository(value):
    parts = value.split("/")
    if len(parts) != 2 or not all(parts):
        raise argparse.ArgumentTypeError(
            f"Repositorio inválido: {value}. Usa owner/repo."
        )
    return parts[0], parts[1]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Agrega o actualiza repositorios en el índice de Azure AI Search."
        )
    )
    parser.add_argument(
        "repositories",
        nargs="*",
        metavar="OWNER/REPO",
        help="Repositorio(s) accesible(s) desde GitHub.",
    )
    parser.add_argument(
        "--from-embeddings",
        action="store_true",
        help=(
            "Indexa data/embeddings.jsonl sin volver a generar los vectores."
        ),
    )
    args = parser.parse_args()

    if args.from_embeddings == bool(args.repositories):
        parser.error(
            "Indica repositorios OWNER/REPO o usa --from-embeddings."
        )

    if args.from_embeddings:
        repositories = load_existing_embeddings(
            "data/embeddings.jsonl"
        )
    else:
        repositories = {}
        for owner, repo in (
            parse_repository(value)
            for value in args.repositories
        ):
            records = ingest_repository(owner, repo)
            if not records:
                raise ValueError(
                    f"{owner}/{repo} no produjo fragmentos; "
                    "no se modificó el índice."
                )
            repositories[records[0]["repository"]] = embed_records(records)

    for records in repositories.values():
        sync_repository(records)

    print(
        f"Sincronización completada para "
        f"{len(repositories)} repositorio(s)."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Error actualizando Azure AI Search: {error}", file=sys.stderr)
        raise SystemExit(1) from error
