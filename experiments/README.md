# experiments/

One subdirectory per training run, so `analysis/compare_agents.py`'s
"compare two runs" actually has two well-defined things to compare instead
of both scripts silently sharing (and overwriting) the same checkpoint
slot.

`referee/training/train.py` creates `experiments/checkpoints/<run_id>/`
automatically (pass `--run-id` to name one explicitly, or it'll generate a
timestamp-based one). Nothing else needs to be created by hand — this
directory is intentionally otherwise empty in source control; checkpoints
and eval logs are run artifacts, not something to commit.

Suggested layout per run, once you're doing enough of these to want it
formalized:

```
experiments/
  checkpoints/<run_id>/checkpoint_*.pt   # written by train.py
  eval_logs/<run_id>.json                # written by evaluate.py --out
  configs/<run_id>.yaml                  # a copy of the ppo_config.yaml used, for reproducibility
```
