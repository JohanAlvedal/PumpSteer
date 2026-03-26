import sys
from pathlib import Path

# Lägg till projektrot (/config)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Lägg till pumpsteer-mappen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 🔥 VIKTIGAST: ladda stubbar först
import ha_test_stubs  # noqa: F401
