"""Brands of IP cameras / recorders that Rack Live recognises (rackd/cameras.py).

Recognition is by what the device says about itself without a login: the web server name, the login realm, the page title, the RTSP server name, the ports
and (for the few makers whose prefixes are certain) the MAC address. «family» tells which vendor API stays as a fallback next to ONVIF:
  hikvision — ISAPI (activation of a new camera, status), dahua — userManager.cgi (password), '' — ONVIF only.
Order matters: the specific brand (an OEM of a big maker) goes before the maker itself."""
import re

# name, family, regex over the lower-cased «blob», first-password tip (what the maker uses to activate / set it), OUI prefixes (only the sure ones)
BRANDS = [
    ('EZVIZ', 'hikvision', r'ezviz', 'приложение EZVIZ (код на наклейке камеры); для ONVIF включите его в настройках камеры', ()),
    ('HiWatch', 'hikvision', r'hiwatch', 'программа SADP от Hikvision или веб-страница камеры', ()),
    ('HiLook', 'hikvision', r'hilook', 'программа SADP от Hikvision или веб-страница камеры', ()),
    ('Hikvision', 'hikvision', r'hikvision|dnvrs-webs|app-webs|/isapi/|\bdvrdvs\b', 'программа SADP от Hikvision (или Rack Live — для части моделей)',
     ('44:19:b6', 'bc:ad:28', 'c0:56:e3', '28:57:be', 'a4:14:37', '54:c4:15', '4c:bd:8f')),
    ('Imou', 'dahua', r'imou', 'приложение Imou Life', ()),
    ('Amcrest', 'dahua', r'amcrest', 'Amcrest Smart Home / ConfigTool', ()),
    ('Lorex', 'dahua', r'lorex', 'приложение Lorex / ConfigTool', ()),
    ('RVi', 'dahua', r'\brvi\b|rvi-', 'программа ConfigTool или веб-страница камеры', ()),
    ('KBVision', 'dahua', r'kbvision', 'программа ConfigTool', ()),
    ('Dahua', 'dahua', r'dahua|dh-ipc|dh-sd|dhwebclient|rpc2_login|login to [0-9a-z]{10,}', 'программа ConfigTool от Dahua или веб-страница камеры',
     ('3c:ef:8c', '4c:11:bf', '90:02:a9', 'e0:50:8b')),
    ('Tiandy', '', r'tiandy|easy7', 'программа производителя (EasyLive / веб-страница камеры)', ()),
    ('Tapo (TP-Link)', '', r'tapo', 'приложение Tapo; для ONVIF создайте там «Учётную запись камеры» (порт 2020)', ()),
    ('TP-Link VIGI', '', r'vigi', 'приложение VIGI / веб-страница камеры', ()),
    ('Reolink', '', r'reolink', 'программа или приложение Reolink', ('ec:71:db',)),
    ('Trassir', '', r'trassir', 'программа Trassir или веб-страница камеры', ()),
    ('Tracer', '', r'tracer|трейсер', 'веб-страница камеры или программа производителя', ()),
    ('Uniview (UNV)', '', r'uniview|\bunv\b|ipc[0-9a-z]{3,4}-[0-9a-z]', 'программа EZTools или веб-страница камеры', ()),
    ('Uniarch', '', r'uniarch', 'веб-страница камеры', ()),
    ('TVT', '', r'\btvt\b|td-\d{4}', 'веб-страница камеры', ()),
    ('Hanwha Wisenet', '', r'hanwha|wisenet|samsung techwin', 'веб-страница камеры', ('00:09:18',)),
    ('Axis', '', r'\baxis\b', 'веб-страница камеры (задать пароль root при первом входе)', ('00:40:8c', 'ac:cc:8e', 'b8:a4:4f')),
    ('Bosch', '', r'bosch', 'веб-страница камеры', ('00:04:63',)),
    ('Sony', '', r'sony network camera|sony corporation', 'веб-страница камеры', ()),
    ('Panasonic i-PRO', '', r'panasonic|i-pro', 'веб-страница камеры', ()),
    ('Vivotek', '', r'vivotek', 'веб-страница камеры', ('00:02:d1',)),
    ('Mobotix', '', r'mobotix', 'веб-страница камеры', ('00:03:c5',)),
    ('Avigilon', '', r'avigilon', 'веб-страница камеры', ()),
    ('Pelco', '', r'pelco', 'веб-страница камеры', ()),
    ('Milesight', '', r'milesight', 'веб-страница камеры', ()),
    ('Foscam', '', r'foscam|fosbaby', 'приложение Foscam', ()),
    ('Ubiquiti UniFi', '', r'ubiquiti|unifi', 'UniFi Protect', ()),
    ('Xiaomi', '', r'xiaomi|mijia|imilab', 'приложение Mi Home (ONVIF у части моделей)', ()),
    ('Xiongmai (XMEye)', '', r'xmeye|xiongmai|dvrip|netsurveillance|sofia', 'приложение XMEye', ()),
    ('Beward', '', r'beward', 'веб-страница камеры', ()),
    ('Optimus', '', r'optimus', 'веб-страница камеры', ()),
    ('Falcon Eye', '', r'falcon ?eye', 'веб-страница камеры', ()),
    ('Ivideon', '', r'ivideon', 'приложение Ivideon', ()),
    ('Rubetek', '', r'rubetek', 'приложение Rubetek', ()),
    ('Provision-ISR', '', r'provision', 'веб-страница камеры', ()),
    ('Annke', '', r'annke', 'приложение AnnkeView / веб-страница камеры', ()),
    ('Swann', '', r'swann', 'приложение Swann Security', ()),
    ('Longse', '', r'longse', 'веб-страница камеры', ()),
    ('Smartec', '', r'smartec', 'веб-страница камеры', ()),
    ('Microdigital', '', r'microdigital', 'веб-страница камеры', ()),
    ('Polyvision', '', r'polyvision', 'веб-страница камеры', ()),
]
_RX = [(n, f, re.compile(rx), how, oui) for n, f, rx, how, oui in BRANDS]
BY_NAME = {n: (f, how) for n, f, _, how, _ in BRANDS}


def detect(blob, ports=(), mac=''):
    """→ (brand, family, tip) or ('', '', '')"""
    blob = (blob or '').lower()
    for n, f, rx, how, oui in _RX:
        if rx.search(blob):
            return n, f, how
    m = (mac or '').lower()[:8]
    if m:
        for n, f, rx, how, oui in _RX:
            if m in oui:
                return n, f, how
    ports = set(ports or ())
    if 37777 in ports:
        return 'Dahua', 'dahua', BY_NAME['Dahua'][1]
    if 8000 in ports:
        return 'Hikvision', 'hikvision', BY_NAME['Hikvision'][1]
    if 34567 in ports:
        return 'Xiongmai (XMEye)', '', BY_NAME['Xiongmai (XMEye)'][1]
    if 2020 in ports:
        return 'Tapo (TP-Link)', '', BY_NAME['Tapo (TP-Link)'][1]
    return '', '', ''


def public():
    return [{'name': n, 'family': f} for n, f, _, _, _ in BRANDS]
