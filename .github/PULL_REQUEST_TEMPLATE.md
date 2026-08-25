## What does this change?

## Which component(s)?
- [ ] arena/ (target-app, k8s manifests, or targets/ device probing)
- [ ] observer/
- [ ] referee/ (env, rewards, or training)
- [ ] red-team/
- [ ] blue-team/
- [ ] llm-core/ (agents, graph, memory, or tools)
- [ ] monitoring/
- [ ] observability/ (Prometheus/Grafana)
- [ ] analysis/ or docs/

## Checklist
- [ ] `go test ./...` passes (if you touched `arena/target-app/`)
- [ ] Ran the relevant component's smoke test locally (sim mode is enough for env/reward/training changes)
- [ ] If you touched `observer/pipeline/state_schema.json` or `common/action_spaces.py`: updated every consumer listed in that file's own docstring/comments
- [ ] If you added a new Red action: it's a simulated effect model (see `red-team/attacks/README.md`), not live attack code
- [ ] If you added/renamed a Prometheus metric: updated the matching Grafana dashboard panel(s) in `observability/grafana/dashboards/`
- [ ] `python3 -m pytest tests/integration/ -v` passes

## Anything reviewers should look closely at?
