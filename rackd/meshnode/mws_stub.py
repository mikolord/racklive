#!/usr/bin/env python3
"""MWS-член Wi-Fi системы Keenetic для узла на OpenWrt (фаза 1: объявление + RCI).

Что делает:
  * рассылает WS-Discovery Hello (SOAP-over-UDP) на 239.255.255.250:3702;
  * поднимает plain-HTTP RCI-заглушку на объявленном порту и отвечает на пути,
    которые контроллер читает при acquisition;
  * логирует КАЖДЫЙ запрос контроллера (метод, путь, заголовки, тело) — это и есть
    запись диалога acquisition, по ней доводим контракт.

Запуск на узле:
  python3 mws_stub.py --iface br-lan --port 8089 --log /tmp/mws.log
"""
import argparse
import hashlib
import json
import os
import re
import socket
import struct
import sys
import threading
import time

WSD_GROUP = "239.255.255.250"
WSD_PORT = 3702
WSD_ADDR = (WSD_GROUP, WSD_PORT)
NS = {
    "wsa": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
    "wsd": "http://schemas.xmlsoap.org/ws/2005/04/discovery",
    "soap": "http://www.w3.org/2003/05/soap-envelope",
}

def _uuid4():
    """uuid4 без модуля uuid (в python3-light на OpenWrt его нет)."""
    b = os.urandom(16)
    b = bytes([(b[0] & 0x0F) | 0x40]) + b[1:8] + bytes([(b[8] & 0x3F) | 0x80]) + b[9:]
    h = b.hex()
    return "-".join([h[0:8], h[8:12], h[12:16], h[16:20], h[20:32]])


LOG_LOCK = threading.Lock()


def log(path, *parts):
    line = " ".join(str(p) for p in parts)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {line}\n")
    print(line, flush=True)


# ---------------------------------------------------------------- состояние
DOWN_UNTIL = [0]        # до этого времени узел считается выключенным (эмуляция reboot)

DEFAULTS = {
    "cid": None,
    "hostname": "openwrt-mws",
    "hw_id": "NAP-630",
    "hw_type": "extender",
    "model": "Orbiter 6 (NAP-630)",
    "fw": "5.1.6",
    "fw_release": "5.01.C.6.0-1",
    "fw_id": "805748992",
    "sandbox": "preview",
    "domain": "netcraze",
    "fqdn": None,
    "region": "EA",
    "serial": None,
    "mac": None,
    "port": 8089,
    "wlan": {},
    "csr": "/etc/mws/csr.pem",
    "csr_format": "keenetic",
    "csr_file": "",
    "resp_dir": "/etc/mws/resp",
    "cert_path": "/etc/mws/cert.pem",
    "ca_path": "/etc/mws/ca.pem",
    "creds": {},
}


def ensure_identity(key, csr, cid, logpath):
    """A fresh node has no key/CSR yet: EC P-256 key + CSR with a single-RDN subject CN=<cid> (the controller rejects more RDNs)."""
    os.makedirs(os.path.dirname(key) or ".", exist_ok=True)
    if not os.path.exists(key):
        os.system("openssl ecparam -name prime256v1 -genkey -noout -out %s 2>/dev/null; chmod 600 %s" % (key, key))
        log(logpath, "создан ключ", key)
    if not os.path.exists(csr) and os.path.exists(key):
        os.system("openssl req -new -key %s -subj /CN=%s -out %s 2>/dev/null" % (key, cid, csr))
        log(logpath, "создан CSR", csr)


# static identity defined in code (firmware/model) — always from DEFAULTS, never from the saved file,
# so updating the stub changes the reported version even on a reinstall that keeps the node's identity.
STATIC_KEYS = ("fw", "fw_release", "fw_id", "sandbox", "hw_id", "hw_type", "model", "domain")


class State:
    def __init__(self, path, **over):
        self.path = path
        self.data = dict(DEFAULTS)
        if os.path.exists(path):
            try:
                self.data.update(json.load(open(path, encoding="utf-8")))
            except Exception:
                pass
        for k in STATIC_KEYS:                       # код всегда главнее сохранённого файла для этих полей
            self.data[k] = DEFAULTS[k]
        self.data.update({k: v for k, v in over.items() if v not in (None, "")})
        if not self.data.get("cid"):
            self.data["cid"] = str(_uuid4())
        if not self.data.get("serial"):
            self.data["serial"] = "S" + hashlib.md5(self.data["cid"].encode()).hexdigest()[:11].upper()
        if not self.data.get("fqdn"):
            self.data["fqdn"] = hashlib.md5(self.data["cid"].encode()).hexdigest()[:24] + ".netcraze.io"
        self.save()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def __getitem__(self, k):
        return self.data.get(k)

    def __setitem__(self, k, v):
        self.data[k] = v
        self.save()


# ---------------------------------------------------------------- ответы RCI
def norm_path(path):
    """Контроллер после провижининга ходит по /https://<cid>/rci/… — снимаем префикс."""
    p = path.strip("/")
    m = re.match(r"^https?://[^/]+/(.*)$", p)
    if m:
        p = m.group(1)
    return p


def iface_map(mac):
    ports = {
        "0": {
            "id": "GigabitEthernet0/0",
            "index": 0,
            "interface-name": "0",
            "label": "0",
            "type": "Port",
            "traits": ["EthernetPort", "GigabitEthernetPort"],
            "link": "up",
            "speed": "1000",
            "duplex": "full",
            "auto-negotiation": "on",
            "flow-control": "off",
            "eee": "off",
            "admin-only": False,
            "summary": {"layer": {"conf": "running", "link": "running"}},
        }
    }
    ports["Bridge0"] = {
        "id": "Bridge0",
        "index": 0,
        "interface-name": "Bridge0",
        "type": "Bridge",
        "description": "Home network",
        "link": "up",
        "connected": "yes",
        "state": "up",
        "mtu": "1500",
        "address": "192.168.1.2",
        "mask": "255.255.255.0",
        "uptime": "1",
        "global": "no",
        "security-level": "public",
        "summary": {"layer": {"conf": "running", "link": "running"}},
    }
    for i in (0, 1):
        ports[f"WifiMaster{i}"] = {
            "id": f"WifiMaster{i}",
            "index": i,
            "interface-name": f"WifiMaster{i}",
            "type": "WifiMaster",
            "description": "2.4 GHz" if i == 0 else "5 GHz",
            "link": "up",
            "mac": mac,
            "band": "2.4" if i == 0 else "5",
            "channel": 1 if i == 0 else 36,
            "summary": {"layer": {"conf": "running", "link": "running"}},
        }
        for ap in range(2):
            ports[f"WifiMaster{i}/AccessPoint{ap}"] = {
                "id": f"WifiMaster{i}/AccessPoint{ap}",
                "index": ap,
                "interface-name": f"WifiMaster{i}/AccessPoint{ap}",
                "type": "AccessPoint",
                "description": "Access point",
                "link": "up",
                "mac": mac,
                "ssid": "",
                "encryption": "wpa2",
                "summary": {"layer": {"conf": "running", "link": "running"}},
            }
    return ports


def constants(port_count=1):
    return {
        "FW_FLASHING_SPEED": 2500000,
        "FW_BOOT_TIME": 65000,
        "FW_SHUTDOWN_TIME": 7000,
        "LAN": "Home",
        "LAN_DESCRIPTION": "Home network",
        "WAN": "ISP",
        "WAN_DESCRIPTION": "Broadband connection",
        "MASTER": "WifiMaster0",
        "MASTER_5G": "WifiMaster1",
        "AP": [f"WifiMaster0/AccessPoint{i}" for i in range(4)],
        "AP_5G": [f"WifiMaster1/AccessPoint{i}" for i in range(4)],
        "STA": "WifiMaster0/WifiStation0",
        "STA_5G": "WifiMaster1/WifiStation0",
        "WAN_SWITCH": "GigabitEthernet0",
        "LAN_SWITCH": "GigabitEthernet0",
        "WAN_PORT": "WAN",
        "ETHER_WAN_PORT": "WAN",
        "WAN_PORTS": {"WAN": 0},
        "HAS_TWO_SWITCHES": False,
        "LED_OPTIONS": ["ENABLED", "DISABLED_ALL"],
        "USB_PORTS_NUMBER": 0,
        "LANGUAGES_ORDER": ["ru", "en"],
        "PORTS_MAP": {
            "WAN": {
                "index": 0,
                "port": "0",
                "color": "gray",
                "type": "ethernet",
                "name": "0",
                "interfaceId": "GigabitEthernet0/0",
                "group": "WAN",
                "maxSpeed": 1000,
            }
        },
        "PORTS_LAYOUT": [["0"]] + ([["1"]] if port_count > 1 else []),
        "HAS_PORTS_STAT": True,
        "profile": {"config": {}, "components": {}, "languages": {"en": True, "ru": True}},
        "WIFI_SPEED_160_OFF": 1200,
        "WIFI_SPEED_160_ON": 2400,
    }


ENC = {"wpa2+3": "sae-mixed", "wpa3": "sae", "wpa2": "psk2", "wpa": "psk-mixed", "wpa+2": "psk-mixed"}
SEC = {"sae-mixed": "wpa2-psk", "sae": "wpa3-psk", "psk2": "wpa2-psk", "psk-mixed": "wpa-psk", "none": "open"}


def uq(v):
    """uci batch value in single quotes."""
    return "'" + str(v).replace("'", "'\\''") + "'"


class WifiApplier:
    """Keenetic's Wi-Fi (mws wlan + bridge VLANs from the config batch) -> OpenWrt uci 'mws_*' sections.
    The plan (which ssid is AccessPoint k on which Bridge) is kept in the state for the client report."""
    BATCH = "/tmp/mws-uci.batch"

    def __init__(self, st, shell):
        self.st = st
        self.shell = shell
        self.lock = threading.Lock()

    @staticmethod
    def extract(req):
        wlans, vlans, country = [], {}, None
        for item in (req if isinstance(req, list) else [req]):
            if not isinstance(item, dict):
                continue
            mws = item.get("mws")
            if isinstance(mws, dict):
                for w in mws.get("wlan") or []:
                    if isinstance(w, dict) and w.get("id"):
                        wlans.append(w)
                for cc in mws.get("country-code") or []:
                    if isinstance(cc, dict) and cc.get("code"):
                        country = cc["code"]
            for itf in item.get("interface") or []:
                if not isinstance(itf, dict):
                    continue
                name, iseg = itf.get("name", ""), itf.get("iseg")
                if re.match(r"^Bridge\d+$", name) and isinstance(iseg, dict) and "include" in iseg:
                    vlans[name] = iseg.get("vlan")
        return wlans, vlans, country

    def uplinks(self):
        """All ports of the br-lan bridge (the node may be cabled into any of them)."""
        out = self.shell("uci show network").splitlines()
        sec = None
        for ln in out:
            m = re.match(r"^network\.([^.=]+)\.name='br-lan'$", ln)
            if m:
                sec = m.group(1)
        ports = []
        for ln in out:
            m = re.match(r"^network\.%s\.ports=(.*)$" % re.escape(sec or "-"), ln)
            if m:
                ports = re.findall(r"'([^']+)'", m.group(1))
        return ports or ["eth0"]

    def radios(self):
        """band index Keenetic uses (0 = 2.4 GHz, 1 = 5 GHz) -> uci wifi-device; by the radio's band, not its number."""
        res = {}
        for ln in self.shell("uci show wireless").splitlines():
            m = re.match(r"^wireless\.([^.=]+)\.band='(\w+)'$", ln)
            if m:
                idx = {"2g": 0, "5g": 1}.get(m.group(2))
                if idx is not None and idx not in res:
                    res[idx] = m.group(1)
        return res

    def plan_of(self, wlans, vlans, country):
        aps = []
        for k, w in enumerate(wlans):
            bridge = (w.get("bind") or {}).get("interface", "Bridge0")
            enc = ENC.get(w.get("encryption") or "", "none")
            aps.append({
                "k": k, "id": w["id"], "bridge": bridge, "seg": int(bridge[6:] or 0), "vlan": vlans.get(bridge),
                "ssid": (w.get("ssid") or {}).get("name", ""), "hide": bool((w.get("ssid") or {}).get("hide")),
                "enc": enc, "key": (w.get("wpa") or {}).get("psk", "") if enc != "none" else "",
                "bands": [int(b) for b in w.get("band") or []], "rrm": bool((w.get("rrm") or {}).get("enable")),
                "isolate": bool(w.get("peer-isolation")), "enable": w.get("enable", True) is not False,
            })
        return {"aps": aps, "country": country or "RU", "uplinks": self.uplinks(), "radios": self.radios()}

    def maybe_apply(self, req):
        wlans, vlans, country = self.extract(req)
        if not wlans:
            return
        plan = self.plan_of(wlans, vlans, country)
        digest = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        if digest == self.st["wifi_digest"]:
            return
        threading.Thread(target=self._apply, args=(plan, digest), daemon=True).start()

    def _apply(self, plan, digest):
        with self.lock:
            lines = []
            wl_now = self.shell("uci show wireless")
            for cfg in ("network", "wireless"):
                for sec in re.findall(r"^%s\.(mws_[A-Za-z0-9_]+)=" % cfg, self.shell("uci show %s" % cfg), re.M):
                    lines.append("delete %s.%s" % (cfg, sec))
            radios = plan["radios"]
            nets = {}
            for ap in plan["aps"]:
                v = ap["vlan"]
                if not v:
                    nets[ap["bridge"]] = "lan"
                    continue
                dev, itf = "mws_br%s" % v, "mws_v%s" % v
                if ap["bridge"] not in nets:
                    lines += ["set network.%s=device" % dev, "set network.%s.type='bridge'" % dev,
                              "set network.%s.name='br-mws%s'" % (dev, v)]
                    lines += ["add_list network.%s.ports=%s" % (dev, uq("%s.%s" % (p, v))) for p in plan["uplinks"]]
                    lines += ["set network.%s=interface" % itf, "set network.%s.proto='none'" % itf,
                              "set network.%s.device='br-mws%s'" % (itf, v)]
                nets[ap["bridge"]] = itf
            for r in sorted(set(radios.values())):
                lines.append("set wireless.%s.country=%s" % (r, uq(plan["country"])))
                lines.append("set wireless.%s.disabled='0'" % r)
            for sec in re.findall(r"^wireless\.([^.=]+)=wifi-iface$", wl_now, re.M):   # the router's own networks step aside
                if not sec.startswith("mws_"):
                    lines.append("set wireless.%s.disabled='1'" % sec)
            for ap in plan["aps"]:
                for b in ap["bands"]:
                    if b not in radios:          # e.g. a 2.4-only router gets no 5 GHz copy
                        continue
                    s = "wireless.mws_%d_%d" % (ap["k"], b)
                    lines += ["set %s=wifi-iface" % s, "set %s.device=%s" % (s, uq(radios[b])), "set %s.mode='ap'" % s,
                              "set %s.network=%s" % (s, uq(nets[ap["bridge"]])), "set %s.ssid=%s" % (s, uq(ap["ssid"])),
                              "set %s.encryption=%s" % (s, uq(ap["enc"])), "set %s.hidden='%d'" % (s, ap["hide"]),
                              "set %s.isolate='%d'" % (s, ap["isolate"]), "set %s.ieee80211k='%d'" % (s, ap["rrm"]),
                              "set %s.ieee80211v='1'" % s, "set %s.disabled='%d'" % (s, not ap["enable"])]
                    if ap["enc"] != "none":
                        lines.append("set %s.key=%s" % (s, uq(ap["key"])))
                    if ap["enc"] in ("sae-mixed", "sae"):     # SAE needs PMF: optional for the mixed mode, required for pure WPA3
                        lines.append("set %s.ieee80211w='%d'" % (s, 1 if ap["enc"] == "sae-mixed" else 2))
            lines += ["commit network", "commit wireless"]
            batch = self.BATCH
            with open(batch, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.chmod(batch, 0o600)
            out = self.shell("uci batch < %s 2>&1; rm -f %s; /etc/init.d/network reload 2>&1; sleep 4; wifi reload 2>&1" % (batch, batch))
            self.st["wifi_plan"] = [{k: v for k, v in ap.items() if k != "key"} for ap in plan["aps"]]
            self.st["wifi_digest"] = digest
            log(self.st.logpath, "WIFI применён:", ", ".join("%s→%s%s" % (a["ssid"], a["bridge"], "" if not a["vlan"] else "/vlan%s" % a["vlan"])
                                                          for a in plan["aps"]), out.strip()[:300])


class Rci:
    """Ответы на пути RCI. Формы сняты с живого узла NAP-630 (refs/member_orbit)."""

    def __init__(self, st):
        self.st = st
        self.started = int(time.time())
        self.counter = 0
        self.down_until = 0
        self.wifi = WifiApplier(st, self._shell)

    def mac(self):
        return (self.st["mac"] or "02:00:00:00:00:01").lower()

    # -------------------------------------------------- show.* ресурсы
    def r_version(self):
        st = self.st
        return {
            "release": st["fw_release"],
            "sandbox": st["sandbox"],
            "title": st["fw"],
            "arch": (os.uname().machine if hasattr(os, "uname") else "aarch64"),
            "ndm": {"exact": "0-996b1e0", "cdate": "12 Sep 2026"},
            "bsp": {"exact": "0-5c4fe0ce31", "cdate": "12 Sep 2026"},
            "ndw": {
                "features": "dual_image,wifi5ghz,vht2ghz,mimo2ghz,mimo5ghz,atf2ghz,atf5ghz,wifi6,wifi_ft,wpa3,hwnat,hwnat_mib,cable_diag",
                "components": "base,cloudcontrol,corewireless,dhcpd,dns-filter,dot1x,easyconfig,igmp,ip6,l2tp,lang-en,lang-ru,miniupnpd,mws,nathelper-ftp,nathelper-h323,nathelper-pptp,nathelper-rtsp,nathelper-sip,ndmp,ndns,pingcheck,ppe,pppoe,pptp,trafficcontrol",
            },
            "ndw3": {"version": "5.1.17"},
            "ndw4": {"version": "5.1.C.6.0"},
            "manufacturer": "Netcraze Ltd.",
            "vendor": "Netcraze",
            "series": "NAP",
            "model": st["model"],
            "hw_version": "3006C100",
            "hw_type": st["hw_type"],
            "hw_id": st["hw_id"],
            "device": "Orbiter 6",
            "consent": st["region"],
            "region": st["region"],
            "description": st["hostname"],
        }

    def r_identification(self):
        st = self.st
        return {
            "servicetag": st["serial"],
            "serial": st["serial"],
            "mac": self.mac(),
            "hwid": st["hw_id"],
            "cid": st["cid"],
        }

    def r_system(self):
        mem = {}
        try:
            for ln in open("/proc/meminfo"):
                k, v = ln.split(":", 1)
                mem[k] = int(v.split()[0])
        except Exception:
            pass
        total, avail = mem.get("MemTotal", 524288), mem.get("MemAvailable", mem.get("MemFree", 340000))
        try:
            ncpu = max(1, os.cpu_count() or 1)
            load = min(100, int(float(open("/proc/loadavg").read().split()[0]) * 100 / ncpu))
        except Exception:
            load = 3
        return {
            "hostname": self.st["hostname"],
            "domainname": "WORKGROUP",
            "cpuload": load,
            "memory": "%d/%d" % (total - avail, total),
            "swap": "0/0",
            "memtotal": total,
            "memfree": avail,
            "uptime": str(int(time.time()) - self.started),
            "mode": "extender",
        }

    def r_system_mode(self):
        return {
            "active": "extender",
            "selected": "extender",
            "supported": "router, extender",
            "hw_controlled": False,
            "hw_locked": False,
        }

    def r_interface(self):
        out = iface_map(self.mac())
        for i in (0, 1):
            info = self._shell("iwinfo phy%d-ap0 info 2>/dev/null" % i)
            ch = re.search(r"Channel:\s*(\d+)", info)
            ssid = re.search(r'ESSID:\s*"([^"]*)"', info)
            master = "WifiMaster%d" % i
            if master in out and ch:
                out[master]["channel"] = int(ch.group(1))
            ap0 = "%s/AccessPoint0" % master
            if ap0 in out and ssid:
                out[ap0]["ssid"] = ssid.group(1)
        return out

    # -------------------------------------------------- клиенты и MWS-состояние
    def _shell(self, cmd):
        try:
            with os.popen(cmd) as f:
                return f.read()
        except Exception:
            return ""

    def controller_cid(self):
        """CID контроллера — это CN его CA-сертификата, который нам выдали в lock."""
        if getattr(self, "_ccid", None):
            return self._ccid
        cid = ""
        out = self._shell("openssl x509 -in %s -noout -subject 2>/dev/null" % self.st["ca_path"])
        m = re.search(r"CN\s*=\s*([0-9a-fA-F-]{36})", out)
        if m:
            cid = m.group(1)
        self._ccid = cid
        return cid

    @staticmethod
    def _rate(s):
        """'390.0 MBit/s HE-MCS 4 HE-NSS 2 HE-GI 0 80MHz' -> rate, mcs, nss, width, gi, mode"""
        rate = re.search(r"([\d.]+) MBit/s", s)
        mcs = re.search(r"MCS (\d+)", s)
        nss = re.search(r"NSS (\d+)", s)
        width = re.search(r"(\d+)MHz", s)
        m = int(mcs.group(1)) if mcs else 0
        mode = "11ax" if "HE-" in s else "11ac" if "VHT" in s else "11n" if mcs else "11g"
        return {"rate": int(float(rate.group(1))) if rate else 0, "mcs": m if nss or not mcs else m % 8,
                "nss": int(nss.group(1)) if nss else (m // 8 + 1 if mcs else 1), "ht": int(width.group(1)) if width else 20,
                "gi": 400 if ("short GI" in s or "HE-GI 1" in s) else 800, "mode": mode}

    def stations(self):
        """Клиенты всех точек OpenWrt (`iw dev` + `station dump`), привязанные к сетям Keenetic по ssid."""
        plan = {a["ssid"]: a for a in (self.st["wifi_plan"] or [])}
        out = []
        cur_if = None
        ifaces = []
        for line in self._shell("iw dev 2>/dev/null").splitlines():
            s = line.strip()
            if s.startswith("Interface "):
                cur_if = {"name": s.split()[1], "ssid": "", "ch": 0}
                ifaces.append(cur_if)
            elif cur_if is not None and s.startswith("ssid "):
                cur_if["ssid"] = s[5:]
            elif cur_if is not None and s.startswith("channel "):
                cur_if["ch"] = int(s.split()[1])
        for itf in ifaces:
            if not itf["ssid"]:
                continue
            band = 0 if 0 < itf["ch"] <= 14 else 1
            ap = plan.get(itf["ssid"], {"k": 0, "seg": 0, "bridge": "Bridge0", "enc": "psk2"})
            cur = None
            for line in self._shell("iw dev %s station dump 2>/dev/null" % itf["name"]).splitlines():
                s = line.strip()
                if s.startswith("Station "):
                    cur = {"mac": s.split()[1].lower(), "ap": "WifiMaster%d/AccessPoint%d" % (band, ap["k"]),
                           "psm": False, "authenticated": True, "txrate": 0, "rxrate": 0, "uptime": 0,
                           "txbytes": 0, "rxbytes": 0, "ht": 20, "mode": "11n", "gi": 800, "rssi": -60,
                           "mcs": 0, "txss": 1, "ebf": False, "dl-mu": False, "security": SEC.get(ap["enc"], "wpa2-psk"),
                           "_seg": ap["seg"], "_bridge": ap["bridge"]}
                    out.append(cur)
                elif cur is None:
                    continue
                elif s.startswith("signal:"):
                    mm = re.search(r"(-?\d+)", s)
                    if mm:
                        cur["rssi"] = int(mm.group(1))
                elif s.startswith("connected time:"):
                    cur["uptime"] = int(re.search(r"(\d+)", s).group(1))
                elif s.startswith("tx bytes:"):
                    cur["txbytes"] = int(s.split()[-1])
                elif s.startswith("rx bytes:"):
                    cur["rxbytes"] = int(s.split()[-1])
                elif s.startswith("authorized:"):
                    cur["authenticated"] = s.endswith("yes")
                elif s.startswith("tx bitrate:"):
                    r = self._rate(s)
                    cur.update(txrate=r["rate"], mcs=r["mcs"], txss=r["nss"], ht=r["ht"], gi=r["gi"], mode=r["mode"])
                elif s.startswith("rx bitrate:"):
                    cur["rxrate"] = self._rate(s)["rate"]
        return out

    def r_mws(self):
        """show.mws — как у настоящего Orbiter: клиенты в wireless-stations.segments[] по мостам."""
        recs = self.stations()
        segs = {}
        for a in (self.st["wifi_plan"] or [{"seg": 0, "bridge": "Bridge0"}]):
            segs.setdefault(a["seg"], {"index": a["seg"], "id": a["bridge"]})
        for r in recs:
            if not r["authenticated"]:          # a device still failing the password is not a client yet (a real AP doesn't list it)
                continue
            seg = segs.setdefault(r["_seg"], {"index": r["_seg"], "id": r["_bridge"]})
            seg.setdefault("station", []).append({k: v for k, v in r.items() if not k.startswith("_")})
        gw = re.search(r"default via (\S+)", self._shell("ip route 2>/dev/null"))
        return {
            "controller": {
                "cid": self.controller_cid(),
                "ip": gw.group(1) if gw else "192.168.1.1", "port": 80, "region": self.st["region"],
                "backhaul": {
                    "bridge": "Bridge0", "root": self.mac(), "uplink": "GigabitEthernet0",
                    "mac": self.mac(), "speed": "1000", "duplex": "full",
                    "port-label": "0", "cost": 1,
                },
            },
            "wired-links": {},
            "associations": {},
            "wireless-stations": {"segments": [segs[k] for k in sorted(segs)]},
        }

    def r_last_change(self):
        return {}

    def r_internet_status(self):
        return {
            "checked": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime()),
            "enabled": True, "reliable": True,
            "gateway-accessible": True, "dns-accessible": True,
            "captive-accessible": True, "internet": True,
            "gateway": {"interface": "Bridge0", "address": "192.168.1.1"},
        }

    def r_components(self):
        st = self.st
        return {
            "validity-period": "4711",
            "auto-update": {"disable": True, "channel": "stable"},
            "firmware": {"version": st["fw"], "release": st["fw_release"]},
        }

    def r_components_status(self):
        st = self.st
        return {
            "status": {"update": {"state": "idle"}},
            "check-update": {
                "title": st["fw"], "release": st["fw_release"], "sandbox": "stable",
                "checking": False, "update-available": False,
                "auto-update-pending": False, "auto-update-enabled": True,
                "sandboxes": [{"name": "stable", "version": st["fw_release"],
                               "title": st["fw"]}],
                "status": [],
            },
        }

    def r_components_list(self):
        st = self.st
        comp = {
            "base": {"version": st["fw"], "release": st["fw_release"]},
            "corewireless": {"version": st["fw"], "release": st["fw_release"]},
            "mws": {"version": st["fw"], "release": st["fw_release"]},
        }
        return {
            "firmware": {"version": st["fw"], "release": st["fw_release"]},
            "sandbox": "stable",
            "local": st["fw"],
            "component": comp,
            "group": {},
            "changelog": {},
        }

    SHOW = {
        "version": "r_version",
        "identification": "r_identification",
        "system": "r_system",
        "interface": "r_interface",
        "last-change": "r_last_change",
        "components": "r_components",
        "mws": "r_mws",
    }

    PROBES = {
        "mws wlan", "mws controller", "mws backhaul bss", "mws country-code",
        "mws sta-mask", "mws auth-token", "mws backhaul stp-encapsulation",
        "show mws associations", "show mws wired-links", "show mws wireless-stations",
    }

    def show(self, name, arg=None):
        if name == "internet":
            full = {"status": self.r_internet_status()}
            if isinstance(arg, dict) and arg:
                return {k: full.get(k, {}) for k in arg}
            return full
        if name == "mws":
            full = self.r_mws()
            if isinstance(arg, dict) and arg:
                return {k: full.get(k, {}) for k in arg}
            return full
        if name == "system" and isinstance(arg, list):
            # NDMS присылает список: [{}, {"mode": {}}] — отвечаем списком той же длины
            out = []
            for item in arg:
                if not isinstance(item, dict) or not item:
                    out.append(self.r_system())
                else:
                    out.append({k: (self.r_system_mode() if k == "mode" else {}) for k in item})
            return out
        if name == "system" and isinstance(arg, dict):
            out = {}
            for k in arg:
                if k == "mode":
                    out["mode"] = self.r_system_mode()
                else:
                    out[k] = {}
            return out
        fn = getattr(self, self.SHOW.get(name, ""), None)
        return fn() if fn else {}

    # -------------------------------------------------- диспетчер
    def handle(self, req):
        """Ответ на POST /rci/ — повторяем структуру запроса."""
        out = {}
        if not isinstance(req, dict):
            return {"status": [{"status": "ok"}]}
        if isinstance(req.get("show"), dict):
            out["show"] = {k: self.show(k, v) for k, v in req["show"].items()}
        if "probe" in req:
            items = req["probe"]
            if isinstance(items, list):
                out["probe"] = [{"found": (str(i) in self.PROBES)} for i in items]
        if isinstance(req.get("components"), dict):
            comp = {}
            for k in req["components"]:
                if k == "list":
                    comp["list"] = self.r_components_list()
                else:
                    comp[k] = {}
            out["components"] = comp
        if "system" in req and "show" not in req:
            out["system"] = self.show("system", req["system"])
        for k in req:
            out.setdefault(k, {})
        return out

    def template(self, key):
        """Готовый JSON-ответ из каталога шаблонов (<resp_dir>/<key>.json)."""
        path = "%s/%s.json" % (self.st["resp_dir"], key)
        try:
            raw = open(path, encoding="utf-8").read()
        except Exception:
            return None
        if not raw.strip():
            return None
        pem = ""
        try:
            pem = open(self.st["csr"], encoding="utf-8").read()
        except Exception:
            pass
        lines = pem.splitlines()
        b64 = "".join(lines[1:-1]) if len(lines) > 2 else ""
        raw = (raw.replace("%%PEM%%", json.dumps(pem)[1:-1])
                  .replace("%%B64%%", b64))
        try:
            return json.loads(raw)
        except Exception as e:
            log(self.st.logpath, "шаблон битый:", path, repr(e))
            return None

    def save_creds(self, body):
        """Контроллер выдал сертификат, CA, realm и токен — сохраняем."""
        creds = {}
        for k in ("realm", "ca-cert", "cert", "token", "tag"):
            v = body.get(k)
            if not v:
                continue
            if k in ("cert", "ca-cert"):
                name = self.st["cert_path"] if k == "cert" else self.st["ca_path"]
                try:
                    with open(name, "w", encoding="utf-8") as f:
                        f.write(v if v.endswith("\n") else v + "\n")
                except Exception as e:
                    log(self.st.logpath, "не записать", name, repr(e))
            else:
                creds[k] = v
        self.st["creds"] = creds
        log(self.st.logpath, "LOCK получен: realm=%r tag=%r token=%d байт, ca=%d, cert=%d"
            % (body.get("realm"), body.get("tag"), len(body.get("token") or ""),
               len(body.get("ca-cert") or ""), len(body.get("cert") or "")))

    def mws_response(self, req):
        """Ответ на POST /rci/mws: шаблон по имени команды, иначе — эхо-статус."""
        key = next(iter(req), "") if isinstance(req, dict) else ""
        if key == "csr":
            return self.csr_response()
        if key == "lock":
            try:
                self.save_creds(req["lock"] or {})
            except Exception as e:
                log(self.st.logpath, "LOCK: разбор не удался", repr(e))
        elif key == "wlan":
            self.st["wlan"] = req["wlan"]
            log(self.st.logpath, "MWS-CONFIG получили, сетей:", len(req["wlan"] or []))
            try:
                self.wifi.maybe_apply([{"mws": req}])
            except Exception as e:
                log(self.st.logpath, "WIFI: разбор не удался", repr(e))
        payload = self.template(key)
        if payload is not None:
            log(self.st.logpath, "ответ по шаблону для", key)
            return payload
        if key == "lock":
            if callable(getattr(self, "start_tls", None)):
                threading.Thread(target=self.start_tls, daemon=True).start()
            return {"lock": {"status": [{"status": "message", "code": "5505224"}]}}
        return {"status": [{"status": "ok"}]}

    def csr_response(self):
        """Ответ на POST /rci/mws {"csr":{}}.

        Если существует файл шаблона (csr_file), форма берётся оттуда — так можно
        перебирать конверты без рестарта заглушки.
        Подстановки: %%PEM%% — PEM целиком, %%B64%% — тело без заголовков,
        %%B64NL%% — тело с переводами строк.
        """
        pem = ""
        try:
            pem = open(self.st["csr"], encoding="utf-8").read()
        except Exception as e:
            log(self.st.logpath, "CSR: не прочитать файл", repr(e))
        log(self.st.logpath, "CSR прочитан, байт:", len(pem))
        tpl = self.template("csr")
        if tpl is not None:
            log(self.st.logpath, "CSR -> по шаблону каталога")
            return tpl
        lines = pem.splitlines()
        b64 = "".join(lines[1:-1])
        b64nl = "\n".join(lines[1:-1])

        path = self.st["csr_file"]
        if path:
            try:
                raw = open(path, encoding="utf-8").read()
            except Exception:
                raw = ""
            if raw.strip():
                raw = (raw.replace("%%PEM%%", json.dumps(pem)[1:-1])
                          .replace("%%B64NL%%", json.dumps(b64nl)[1:-1])
                          .replace("%%B64%%", b64))
                try:
                    payload = json.loads(raw)
                    log(self.st.logpath, "CSR -> по шаблону:", path, "байт:", len(str(payload)))
                    return payload
                except Exception as e:
                    log(self.st.logpath, "CSR-шаблон битый:", repr(e))

        fmt = self.st["csr_format"]
        ok = [{"status": "ok"}]
        if fmt in ("keenetic", "", None, "nested", "ident"):   # the one NDMS 5.x accepts (found in libndmMwsController)
            log(self.st.logpath, "CSR -> контроллеру, байт:", len(pem))
            return {"csr": {"status": [{"status": "message", "code": "5505124"}], "csr": pem}}
        if fmt == "raw":
            payload = {"csr": pem}
        elif fmt == "b64":
            payload = {"csr": b64}
        elif fmt == "flat":
            payload = {"csr": {"pem": pem}, "status": ok}
        elif fmt == "data":
            payload = {"csr": {"status": ok, "data": pem}}
        elif fmt == "request":
            payload = {"csr": {"status": ok, "request": pem}}
        elif fmt == "statusobj":
            payload = {"csr": {"status": {"status": "ok"}, "pem": pem}}
        elif fmt == "nested_csr":
            payload = {"csr": {"status": ok, "csr": {"pem": pem}}}
        elif fmt == "strstatus":
            payload = {"csr": {"status": ["ok"], "pem": pem}}
        elif fmt == "ident":
            payload = {"csr": {"status": [{"status": "ok", "ident": "Mws::Member::Csr"}], "pem": pem}}
        else:
            payload = {"csr": {"status": ok, "pem": pem}}
        log(self.st.logpath, "CSR -> контроллеру, формат:", fmt, "байт:", len(str(payload)))
        return payload

    def get(self, path):
        p = norm_path(path)
        if p in ("", "rci"):
            return 200, {"status": [{"status": "ok"}]}
        if p == "auth":
            return 200, {"status": "ok"}
        routes = {
            "rci/show/version": self.r_version,
            "rci/show/identification": self.r_identification,
            "rci/show/system": self.r_system,
            "rci/show/system/mode": self.r_system_mode,
            "rci/show/interface": self.r_interface,
            "rci/show/last-change": self.r_last_change,
            "rci/show/components": lambda: {},
            "rci/components": self.r_components,
            "rci/components/list": self.r_components_list,
            "rci/show/ip/neighbour": lambda: {},
            "rci/show/ip/hotspot": lambda: {"host": []},
            "rci/show/ip/dhcp": lambda: {},
            "rci/show/mws": self.r_mws,
            "rci/show/mws/associations": lambda: self.r_mws()["associations"],
            "rci/show/mws/wireless-stations": lambda: self.r_mws()["wireless-stations"],
            "rci/show/mws/wired-links": lambda: self.r_mws()["wired-links"],
            "rci/show/mws/controller": lambda: self.r_mws()["controller"],
            "rci/user": lambda: {"user": [{"name": "admin", "tag": "cli"}]},
            "rci/show/components/status": self.r_components_status,
            "rci/mws": lambda: self.st["wlan"] or {},
            "ndmConstants.json": lambda: constants(),
            "rci/probe": lambda: {"status": [{"status": "ok"}]},
        }
        fn = routes.get(p)
        if fn is None:
            return 404, None
        return 200, fn()

    def _delayed_reboot(self):
        """The controller cycles POST /rci/system/reboot after lock and waits for the node to go away and come back once,
        then it sends the Wi-Fi config. We exit the process (all sockets drop → controller sees it gone) and procd respawns
        it in a few seconds; on respawn the saved cert is loaded and HTTPS comes back. A real router reboot would loop
        (too slow — the controller re-asks before the node is back), so we exit instead of rebooting."""
        time.sleep(4)
        log(self.st.logpath, "перезапуск службы по просьбе контроллера (procd поднимет заново)")
        os._exit(0)

    def _delayed_restart(self):
        time.sleep(3)
        log(self.st.logpath, "перезапуск службы после factory-reset")
        os._exit(0)

    def is_down(self):
        """Эмуляция перезагрузки (не используется: узел перезагружается по-настоящему)."""
        now = time.time()
        if DOWN_UNTIL[0] and now >= DOWN_UNTIL[0]:
            DOWN_UNTIL[0] = 0
            self.started = now        # после «загрузки» uptime с нуля
            log(self.st.logpath, "узел снова в сети после перезагрузки")
        return now < DOWN_UNTIL[0]

    def post(self, path, body, headers):
        p = norm_path(path)
        try:
            req = json.loads(body or "{}")
        except Exception:
            req = {}
        if p == "auth":
            return 200, {"status": "ok"}
        if p in ("rci/system/factory-reset", "rci/system/factory_reset"):
            log(self.st.logpath, "контроллер просит factory-reset — чищу MWS-состояние")
            self.st["wifi_digest"] = None
            for f in (self.st["cert_path"], self.st["ca_path"]):
                try:
                    os.unlink(f)
                except OSError:
                    pass
            self.st["creds"] = {}
            threading.Thread(target=self._delayed_restart, daemon=True).start()
            return 200, {"status": [{"status": "message", "code": "5505124",
                                     "ident": "Core::Configurator",
                                     "message": "factory reset accepted"}]}
        if p == "rci/system/reboot":
            self.reboot_count = getattr(self, "reboot_count", 0) + 1
            log(self.st.logpath, "REBOOT просят (раз %d) — выхожу, procd поднимет заново" % self.reboot_count)
            if not getattr(self, "_reboot_planned", False):
                self._reboot_planned = True
                threading.Thread(target=self._delayed_reboot, daemon=True).start()
            return 200, {"status": [{"status": "message", "code": "5505124",
                                     "ident": "Mws::Member::Reboot",
                                     "message": "rebooting"}]}
        if p == "rci/mws":
            return 200, self.mws_response(req)
        if p in ("rci/show/interface",):
            return 200, self.r_interface()
        if p == "rci/components/list":
            # настоящие узлы отвечают маркером продолжения, данные идут следующим запросом
            return 200, {"continued": False}
        if p == "rci/interface/components/check-update":
            return 200, {"status": [{"status": "ok"}]}
        if p in ("rci/components/commit", "rci/interface/components/commit"):
            return 200, {"status": [{"status": "ok"}]}
        if p in ("rci", ""):
            self.counter += 1
            if isinstance(req, list):           # a config batch from the controller
                try:
                    self.wifi.maybe_apply(req)
                except Exception as e:
                    log(self.st.logpath, "WIFI: разбор не удался", repr(e))
            resp = self.handle(req)
            log(self.st.logpath, f"<<< ответ #{self.counter}",
                json.dumps(resp, ensure_ascii=False)[:900])
            return 200, resp
        # прочие POST — тоже RCI-запрос
        resp = self.handle(req)
        log(self.st.logpath, f"<<< ответ (POST /{p})", json.dumps(resp, ensure_ascii=False)[:600])
        return 200, resp


# ---------------------------------------------------------------- HTTP-сервер
class HttpServer(threading.Thread):
    def __init__(self, rci, port, logpath):
        super().__init__(daemon=True)
        self.rci = rci
        self.port = port
        self.logpath = logpath
        self.context = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", port))
        self.sock.listen(32)

    def set_tls(self, certfile, keyfile):
        import ssl as _ssl
        ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        self.context = ctx

    def run(self):
        while True:
            try:
                conn, addr = self.sock.accept()
            except OSError:
                return
            try:
                if self.context is not None:
                    conn = self.context.wrap_socket(conn, server_side=True)
                self.handle(conn, addr)
            except Exception as e:
                log(self.logpath, "HTTP !", repr(e))
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def handle(self, conn, addr):
        if self.rci.is_down():
            # узел «перезагружается» — соединения не обслуживаем
            return
        conn.settimeout(10)
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(8192)
            if not chunk:
                return
            data += chunk
        head, _, rest = data.partition(b"\r\n\r\n")
        lines = head.decode("utf-8", "replace").split("\r\n")
        method, path, _ = (lines[0].split(" ") + ["", ""])[:3]
        headers = {}
        for ln in lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        length = int(headers.get("content-length", "0") or 0)
        body = rest
        while len(body) < length:
            chunk = conn.recv(8192)
            if not chunk:
                break
            body += chunk
        body_text = body[:length].decode("utf-8", "replace")

        log(self.logpath, f">>> {method} /{path.lstrip('/')} from {addr[0]} token={headers.get('x-ndm-token','-')}"
            + (f" body={body_text[:600]}" if body_text else ""))

        if method == "POST":
            code, payload = self.rci.post(path, body_text, headers)
        else:
            code, payload = self.rci.get(path)

        if payload is None:
            resp = b"HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\n\r\n"
        else:
            raw = json.dumps(payload, ensure_ascii=False).encode()
            resp = (b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n"
                    + f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
        conn.sendall(resp)


# ---------------------------------------------------------------- WS-Discovery
class Wsd(threading.Thread):
    """WS-Discovery: Hello (из порта 3702, как у настоящих узлов) + ответы на Probe/Resolve."""

    def __init__(self, st, iface_ip, port, logpath):
        super().__init__(daemon=True)
        self.st = st
        self.iface_ip = iface_ip
        self.port = port
        self.logpath = logpath
        self.instance = int(time.time()) % 100000
        self.msg = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_REUSEPORT", 1), 1)
        except OSError:
            pass
        try:
            self.sock.bind(("", WSD_PORT))
        except OSError as e:
            log(self.logpath, f"WSD: не смог занять :{WSD_PORT} ({e}) — работаю без приёма Probe")
        try:
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                 struct.pack("4s4s", socket.inet_aton(WSD_GROUP),
                                             socket.inet_aton(iface_ip)))
        except OSError:
            pass
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        try:
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                 socket.inet_aton(iface_ip))
        except OSError:
            pass

    def scopes(self):
        st, d = self.st, self.st["domain"]
        return " ".join([
            f"mws://mws.ndm.{d}/mac/{(st['mac'] or '').lower()}",
            f"mws://mws.ndm.{d}/mode/extender",
            f"mws://mws.ndm.{d}/http-port/{self.port}",
            f"mws://mws.ndm.{d}/fw-id/{st['fw_id']}",
            f"mws://mws.ndm.{d}/fw-version/{st['fw_release']}",
            f"mws://mws.ndm.{d}/cid/{st['cid']}",
            f"mws://mws.ndm.{d}/default-domain/{st['fqdn']}",
            f"mws://mws.ndm.{d}/region/{st['region']}",
        ])

    def _envelope(self, action, body, relates=None):
        head = (
            "<soap:Header>"
            f"<wsa:Action>{action}</wsa:Action>"
            f"<wsa:MessageID>urn:uuid:{_uuid4()}</wsa:MessageID>"
            + (f"<wsa:RelatesTo>{relates}</wsa:RelatesTo>" if relates else "")
            + "<wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>"
            f'<wsd:AppSequence InstanceId="{self.instance}" MessageNumber="{self.msg}" />'
            "</soap:Header>"
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<soap:Envelope xmlns:wsa="{NS["wsa"]}" xmlns:soap="{NS["soap"]}" xmlns:wsd="{NS["wsd"]}">'
            + head + "<soap:Body>" + body + "</soap:Body></soap:Envelope>"
        ).encode()

    def hello(self):
        if time.time() < DOWN_UNTIL[0]:
            return          # узел «перезагружается» — Hello не рассылаем
        self.msg += 1
        body = (
            "<wsd:Hello>"
            f"<wsa:EndpointReference><wsa:Address>urn:uuid:{self.st['cid']}</wsa:Address></wsa:EndpointReference>"
            "<wsd:MetadataVersion>1</wsd:MetadataVersion>"
            f"<wsd:Scopes> {self.scopes()}</wsd:Scopes>"
            "</wsd:Hello>"
        )
        pkt = self._envelope("http://schemas.xmlsoap.org/ws/2005/04/discovery/Hello", body)
        try:
            self.sock.sendto(pkt, WSD_ADDR)
            log(self.logpath, f"WSD Hello #{self.msg} -> {WSD_ADDR[0]}:{WSD_ADDR[1]} ({len(pkt)} байт)")
        except OSError as e:
            log(self.logpath, "WSD Hello ошибка:", repr(e))

    def _match(self, kind, relates):
        self.msg += 1
        match = (
            f"<wsd:{kind}><wsd:ProbeMatch>"
            f"<wsa:EndpointReference><wsa:Address>urn:uuid:{self.st['cid']}</wsa:Address></wsa:EndpointReference>"
            f"<wsd:Scopes> {self.scopes()}</wsd:Scopes>"
            f"<wsd:XAddrs>http://{self.iface_ip}:{self.port}/</wsd:XAddrs>"
            "<wsd:MetadataVersion>1</wsd:MetadataVersion>"
            "</wsd:ProbeMatch></wsd:ProbeMatches>"
        ) if kind == "ProbeMatches" else (
            f"<wsd:ResolveMatches><wsd:ResolveMatch>"
            f"<wsa:EndpointReference><wsa:Address>urn:uuid:{self.st['cid']}</wsa:Address></wsa:EndpointReference>"
            f"<wsd:Scopes> {self.scopes()}</wsd:Scopes>"
            f"<wsd:XAddrs>http://{self.iface_ip}:{self.port}/</wsd:XAddrs>"
            "<wsd:MetadataVersion>1</wsd:MetadataVersion>"
            "</wsd:ResolveMatch></wsd:ResolveMatches>"
        )
        return self._envelope(
            f"http://schemas.xmlsoap.org/ws/2005/04/discovery/{kind}", match, relates)

    def run(self):
        self.hello()
        next_hello = time.time() + 60
        self.sock.settimeout(1.0)
        while True:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                data, addr = None, None
            except OSError:
                data, addr = None, None
            if data:
                text = data.decode("utf-8", "replace")
                action = ""
                m = re.search(r"<wsa:Action>([^<]+)</wsa:Action>", text)
                if m:
                    action = m.group(1)
                mid = ""
                m2 = re.search(r"<wsa:MessageID>([^<]+)</wsa:MessageID>", text)
                if m2:
                    mid = m2.group(1)
                if addr and addr[0] != self.iface_ip:
                    log(self.logpath, f"WSD <- {addr[0]}:{addr[1]} {action.split('/')[-1]} ({len(data)} б)")
                try:
                    if action.endswith("/Probe"):
                        self.sock.sendto(self._match("ProbeMatches", mid), addr)
                        log(self.logpath, f"WSD -> ProbeMatches {addr[0]}")
                    elif action.endswith("/Resolve"):
                        self.sock.sendto(self._match("ResolveMatches", mid), addr)
                        log(self.logpath, f"WSD -> ResolveMatches {addr[0]}")
                except OSError as e:
                    log(self.logpath, "WSD ответ ошибка:", repr(e))
            if time.time() >= next_hello:
                self.hello()
                next_hello = time.time() + 60


def local_ip(iface):
    try:
        out = os.popen(f"ip -4 addr show dev {iface}").read()
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                return line.split()[1].split("/")[0]
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def iface_mac(iface):
    try:
        return open(f"/sys/class/net/{iface}/address").read().strip()
    except Exception:
        return "02:00:00:00:00:01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", default="br-lan")
    ap.add_argument("--mac", default="", help="MAC узла (по умолчанию — MAC интерфейса)")
    ap.add_argument("--ip", default="", help="IP узла (по умолчанию — адрес интерфейса)")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--log", default="/tmp/mws.log")
    ap.add_argument("--dir", default="/etc/mws", help="ключ, CSR, сертификаты, состояние")
    ap.add_argument("--state", default="")
    ap.add_argument("--csr", default="", help="путь к файлу CSR")
    ap.add_argument("--csr-file", default="", help="JSON-шаблон ответа на запрос CSR")
    ap.add_argument("--csr-format", default="", choices=["", "keenetic", "raw", "b64", "nested", "flat", "data", "request", "statusobj", "nested_csr", "strstatus", "ident"])
    ap.add_argument("--tls-port", type=int, default=443, help="HTTPS-порт для члена системы")
    ap.add_argument("--cert", default="")
    ap.add_argument("--ca", default="")
    ap.add_argument("--key", default="")
    ap.add_argument("--hw-id", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--fw", default="")
    ap.add_argument("--fw-release", default="")
    ap.add_argument("--fw-id", default="")
    ap.add_argument("--domain", default="")
    ap.add_argument("--hostname", default="")
    args = ap.parse_args()
    d = args.dir
    os.makedirs(d, exist_ok=True)
    key, csr = args.key or d + "/key.pem", args.csr or d + "/csr.pem"
    cert, ca = args.cert or d + "/cert.pem", args.ca or d + "/ca.pem"

    ip = args.ip or local_ip(args.iface)
    mac = args.mac or iface_mac(args.iface)
    st = State(args.state or d + "/state.json", mac=mac, port=args.port, hw_id=args.hw_id, model=args.model,
               fw=args.fw, fw_release=args.fw_release, fw_id=args.fw_id,
               domain=args.domain, hostname=args.hostname, csr=csr, csr_format=args.csr_format,
               csr_file=args.csr_file, cert_path=cert, ca_path=ca, resp_dir=d + "/resp")
    st.logpath = args.log
    ensure_identity(key, csr, st["cid"], args.log)
    log(args.log, f"старт: iface={args.iface} ip={ip} mac={mac} cid={st['cid']} port={args.port}")
    log(args.log, f"identity: model={st['model']} hw_id={st['hw_id']} fw={st['fw']} region={st['region']}")

    rci = Rci(st)
    HttpServer(rci, args.port, args.log).start()
    log(args.log, f"HTTP RCI слушает 0.0.0.0:{args.port}")
    tls = {"on": False}

    def start_tls():                    # at start if already a member, or right after the controller hands out the certificate (lock)
        if tls["on"] or not args.tls_port:
            return
        for _ in range(20):
            if os.path.exists(cert) and os.path.exists(key):
                break
            time.sleep(0.5)
        else:
            log(args.log, "HTTPS: нет сертификата или ключа", cert, key)
            return
        try:
            srv = HttpServer(rci, args.tls_port, args.log)
            srv.set_tls(cert, key)
            srv.start()
            tls["on"] = True
            log(args.log, f"HTTPS RCI слушает 0.0.0.0:{args.tls_port}")
        except Exception as e:
            log(args.log, "HTTPS: не поднять", repr(e))

    rci.start_tls = start_tls
    if os.path.exists(cert):
        start_tls()
    Wsd(st, ip, args.port, args.log).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
