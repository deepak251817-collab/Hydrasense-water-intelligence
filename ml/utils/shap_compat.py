"""Compatibility shim: SHAP 0.48 with xgboost >= 3.0 models (Phase 5E).

Background
----------
xgboost 3.x serializes a scalar ``base_score`` in ``learner_model_param`` as a
one-element vector string (e.g. ``'[5E-1]'`` for 0.5), replacing the plain
float serialization used by xgboost 1.x/2.x. SHAP's ``XGBTreeModelLoader``
(shap <= 0.48, the newest line compatible with numpy 1.26) parses this field
with ``float(...)`` and raises:

    ValueError: could not convert string to float: '[5E-1]'

shap 0.49+ parses the vector form but requires numpy >= 2, which is
incompatible with the rest of this project's pinned numeric stack
(``numpy<2``). Since a one-element vector encoding of a scalar has exactly one
well-defined value, this shim normalizes the *decoded in-memory representation*
that SHAP reads so ``float()`` succeeds. The string ``'[<v>]'`` is rewritten to
``'<v>'``; any other format is left untouched and re-raises the original error.

Scope and safety
----------------
- Only the in-memory byte buffer SHAP decodes is patched. The model artifact
  on disk, its parameters, and its predictions/probabilities are untouched
  (verified by the Phase 5E test suite and the before/after prediction
  consistency checks in the explanation scripts).
- The shim is applied by the Phase 5E explanation scripts only, is idempotent,
  and never changes SHAP results: Tree SHAP contributions depend on tree
  structure and leaf values; the base score affects only the explainer's
  ``expected_value`` constant, which is parsed identically (0.5 == [5E-1]).
"""

from __future__ import annotations

import io
import re
from typing import Any

_BASE_SCORE_VECTOR_RE = re.compile(r"^\[\s*([+-]?[0-9.eE+-]+)\s*\]$")

_original_decode = None


def _normalize_vector_base_score(jmodel: Any) -> Any:
    """Rewrite a one-element vector ``base_score`` string to plain scalar form.

    Operates on the decoded ubjson dictionary SHAP builds from the model's
    raw byte dump; ``'[5E-1]'`` becomes ``'5E-1'`` so shap's ``float()``
    call succeeds. Other structures pass through unchanged.
    """
    try:
        learner = jmodel["learner"]
        param = learner["learner_model_param"]["base_score"]
    except (KeyError, TypeError):
        return jmodel
    if isinstance(param, str):
        match = _BASE_SCORE_VECTOR_RE.match(param)
        if match:
            learner["learner_model_param"]["base_score"] = match.group(1)
    return jmodel


def _patched_decode_ubjson_buffer(fd: io.BufferedIOBase) -> Any:
    assert _original_decode is not None
    return _normalize_vector_base_score(_original_decode(fd))


def apply_shap_xgboost_compat() -> None:
    """Make shap.TreeExplainer usable with xgboost >= 3.0 model dumps.

    Idempotent: repeated calls are no-ops. Raises nothing on its own; if the
    decode hook cannot be installed (unexpected shap layout) the caller will
    see SHAP's original error, unchanged.
    """
    global _original_decode
    if _original_decode is not None:
        return
    try:
        from shap.explainers import _tree as shap_tree_module
    except ImportError:
        return
    original = getattr(shap_tree_module, "decode_ubjson_buffer", None)
    if original is None:
        return
    _original_decode = original
    shap_tree_module.decode_ubjson_buffer = _patched_decode_ubjson_buffer
