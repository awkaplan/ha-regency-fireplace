#!/usr/bin/env bash
# Install Home Assistant 2026.11.1 plus pytest-homeassistant-custom-component.
#
# The newest harness release (0.13.375) still pins Home Assistant 2026.10.4,
# whose radio_frequency consumer API differs from 2026.11. Install the harness,
# then upgrade Home Assistant, then fix the one import the harness gets wrong
# against 2026.11 (_clear_logger_overwrites moved to logger.helpers).
# Drop this workaround once a harness release pins 2026.11.
set -euo pipefail
python -m pip install --upgrade pip
python -m pip install pytest-homeassistant-custom-component==0.13.375
python -m pip install homeassistant==2026.11.1 rf-protocols==4.3.0
python - <<'PY'
import importlib.util, pathlib
common = pathlib.Path(importlib.util.find_spec("pytest_homeassistant_custom_component").origin).parent / "common.py"
text = common.read_text()
old = "    SERVICE_SET_LEVEL,\n    _clear_logger_overwrites,\n)"
new = "    SERVICE_SET_LEVEL,\n)\nfrom homeassistant.components.logger.helpers import _clear_logger_overwrites"
if old in text:
    common.write_text(text.replace(old, new))
    print("patched", common)
PY
