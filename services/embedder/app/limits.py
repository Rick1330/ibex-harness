"""Input limits for Embed (fail closed before upstream)."""

MAX_BATCH_TEXTS = 64
MAX_TEXT_BYTES = 32 * 1024  # 32 KiB per text
MAX_MODEL_ID_LEN = 256  # hosted profile model ids (e.g. BAAI/bge-m3)
