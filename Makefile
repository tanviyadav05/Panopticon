.PHONY: help setup-arena reset-arena cleanup-arena train evaluate dashboard \
        llm-server red-attacker blue-controller test test-go test-python test-integration \
        anomaly-model probe-targets killswitch \
        agent-graph-demo observability-up observability-down observability-logs node-exporter-install

help:
	@echo "Project Panopticon — common entrypoints"
	@echo ""
	@echo "  Arena (run on laptop 04):"
	@echo "    make setup-arena       - bring up the Kubernetes Arena"
	@echo "    make reset-arena       - reset between episodes"
	@echo "    make cleanup-arena     - tear the Arena down"
	@echo ""
	@echo "  Services (run on the matching laptop):"
	@echo "    make llm-server        - laptop 01 (multi-agent stack, see docs/multi_agent_llm.md)"
	@echo "    make red-attacker      - laptop 02"
	@echo "    make blue-controller   - laptop 03"
	@echo "    make dashboard         - laptop 05 (set PANOPTICON_DEMO=1 for synthetic data)"
	@echo ""
	@echo "  Training (laptop 05, or any single machine in sim mode):"
	@echo "    make train             - run referee/training/train.py"
	@echo "    make evaluate          - run referee/training/evaluate.py against the latest checkpoint"
	@echo ""
	@echo "  Observability (Prometheus + Grafana, see docs/observability.md):"
	@echo "    make node-exporter-install  - install node_exporter on THIS laptop (run on all 5)"
	@echo "    make observability-up        - start Prometheus + Grafana (laptop 05 only)"
	@echo "    make observability-down      - stop them"
	@echo "    make observability-logs      - tail both containers' logs"
	@echo ""
	@echo "  Misc:"
	@echo "    make anomaly-model     - (re)bootstrap blue-team's detection_model.pkl"
	@echo "    make probe-targets     - run one round of arena/targets probing, print results"
	@echo "    make agent-graph-demo  - run the 4-agent LangGraph flow once against a sample task"
	@echo "    make killswitch        - stop all local Red/Blue processes immediately"
	@echo "    make test              - go test + python compileall + integration tests"

setup-arena:
	cd arena/scripts && ./setup.sh

reset-arena:
	cd arena/scripts && ./reset.sh

cleanup-arena:
	cd arena/scripts && ./cleanup.sh

llm-server:
	cd llm-core/server && python3 llm_server.py

red-attacker:
	cd red-team/attacks && python3 red_attacker.py

blue-controller:
	cd blue-team/countermeasures && python3 blue_controller.py

dashboard:
	cd monitoring && python3 dashboard_server.py

train:
	cd referee/training && python3 train.py $(ARGS)

evaluate:
	cd referee/training && python3 evaluate.py $(ARGS)

anomaly-model:
	cd blue-team/countermeasures && python3 anomaly_detector.py

probe-targets:
	python3 -c "from arena.targets.target_registry import registry; registry.probe_all(); [print(t.to_dict()) for t in registry.all_targets()]"

agent-graph-demo:
	cd llm-core && python3 -c "\
from graph.agent_graph import run_agent_graph; \
import json; \
result = run_agent_graph(task='Investigate the wifi_router target and propose a plan to test its resilience.', target_context={'device_type': 'wifi_router'}); \
print(json.dumps({k: v for k, v in result.items() if k != 'history'}, indent=2)); \
print(f'\n{len(result[\"history\"])} agent turns (mocked unless Ollama is reachable at agents_config.yaml\\'s ollama.host)')"

killswitch:
	./containment/killswitch.sh

observability-up:
	cd observability && docker compose up -d

observability-down:
	cd observability && docker compose down

observability-logs:
	cd observability && docker compose logs -f

node-exporter-install:
	cd observability/node_exporter && sudo ./install_node_exporter.sh

test: test-go test-python test-integration

test-go:
	cd arena/target-app && go build ./... && go vet ./... && go test ./...

test-python:
	@for d in observer referee red-team blue-team llm-core monitoring analysis arena common; do \
		echo "compiling $$d..."; python3 -m compileall -q $$d || exit 1; \
	done

test-integration:
	python3 -m pytest tests/integration/ -v
