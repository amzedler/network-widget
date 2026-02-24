from setuptools import setup

APP = ['network_widget.py']

OPTIONS = {
    'argv_emulation': False,
    'packages': ['rumps', 'speedtest'],
    'plist': {
        'LSUIElement': True,          # menu-bar only — no Dock icon, no app switcher
        'CFBundleName': 'Network Widget',
        'CFBundleDisplayName': 'Network Widget',
        'CFBundleIdentifier': 'com.local.network-widget',
        'CFBundleVersion': '1.0.0',
    },
}

setup(
    name='Network Widget',
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
