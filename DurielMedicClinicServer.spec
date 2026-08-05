# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('DurielMedic', 'DurielMedic'), ('DurielMedicApp', 'DurielMedicApp'), ('DurielEyeApp', 'DurielEyeApp'), ('DurielDentalApp', 'DurielDentalApp'), ('core', 'core'), ('templates', 'templates'), ('static', 'static'), ('staticfiles', 'staticfiles'), ('manage.py', '.'), ('requirements.txt', '.'), ('DESKTOP_VERSION', '.')]
datas += collect_data_files('tzdata')
datas += collect_data_files('crispy_forms')
datas += collect_data_files('crispy_tailwind')


a = Analysis(
    ['desktop_launcher.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['django.core.management.commands.migrate', 'django.core.management.commands.collectstatic', 'core.management.commands.activate_local_clinic', 'core.management.commands.sync_worker', 'core.management.commands.sync_once', 'waitress'],
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
    name='DurielMedicClinicServer',
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
)
