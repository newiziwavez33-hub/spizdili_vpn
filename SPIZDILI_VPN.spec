# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3/windows/main_win.py'],
    pathex=['Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3', 'Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3/windows'],
    binaries=[],
    datas=[('Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3/icons', 'icons'), ('Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3/wavez_servers.json', '.'), ('Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3/bin/xray.exe', 'bin'), ('Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3/bin/geoip.dat', 'bin'), ('Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3/bin/geosite.dat', 'bin')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SPIZDILI_VPN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Z:/home/astra/vint/Downloads/spizdili_vpn-1.0.3/icons/spizdili-vpn.ico'],
)
