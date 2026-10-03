import os
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
(root/"work").mkdir(exist_ok=True)
os.environ["QT_QPA_PLATFORM"]="windows"
sys.argv=[sys.argv[0],"--self-test",str(root/"work"/"gui-test.json")]
from desktop_entry import run
run()
print("GUI discovery/read smoke OK")
