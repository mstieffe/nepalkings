"""Generate Windows version info for PyInstaller."""

# This creates a VSVersionInfo structure that embeds version metadata
# into the Windows .exe, improving SmartScreen reputation.

VSVersionInfo = None
try:
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo as _VSVersionInfo,
        FixedFileInfo,
        StringFileInfo,
        StringTable,
        StringStruct,
        VarFileInfo,
        VarStruct,
    )

    VSVersionInfo = _VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(0, 1, 1, 0),
            prodvers=(0, 1, 1, 0),
            mask=0x3F,
            flags=0x0,
            OS=0x40004,        # VOS_NT_WINDOWS32
            fileType=0x1,      # VFT_APP
            subtype=0x0,
        ),
        kids=[
            StringFileInfo([
                StringTable(
                    '040904B0',  # lang=US English, charset=Unicode
                    [
                        StringStruct('CompanyName', 'Nepal Kings'),
                        StringStruct('FileDescription', 'Nepal Kings Card Game'),
                        StringStruct('FileVersion', '0.1.1'),
                        StringStruct('InternalName', 'NepalKings'),
                        StringStruct('OriginalFilename', 'NepalKings.exe'),
                        StringStruct('ProductName', 'Nepal Kings'),
                        StringStruct('ProductVersion', '0.1.1'),
                    ],
                ),
            ]),
            VarFileInfo([VarStruct('Translation', [0x0409, 1200])]),
        ],
    )
except ImportError:
    pass
