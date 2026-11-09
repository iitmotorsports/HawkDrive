from pathlib import Path

import cantools
from cantools.database import Database

dbc_path = Path(__file__).parent.parent / "resources" / "hawkdrive.dbc"


db: Database = cantools.database.load_file(dbc_path)
print(db.messages)
example_message = db.get_message_by_name('EngineData')
print(example_message.signals)
