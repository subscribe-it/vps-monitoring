"""Minimalny klient S3 (tylko odczyt) z podpisem AWS SigV4 — wyłącznie stdlib.

Potrzebny do jednej rzeczy: sprawdzić, czy w buckecie R2 faktycznie leży świeży
backup i jak duży jest. Wcześniej watchdog czytał tylko logi usługi backupu, co
nie odpowiada na pytanie „czy kopia dotarła na miejsce".

Podpis liczy się dokładnie tak, jak opisuje specyfikacja AWS SigV4; poprawność
jest weryfikowana testem przeciwko prawdziwemu serwerowi zgodnemu z S3 (MinIO),
bo tylko serwer może potwierdzić, że podpis jest prawidłowy.
"""

import datetime
import hashlib
import hmac
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ALGORYTM = "AWS4-HMAC-SHA256"
BEZ_TRESCI = hashlib.sha256(b"").hexdigest()


def _hmac(klucz, dane):
    return hmac.new(klucz, dane.encode("utf-8"), hashlib.sha256).digest()


def klucz_podpisujacy(sekret, data, region, usluga):
    k = _hmac(("AWS4" + sekret).encode("utf-8"), data)
    k = _hmac(k, region)
    k = _hmac(k, usluga)
    return _hmac(k, "aws4_request")


def _kanoniczny_uri(sciezka):
    # S3 wymaga, by każdy segment był zakodowany, ale ukośniki zostały ukośnikami.
    return "/".join(urllib.parse.quote(segment, safe="") for segment in sciezka.split("/"))


def podpisz_get(url, region, usluga, access_key, secret_key, moment=None):
    """Zwraca słownik nagłówków z podpisem dla żądania GET bez treści."""
    moment = moment or datetime.datetime.now(datetime.timezone.utc)
    znacznik = moment.strftime("%Y%m%dT%H%M%SZ")
    data = moment.strftime("%Y%m%d")

    czesci = urllib.parse.urlsplit(url)
    pary = urllib.parse.parse_qsl(czesci.query, keep_blank_values=True)
    kanoniczne_query = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
        for k, v in sorted(pary)
    )

    # UWAGA: wszystkie nagłówki, które trafiają do SignedHeaders, MUSZĄ być
    # obecne już w żądaniu kanonicznym. Dołożenie ich później (częsty błąd)
    # daje podpis, którego serwer nie może odtworzyć → 403 SignatureDoesNotMatch.
    naglowki = {
        "host": czesci.netloc,
        "x-amz-content-sha256": BEZ_TRESCI,
        "x-amz-date": znacznik,
    }
    podpisane_naglowki = ";".join(sorted(naglowki))
    kanoniczne_naglowki = "".join(f"{k}:{naglowki[k]}\n" for k in sorted(naglowki))

    kanoniczne_zadanie = "\n".join([
        "GET",
        _kanoniczny_uri(czesci.path),
        kanoniczne_query,
        kanoniczne_naglowki,
        podpisane_naglowki,
        BEZ_TRESCI,
    ])

    zakres = f"{data}/{region}/{usluga}/aws4_request"
    do_podpisu = "\n".join([
        ALGORYTM,
        znacznik,
        zakres,
        hashlib.sha256(kanoniczne_zadanie.encode("utf-8")).hexdigest(),
    ])
    podpis = hmac.new(klucz_podpisujacy(secret_key, data, region, usluga),
                      do_podpisu.encode("utf-8"), hashlib.sha256).hexdigest()

    naglowki["Authorization"] = (
        f"{ALGORYTM} Credential={access_key}/{zakres}, "
        f"SignedHeaders={podpisane_naglowki}, Signature={podpis}"
    )
    return naglowki


def listuj_obiekty(endpoint, bucket, prefix, access_key, secret_key, region="auto", timeout=20):
    """ListObjectsV2. Zwraca listę słowników {key, size, last_modified}."""
    baza = endpoint.rstrip("/")
    if not baza.startswith("http"):
        baza = "https://" + baza
    query = urllib.parse.urlencode({"list-type": "2", "prefix": prefix or "", "max-keys": "1000"})
    url = f"{baza}/{bucket}?{query}"

    naglowki = podpisz_get(url, region, "s3", access_key, secret_key)
    zadanie = urllib.request.Request(url, headers=naglowki, method="GET")
    with urllib.request.urlopen(zadanie, timeout=timeout) as odpowiedz:
        tresc = odpowiedz.read()

    obiekty = []
    korzen = ET.fromstring(tresc)
    for wpis in korzen.iter():
        if not wpis.tag.endswith("Contents"):
            continue
        dane = {p.tag.split("}")[-1]: (p.text or "") for p in wpis}
        klucz = dane.get("Key", "")
        if not klucz or klucz.endswith("/"):
            continue
        try:
            rozmiar = int(dane.get("Size") or 0)
        except ValueError:
            rozmiar = 0
        data = None
        surowa = dane.get("LastModified")
        if surowa:
            try:
                data = datetime.datetime.fromisoformat(surowa.replace("Z", "+00:00"))
            except ValueError:
                data = None
        obiekty.append({"key": klucz, "size": rozmiar, "last_modified": data})
    return obiekty
