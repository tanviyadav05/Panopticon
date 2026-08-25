# DeepSeek-R1 weights go here

This directory is where `server/inference_engine.py`'s `transformers`
backend (`LLM_BACKEND=transformers`) expects to find a local Hugging
Face-format checkpoint — `config.json`, tokenizer files, and the model
shards.

This repo doesn't ship the weights themselves (multi-gigabyte binary
files don't belong in source control, and licensing/distribution terms are
DeepSeek's to set, not this project's). To populate this directory:

```bash
# using the huggingface CLI, on the LLM laptop (01):
pip install -U huggingface_hub
huggingface-cli download deepseek-ai/DeepSeek-R1 --local-dir llm-core/models/deepseek-r1
```

Until you do that, `LLM_BACKEND` defaults to `mock`, which needs nothing
here and is enough to exercise the rest of the pipeline (see
server/inference_engine.py's docstring).
