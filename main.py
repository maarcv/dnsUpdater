#!/usr/bin/env python3
import os
import sys
import requests
from typing import Optional, Tuple

# SOAP client (zeep)
from zeep import Client
from zeep.transports import Transport
import requests as r

WSDL_URL = "https://api.servidoresdns.net:54321/hosting/api/soap/index.php?wsdl"

def get_env(name: str) -> str:
    if name == "ARSYS_LOGIN":
        return "espaiartesania.cat"
    elif name == "ARSYS_API_KEY":
        return  "Rp6Jp0FT7zJmiI1ip9BxXBS5a"
    elif name == "ARSYS_DOMAIN":
        return "espaiartesania.cat"
    elif name == "ARSYS_DNS":
        return "espaiartesania.cat"


    val = os.environ.get(name)
    if not val:
        print(f"[ERROR] Falta la variable d'entorn: {name}", file=sys.stderr)
        sys.exit(1)
    return val

def get_public_ip(timeout: int = 5) -> str:
    # Fonts redundants
    urls = [
        "https://api64.ipify.org",
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ipinfo.io/ip",
    ]
    for u in urls:
        try:
            ip = requests.get(u, timeout=timeout).text.strip()
            # Validació bàsica
            if ip and len(ip) < 64 and all(ch in "0123456789abcdefABCDEF:." for ch in ip):
                return ip
        except requests.RequestException:
            continue
    raise RuntimeError("No s'ha pogut obtenir la IP pública des de cap servei.")

def build_arsys_client(login: str, api_key: str) -> Client:
    session = r.Session()
    session.auth = (login, api_key)  # Basic Auth
    # timeouts raonables
    transport = Transport(session=session, timeout=30)
    return Client(wsdl=WSDL_URL, transport=transport)

def find_current_a_value(client: Client, domain: str, dns_name: str) -> Optional[str]:
    """
    Torna el 'value' actual del registre A per a dns_name, o None si no existeix.
    """
    try:
        # Segons el WSDL, els mètodes accepten un paràmetre 'input' amb els camps
        resp = client.service.InfoDNSZone(input={
            "domain": domain,
            "dns": dns_name,
            "type": "A",
            "value": ""
        })
    except Exception as e:
        raise RuntimeError(f"Error cridant InfoDNSZone: {e}")

    # La resposta té: errorCode, errorMsg i res (que conté status i data[])
    if resp is None:
        return None

    if getattr(resp, "errorCode", 0) != 0:
        msg = getattr(resp, "errorMsg", "Error desconegut")
        raise RuntimeError(f"InfoDNSZone ha retornat errorCode={resp.errorCode}: {msg}")

    data = getattr(resp, "res", None)
    if not data:
        return None

    items = getattr(data, "data", None)
    if not items:
        return None

    # Busca el primer registre A exactament per aquest nom
    for item in items:
        if getattr(item, "type", "") == "A" and getattr(item, "name", "") == dns_name:
            return getattr(item, "value", None)
    return None

def create_a_record(client: Client, domain: str, dns_name: str, value: str) -> None:
    try:
        resp = client.service.CreateDNSEntry(input={
            "domain": domain,
            "dns": dns_name,
            "type": "A",
            "value": value
        })
    except Exception as e:
        raise RuntimeError(f"Error cridant CreateDNSEntry: {e}")

    if resp is None or getattr(resp, "errorCode", 0) != 0 or getattr(resp, "res", False) is not True:
        code = getattr(resp, "errorCode", "??")
        msg = getattr(resp, "errorMsg", "Error desconegut")
        raise RuntimeError(f"CreateDNSEntry ha fallat: errorCode={code}, errorMsg={msg}")

def modify_a_record(client: Client, domain: str, dns_name: str, current_value: str, new_value: str) -> None:
    try:
        resp = client.service.ModifyDNSEntry(input={
            "domain": domain,
            "dns": dns_name,
            "currenttype": "A",
            "currentvalue": current_value,
            "newtype": "A",
            "newvalue": new_value
        })
    except Exception as e:
        raise RuntimeError(f"Error cridant ModifyDNSEntry: {e}")

    if resp is None or getattr(resp, "errorCode", 0) != 0 or getattr(resp, "res", False) is not True:
        code = getattr(resp, "errorCode", "??")
        msg = getattr(resp, "errorMsg", "Error desconegut")
        raise RuntimeError(f"ModifyDNSEntry ha fallat: errorCode={code}, errorMsg={msg}")

def main():
    login = get_env("ARSYS_LOGIN")
    api_key = get_env("ARSYS_API_KEY")
    domain = get_env("ARSYS_DOMAIN")
    dns_name = get_env("ARSYS_DNS")

    print("[*] Recuperant IP pública…")
    public_ip = get_public_ip()
    print(f"    IP pública actual: {public_ip}")

    print("[*] Connectant amb l'API d'Arsys…")
    client = build_arsys_client(login, api_key)

    print(f"[*] Comprovant registre A existent per a {dns_name} a la zona de {domain}…")
    current = find_current_a_value(client, domain, dns_name)
    if current is None:
        print("    No existeix el registre A. Es crearà.")
        create_a_record(client, domain, dns_name, public_ip)
        print(f"[OK] Creat {dns_name} A {public_ip}")
    elif current == public_ip:
        print(f"[OK] Sense canvis: {dns_name} ja apunta a {public_ip}")
    else:
        print(f"    Canvi detectat: {dns_name} A {current} -> {public_ip}")
        modify_a_record(client, domain, dns_name, current, public_ip)
        print(f"[OK] Actualitzat {dns_name} A {public_ip}")

    print("Nota: la propagació DNS pot trigar uns minuts.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        sys.exit(2)
