# OSINT agent & workflow configs

Persona / C2 demo agents and workflows for Operation RED HORIZON live here
(not under `tkeir/configs/`). The agent service discovers them via:

- `datasets/<pack>/agents/*.yaml`
- `datasets/<pack>/workflows/*.yaml`

Docker images may also ship packs under ``<package>/packs/<pack>/agents/``.
Core / product-neutral agents remain in `tkeir/configs/agents/` and
`tkeir/configs/workflows/` (`researcher`, `content_brief`, `okf_wiki_brief`, …).

Images copy OSINT packs to `tkeir/packs/osint/{agents,workflows}` (see
`Dockerfile.tkeir-lib`).

| Kind | Path |
|------|------|
| Persona agents | `agents/<persona>_{analyser,reviewer,writer}.yaml` |
| Persona wiki prompts | `agents/<persona>_prompt.yaml` (OKF iterative wiki) |
| Shared writers | `agents/wiki_writer.yaml` |
| Persona workflows | `workflows/persona_*.yaml` |
| Shared C2 / wiki | `workflows/otan_c2_brief.yaml`, `workflows/llm_wiki.yaml` |
