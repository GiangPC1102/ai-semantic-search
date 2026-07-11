#!/bin/sh
set -e

MODEL_DIR="${BGE_M3_MODEL_PATH:-/app/models/bge-m3}"
MARKER="$MODEL_DIR/config.json"

if [ ! -f "$MARKER" ]; then
  echo "[entrypoint] BGE-M3 model not found at $MODEL_DIR — downloading from HuggingFace..."
  python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='BAAI/bge-m3',
    local_dir='$MODEL_DIR',
    ignore_patterns=['*.msgpack', '*.h5', 'flax_model*', 'tf_model*', 'onnx/*'],
)
print('[entrypoint] Download complete.')
"
else
  echo "[entrypoint] BGE-M3 model found at $MODEL_DIR — skipping download."
fi

exec "$@"
