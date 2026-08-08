# Declarative twin

This bundle declares the same four pieces as the imperative demo:

- `VectorStore`: Turbopuffer, using the shared credential from a Kubernetes Secret.
- `Warehouse`: public Wikimedia content exposed through Hugging Face's dataset mirror.
- `Pipeline`: paragraph-sized CPU extraction into `wiki-simple`; paused until the stock source can declare the Lattice embed profile directly.
- `Index`: cosine-distance operational policy for the namespace.

The live slice is intentionally loaded with `uv run python -m indexer`, because that path sends the documented `embed.serving.prefer: lattice` schema directly to the gateway and is the exact demo contract. The Pipeline remains paused so it cannot stage unembedded rows. Unpause only after configuring the worker to write the schema from `wiki_common.gateway.embedding_schema()`.

Create the credential without committing it:

```sh
kubectl -n wiki create secret generic wiki-turbopuffer \
  --from-literal=credential="$LAYER_GATEWAY_API_KEY"
kubectl apply -f deploy/namespace.yaml
kubectl apply -f deploy/vectorstore.yaml -f deploy/warehouse.yaml -f deploy/pipeline.yaml
kubectl apply -f deploy/index.yaml
```
