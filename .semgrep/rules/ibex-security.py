# Semgrep rule fixtures for ibex-security.yml (run: semgrep --test .semgrep/rules/).
# Not scanned by CI hard gate (that job targets services/ and packages/ only).

# --- ibex-memory-no-ml-imports: direct ---
# ruleid: ibex-memory-no-ml-imports
import torch
# ruleid: ibex-memory-no-ml-imports
import tensorflow
# ruleid: ibex-memory-no-ml-imports
import transformers
# ruleid: ibex-memory-no-ml-imports
import sentence_transformers
# ruleid: ibex-memory-no-ml-imports
import sklearn

# --- ibex-memory-no-ml-imports: aliased ---
# ruleid: ibex-memory-no-ml-imports
import torch as torch_lib
# ruleid: ibex-memory-no-ml-imports
import tensorflow as tf
# ruleid: ibex-memory-no-ml-imports
import transformers as hf
# ruleid: ibex-memory-no-ml-imports
import sentence_transformers as st
# ruleid: ibex-memory-no-ml-imports
import sklearn as sk

# --- ibex-memory-no-ml-imports: submodule ---
# ruleid: ibex-memory-no-ml-imports
import torch.nn
# ruleid: ibex-memory-no-ml-imports
import tensorflow.keras
# ruleid: ibex-memory-no-ml-imports
import transformers.models
# ruleid: ibex-memory-no-ml-imports
import sentence_transformers.models
# ruleid: ibex-memory-no-ml-imports
import sklearn.metrics

# --- ibex-memory-no-ml-imports: aliased submodule ---
# ruleid: ibex-memory-no-ml-imports
import torch.nn as nn
# ruleid: ibex-memory-no-ml-imports
import tensorflow.keras as keras
# ruleid: ibex-memory-no-ml-imports
import transformers.models as hf_models
# ruleid: ibex-memory-no-ml-imports
import sentence_transformers.models as st_models
# ruleid: ibex-memory-no-ml-imports
import sklearn.metrics as sk_metrics

# --- ibex-memory-no-ml-imports: from-submodule ---
# ruleid: ibex-memory-no-ml-imports
from torch.nn import Linear
# ruleid: ibex-memory-no-ml-imports
from tensorflow.keras import Model
# ruleid: ibex-memory-no-ml-imports
from transformers.models import bert
# ruleid: ibex-memory-no-ml-imports
from sentence_transformers.util import cos_sim
# ruleid: ibex-memory-no-ml-imports
from sklearn.model_selection import train_test_split

# ok: ibex-memory-no-ml-imports
import httpx
# ok: ibex-memory-no-ml-imports
from sqlalchemy import text
