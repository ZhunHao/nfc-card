"""Private contact details for the card backs.

The committed boards are built without a phone number. To print one on your own
cards, copy `contact.example.json` (repo root) to `contact.local.json` (gitignored),
fill it in, and export with it:

    python3 scripts/export-card.py orbit --contact contact.local.json

That rebuilds a private copy of the board under `build/personal/` and exports the
fab package from it; the boards under `hardware/` are never touched. The builders
read the file named by the CARD_CONTACT environment variable, if any.
"""
import json
import os

PHONE = ''

_path = os.environ.get('CARD_CONTACT')
if _path:
    with open(_path, encoding='utf-8') as f:
        PHONE = json.load(f).get('phone', '')
