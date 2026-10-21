
import argparse
import base64
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.github.com"
MAX_FILE_BYTES = 500_000
CHUNK_LINES = 80
OVERLAP_LINES = 10

ALLOWED_EXTENSIONS = {
    ".py", ".md", ".txt", ".ts", ".tsx", ".js", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".sql", ".tf",
    ".bicep", ".html", ".css", ".scss",
}

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules",
    "__pycache__", "dist", "build", ".next", "coverage",
}

EXCLUDED_FILES = {
    ".env", ".env.local", ".env.production",
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "poetry.lock",
}


def make_session():
    session = requests.Session()
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    token = os.getenv("GITHUB_TOKEN")
    if token:
        session.headers["Authorization"] = f"Bearer {token}"

    return session


def get_json(session, url, params=None):
    response = session.get(url, params=params, timeout=30)

    if response.status_code == 401:
        raise RuntimeError(
            "GitHub rechazó la autenticación. Revisa GITHUB_TOKEN."
        )

    if response.status_code == 403:
        raise RuntimeError(
            "GitHub devolvió 403. Revisa los permisos del token "
            "y el límite de solicitudes."
        )

    if response.status_code == 404:
        raise RuntimeError(
            f"Recurso no encontrado o sin acceso: {url}"
        )

    response.raise_for_status()
    return response.json()


def should_skip(path, size):
    parts = Path(path).parts
    name = Path(path).name.lower()

    if any(part.lower() in EXCLUDED_DIRS for part in parts):
        return True

    if name in EXCLUDED_FILES:
        return True

    if any(word in name for word in (
        "secret", "credential", "private_key"
    )):
        return True

    if Path(path).suffix.lower() not in ALLOWED_EXTENSIONS:
        return True

    if size is None or size > MAX_FILE_BYTES:
        return True

    return False


def chunk_text(text):
    lines = text.splitlines()
    chunks = []
    start = 0

    while start < len(lines):
        end = min(start + CHUNK_LINES, len(lines))
        content = "\n".join(lines[start:end]).strip()

        if content:
            chunks.append(content)

        if end == len(lines):
            break

        start = end - OVERLAP_LINES

    return chunks


def ingest_repository(owner, repo):
    session = make_session()
    repo_url = f"{API_URL}/repos/{owner}/{repo}"

    metadata = get_json(session, repo_url)
    branch = metadata["default_branch"]
    full_name = metadata["full_name"]

    # Obtiene el SHA real del commit de la rama predeterminada.
    encoded_branch = quote(branch, safe="")
    branch_data = get_json(
        session,
        f"{repo_url}/branches/{encoded_branch}",
    )

    commit_sha = branch_data["commit"]["sha"]
    tree_sha = branch_data["commit"]["commit"]["tree"]["sha"]

    tree_data = get_json(
        session,
        f"{repo_url}/git/trees/{tree_sha}",
        params={"recursive": "1"},
    )

    if tree_data.get("truncated"):
        raise RuntimeError(
            f"GitHub truncó el árbol de {full_name}. "
            "Necesitamos una estrategia de ingesta por directorios."
        )

    records = []
    files_processed = 0

    print(f"\nRepositorio: {full_name}")
    print(f"Rama: {branch}")
    print(f"Commit: {commit_sha}")

    for item in tree_data["tree"]:
        if item["type"] != "blob":
            continue

        path = item["path"]

        if should_skip(path, item.get("size")):
            continue

        blob = get_json(
            session,
            f"{repo_url}/git/blobs/{item['sha']}",
        )

        if blob.get("encoding") != "base64":
            continue

        try:
            raw_content = base64.b64decode(blob["content"])
            if len(raw_content) > MAX_FILE_BYTES:
                continue

            content = raw_content.decode("utf-8")
        except (ValueError, UnicodeError, KeyError):
            print(f"Archivo omitido (no UTF-8): {path}")
            continue

        if not content.strip():
            continue

        chunks = chunk_text(content)

        for index, chunk in enumerate(chunks):
            records.append({
                "repository": full_name,
                "branch": branch,
                "commit_sha": commit_sha,
                "file_path": path,
                "file_sha": item["sha"],
                "chunk_index": index,
                "text": chunk,
            })

        files_processed += 1
        print(f"Procesado: {path}")

    print(f"Archivos procesados: {files_processed}")
    print(f"Fragmentos generados: {len(records)}")

    return records


def save_records(records, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Escribe primero un archivo temporal para no dejar
    # una salida parcialmente escrita si ocurre un error.
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_path.parent,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)

            for record in records:
                temp_file.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )

        os.replace(temp_path, output_path)

    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingesta múltiples repositorios desde GitHub"
    )
    parser.add_argument(
        "repositories",
        nargs="+",
        help="Repositorios con formato owner/repo",
    )
    args = parser.parse_args()

    all_records = []
    seen_repositories = set()

    try:
        for repository in args.repositories:
            parts = repository.split("/")

            if len(parts) != 2 or not all(parts):
                raise ValueError(
                    f"Formato inválido: {repository}. Usa owner/repo."
                )

            owner, repo = parts
            key = f"{owner.lower()}/{repo.lower()}"

            if key in seen_repositories:
                print(f"Repositorio duplicado, se omite: {repository}")
                continue

            seen_repositories.add(key)
            all_records.extend(ingest_repository(owner, repo))

        output_path = Path("data") / "chunks.jsonl"
        save_records(all_records, output_path)

        print("\nIngesta completada.")
        print(f"Repositorios solicitados: {len(seen_repositories)}")
        print(f"Total de fragmentos: {len(all_records)}")
        print(f"Archivo de salida: {output_path.resolve()}")

    except (
        requests.RequestException,
        RuntimeError,
        OSError,
        ValueError,
    ) as error:
        print(f"\nError durante la ingesta: {error}")
        raise SystemExit(1)
