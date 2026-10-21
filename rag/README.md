# Azure AI Search indexing

The chat API retrieves vectors from the Azure AI Search index configured by
`AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_INDEX`. It uses
`DefaultAzureCredential`, so the Function App identity needs the **Search
Index Data Reader** role. The identity used to run indexing needs **Search
Index Data Contributor** and permission to call the embedding deployment.

For local indexing, set these values in `.env`:

```text
AZURE_SEARCH_ENDPOINT=https://<search-service-name>.search.windows.net
AZURE_SEARCH_INDEX=chathubdixon-index
```

The deployment parameter file reads the four Azure AI endpoint/deployment
values from environment variables with the same names as the `.env` keys.
Set them in the shell before running `az deployment sub create`.

To add or refresh repositories, configure Azure authentication and the
embedding settings in the environment (or `.env`), then run:

```powershell
python -m rag.update owner/repository
```

Pass multiple `owner/repository` values to synchronize several repositories.
The command reads files from GitHub, generates embeddings, creates the search
index if needed, upserts the repository's documents, and removes stale chunks
for that repository. Set `GITHUB_TOKEN` when ingesting private repositories
or to avoid unauthenticated GitHub API rate limits.

To seed the index from the existing local embedding file without regenerating
vectors, run:

```powershell
python -m rag.update --from-embeddings
```

The first indexing run creates the index using the embedding vector
dimensions returned by the configured model. Changing to a model that returns
a different vector size requires a new index.
