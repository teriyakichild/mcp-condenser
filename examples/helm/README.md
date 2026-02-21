# Helm Examples

## Single upstream

```bash
helm install mcp-condenser ./helm/mcp-condenser -f examples/helm/values-single.yaml
```

## Multi-upstream

```bash
helm install mcp-condenser ./helm/mcp-condenser -f examples/helm/values-multi.yaml
```

## Helmfile

```bash
helmfile apply
```

Edit `helmfile.yaml` to switch between `values-single.yaml` and `values-multi.yaml`.

## Chart values reference

See the full [values.yaml](../../helm/mcp-condenser/values.yaml) for all available options.
