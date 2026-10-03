# Reproducible packaging. Qt uses the Windows system ICU, not Poppler ICU.
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / "desktop_entry.py")], pathex=[str(root)], binaries=[],
             datas=[(str(root / "samples"), "samples"), (str(root / "assets" / "vrmbench.ico"), "assets")], hiddenimports=[],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
             noarchive=False, optimize=0)
a.binaries = [item for item in a.binaries
              if item[0].lower() not in ("icuuc.dll", "icudt78.dll")]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VRMBench",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False, icon=str(root / "assets" / "vrmbench.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VRMBench")
