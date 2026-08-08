# SearXNG (deploy helper)

Canonical settings live in the package resources tree:

```text
tkeir/resources/searxng/settings.yml
```

`make searxng-up` / `make pull-searxng` copy that file to
`$(WORKSPACE)/searxng/config/settings.yml` when missing, then mount it at
`/etc/searxng/` in the container. Stop with `make searxng-down` (volumes kept).
