#!/usr/bin/env python
"""
Saca el precio REAL de cada país entrando al checkout y cambiando el país ahí dentro.

Por qué así y no de otra forma: Hotmart resuelve el país por la IP del servidor y no
acepta parámetros, cabeceras ni cookies para cambiarlo. Pero el checkout tiene un botón
"Cambiar país" que hace justamente eso. Se abre el checkout en un navegador real, se
recorre la lista de países y se lee el importe que muestra en cada uno.

Hotmart reconvierte al tipo de cambio del día, así que esto hay que correrlo a diario.
El resultado se sube a R2 y el worker lo lee para decirle a cada lead el precio de SU
país, que es el que va a ver al entrar.

Cobertura: el selector de país de Hotmart ofrece ~219 países (verificado 22/08/2026),
no los 19 que estaban escritos a mano. La lista se descubre SOLA leyendo el propio
checkout (no hay que tocar código si Hotmart agrega o saca un país) y se cachea en
analisis/paises_hotmart.json. No entran todos en una corrida: cada una arranca donde
quedó la anterior (state/precios_cursor.json) y completa la tabla existente en vez de
reemplazarla, así que la cobertura total crece de a poco entre corridas sin perder
nunca un país por no llegar a re-leerlo ese día. Los 22 países de siempre (Argentina,
México, etc.) mantienen el mismo nombre en español de toda la vida; los ~185 nuevos
quedan con su nombre en INGLÉS (Hotmart no da uno en español para todos), así que
--paises usa ese idioma para los que no estaban antes (ej: "Germany", no "Alemania").

Uso:
    python sync_precios.py                          # todos los países, sube a R2
    python sync_precios.py --sin-subir              # solo scrapea, no toca R2
    python sync_precios.py --paises Ecuador,Germany # chequeo rápido de unos pocos
    python sync_precios.py --limite 4               # los primeros 4 de la lista (según cursor)

Códigos de salida (los mira la Tarea Programada de Windows):
    0  al menos la mitad de los países INTENTADOS esta corrida salieron bien, y subido a R2
    1  no se leyó NINGÚN precio (el scrapeo falló entero)
    2  de lo intentado ESTA corrida salió muy poco (menos de la mitad): revisar
    3  se scrapeó bien pero NO se pudo subir a R2 (el lead sigue viendo lo viejo)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import phonenumbers

ROOT = Path(__file__).resolve().parent
# En GitHub Actions no está la carpeta del Worker: wrangler toma el token del entorno.
WDIR = ROOT / "cloudflare-worker" if (ROOT / "cloudflare-worker").is_dir() else ROOT
LOG = ROOT / "logs" / "precios.log"
ESTADO = ROOT / "analisis" / "precios_checkout_estado.json"
# Los 219 países que ofrece HOY el checkout de Hotmart (iso/nombre en inglés/nombre
# local), leídos en vivo del selector. Antes solo se cubrían 22 escritos a mano (19
# efectivos, ver SIN_HOTMART) — un lead de Alemania, India o cualquiera de los otros
# ~190 países se cotizaba a ciegas en USD genérico. Se cachea acá para no depender de
# tener el navegador abierto para construir PREFIJO/MONEDA al importar el módulo.
CACHE_PAISES = ROOT / "analisis" / "paises_hotmart.json"

# La salida estándar de la Tarea Programada es cp1252 y reventaba con el símbolo del
# colón de Costa Rica (₡): UnicodeEncodeError DENTRO del print, el proceso moría en el
# país 12 de 22 y nunca llegaba a escribir el JSON ni a subirlo a R2. Por eso la tabla
# quedó congelada días entre corridas "exitosas". Con utf-8 + errors=replace un símbolo
# raro ya no puede cortar la corrida: en el peor caso se ve un carácter feo en el log.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass   # pythonw.exe no tiene stdout: no hay nada que reconfigurar

# pythonw.exe (con el que la Tarea Programada lanza esto) no tiene consola: los print()
# se pierden en el vacío y la corrida no dejaba UNA SOLA línea de rastro, por eso nadie
# se enteró de que hacía días que no actualizaba. Cuando no hay consola se escribe a
# logs/precios.log. Solo en ese caso: run_precios.bat ya redirige stdout a ese mismo
# archivo, y escribir siempre dejaba cada línea duplicada.
_SIN_CONSOLA = sys.stdout is None


def _log(msg: str = "") -> None:
    """print de siempre, o línea con fecha en logs/precios.log si no hay consola."""
    if not _SIN_CONSOLA:
        print(msg)
        return
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8", errors="replace") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except Exception:
        pass   # que no se pueda loguear no puede ser motivo para perder el scrapeo


def _nicho() -> str:
    """Nicho activo. OJO con os.getenv("NICHE", "hidroponia"): el default NO se usa
    cuando la variable EXISTE pero está VACÍA (NICHE= en el .env). load_niche("")
    revienta, el except de abajo se lo come y la corrida termina sin URL de checkout
    ("sin URL de checkout: revisar cta_link del nicho") sin que se entienda por qué.
    Con `or`, una variable vacía o con espacios se comporta igual que no tenerla."""
    import os
    return (os.getenv("NICHE") or "").strip() or "hidroponia"


def _cfg() -> tuple[str, str]:
    """(checkout, bucket) desde la configuración del usuario: el checkout sale del
    NICHO (cta_link) y el bucket de las credenciales. Así cada uno scrapea SUS precios
    y los sube a SU R2, sin tocar código. Si algo falta, se usan los valores de acá."""
    checkout, bucket = "", "marketing-reels"
    try:
        import config
        checkout = config.load_niche(_nicho()).cta_link or ""
        bucket = config.load_secrets().r2_bucket or bucket
    except Exception:
        pass
    return checkout, bucket


CHECKOUT_CFG, BUCKET = _cfg()


def nichos_con_checkout() -> list:
    """(nicho, checkout, clave de R2) de CADA nicho que tenga un checkout de Hotmart.

    Por qué recorre todos y no solo el activo: los precios por país solo se pueden leer
    ADENTRO del checkout, y Eugenia cotiza para los dos productos. Scrapeando uno solo,
    al lead de bonsái se le terminaba diciendo el precio de hidroponía.

    Usa `cta_checkout` y NO `cta_link`: desde que existe el switch landing/checkout, un
    nicho puede estar apuntando a la landing y aun así necesitar que le scrapeemos SU
    checkout. Si el nicho es viejo y solo tiene `cta_link`, se usa ese cuando es de Hotmart.

    Hidroponía conserva la clave histórica `wa/precios_pais.json` porque es la que lee el
    Worker hoy: renombrarla lo dejaría sin precios hasta el próximo deploy.
    """
    salida = []
    try:
        import config
    except Exception as e:  # noqa: BLE001
        _log(f"no se pudo importar config: {str(e)[:120]}")
        return salida
    for y in sorted((ROOT / "niches").glob("*.yaml")):
        nombre = y.stem
        try:
            n = config.load_niche(nombre)
        except Exception as e:  # noqa: BLE001
            _log(f"nicho '{nombre}': no se pudo leer ({str(e)[:90]})")
            continue
        url = (getattr(n, "cta_checkout", "") or "").strip()
        if not url and "hotmart" in (getattr(n, "cta_link", "") or "").lower():
            url = (n.cta_link or "").strip()
        if not url:
            _log(f"nicho '{nombre}': sin checkout cargado — no se scrapea")
            continue
        if "hotmart" not in url.lower():
            _log(f"nicho '{nombre}': el checkout no es de Hotmart — no se scrapea")
            continue
        clave = ("wa/precios_pais.json" if nombre == "hidroponia"
                 else f"wa/precios_pais_{nombre}.json")
        salida.append((nombre, url, clave))
    return salida


# Cursos que se venden con página propia pero NO son un nicho de Eugenia (no tienen
# niches/*.yaml: no publican reels ni tienen chat). Solo necesitan su tabla de precios
# para que la página muestre el precio en la moneda del visitante.
# Ver analisis/PRECIO_EN_PAGINAS.md.
PRODUCTOS_EXTRA = {
    "herbologia": "https://pay.hotmart.com/S98066991C?checkoutMode=10",
    "terrarios": "https://pay.hotmart.com/J106100032L?checkoutMode=10",
}
# Minutos por corrida para CADA extra. Van DESPUÉS de los nichos y con su propio tope:
# no le sacan ni un minuto a hidroponía ni a bonsái, que son los que cotiza el chat.
MIN_POR_EXTRA = 8


def productos_extra() -> list:
    """(nombre, checkout, clave de R2) de los cursos de PRODUCTOS_EXTRA.

    Desde el 14/11 herbologia y terrarios TAMBIÉN tienen niches/*.yaml (nichos en borrador).
    Siguen leyéndose desde acá a propósito: así su tabla no depende de que el yaml cargue
    (un nicho a medio armar no carga) y siguen con su tope aparte. main() saca de la lista
    de nichos a los que figuren acá, para no leerlos dos veces."""
    return [(n, u, f"wa/precios_pais_{n}.json") for n, u in PRODUCTOS_EXTRA.items()]

# Moneda de los países HISTÓRICOS (los 22 que ya se cotizaban a mano). El checkout
# muestra "$444.00" a secas y el lead no sabe si son pesos o dólares: hay que decirle
# la moneda o el precio no significa nada. Para los países NUEVOS (todo lo demás que
# Hotmart ofrece y antes no se leía) no hay tabla: el precio sale igual, sin el sufijo
# de moneda — sigue siendo útil (trae el símbolo tal cual lo muestra Hotmart), solo le
# falta el código de 3 letras de propina.
MONEDA_HISTORICA = {
    "Argentina": "ARS", "México": "MXN", "Chile": "CLP", "Colombia": "COP",
    "Perú": "PEN", "Uruguay": "UYU", "Paraguay": "PYG", "Bolivia": "BOB",
    "Ecuador": "USD", "Venezuela": "USD", "Guatemala": "GTQ", "Costa Rica": "CRC",
    "Panamá": "USD", "Honduras": "HNL", "Nicaragua": "NIO", "El Salvador": "USD",
    "República Dominicana": "DOP", "Puerto Rico": "USD", "Cuba": "USD",
    "España": "EUR", "Estados Unidos": "USD", "Brasil": "BRL",
}

# Los 22 nombres de siempre. Se preservan tal cual (mismo string exacto) para que
# vigilar_precio.py (TESTIGO="Ecuador") y webapp.py sigan andando sin tocarlos: Hotmart
# ofrece "Ecuador" bajo el nombre compuesto "Ikwayur - Ecuador - Ekuatur", así que hace
# falta este mapa para no perder el nombre lindo de siempre.
_NOMBRES_HISTORICOS = list(MONEDA_HISTORICA)

# Nombres donde nuestro string no aparece en NINGÚN campo del selector de Hotmart, ni
# como substring: "Estados Unidos" no comparte ni una palabra con "United States".
_ALIAS_ISO = {"Estados Unidos": "US"}

# Países cuyo código de teléfono lo comparten VARIOS países del selector (+1 en todo
# el Caribe/Norteamérica, +7 en Rusia/Kazajistán, y algunos pares chicos). Sin
# distinguirlos, el segundo País pisaría al primero en la tabla (son claves de un
# mismo dict) y el worker no podría saber a cuál de los dos le está hablando un lead.
#
# Para las ISLAS chicas del Caribe (y Kazajistán) se arma un prefijo COMPUESTO
# (código de país + los primeros dígitos de un número real de esa región), igual al
# truco que ya usaba a mano este archivo para Puerto Rico (1787) y República
# Dominicana (1809) — de hecho, derivado así da EXACTO 1787 y 1809, así que no hace
# falta mantenerlos aparte. Estados Unidos y Canadá se DEJAN con el código desnudo
# ("1"): son países grandes con decenas de códigos de área, no hay UN número que los
# represente, y romper eso perdería la cotización de la enorme mayoría de leads de
# esos dos países. Canadá directamente no entra (nunca se distinguió de EEUU, como
# hoy) y así no le pisa el "1" a Estados Unidos.
_DISAMBIGUAR = ["BS", "BB", "AI", "AG", "VG", "VI", "KY", "BM", "GD", "TC", "MS", "MP",
                "GU", "AS", "LC", "DM", "VC", "TT", "KN", "JM", "PR", "DO", "RU", "KZ"]

# Islas/territorios chicos (población y tráfico esperado ~nulos para este negocio) que
# comparten código con un país grande y NO entran en la lista de arriba: se pierden a
# propósito antes que romper el código del país grande. Sumado Canadá (ver arriba).
_IGNORAR_ISO = {"CA", "VA", "SJ", "CX", "CC", "EH", "YT",
                # sin código de teléfono asignable — no se puede enrutar un WhatsApp:
                "AQ", "AN", "PN", "GS", "UM"}


def _normalizar(s: str) -> str:
    """minusculas, sin acentos, solo letras/numeros — para comparar nombres de país
    sin que una tilde o un guion de más rompa el match."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _prefijo_compuesto(iso: str) -> str | None:
    """código de país + primeros 3 dígitos de un número real de ESA región. Sirve para
    distinguir, dentro de un código compartido, a un país chico del grande que lo
    domina (ver _DISAMBIGUAR)."""
    cc = phonenumbers.country_code_for_region(iso)
    ej = phonenumbers.example_number(iso)
    if not cc or not ej:
        return None
    return f"{cc}{str(ej.national_number)[:3]}"


def construir_paises(crudos: list[dict]) -> tuple[dict, dict, set, dict]:
    """(PREFIJO, MONEDA, SIN_HOTMART, ISO_DE_NOMBRE) a partir de lo que HOY ofrece el
    checkout (`crudos`: [{iso, en, es}], ver descubrir_paises()).

    PREFIJO/MONEDA/SIN_HOTMART quedan con la MISMA forma de siempre ({nombre: valor} /
    {nombre}), así que nada de lo que ya los usa (vigilar_precio.py, webapp.py) se
    entera del cambio. Los ~190 países que Hotmart ofrece y antes no estaban entran
    con su nombre en inglés (no tienen un nombre "de siempre" que preservar).
    """
    idx: dict[str, str] = {}
    for c in crudos:
        for campo in (c.get("es", ""), c.get("en", "")):
            for seg in re.split(r"[|\-–]", campo or ""):
                seg = seg.strip()
                if seg:
                    idx.setdefault(_normalizar(seg), c["iso"])

    def resolver(nombre: str) -> str | None:
        return _ALIAS_ISO.get(nombre) or idx.get(_normalizar(nombre))

    prefijo, moneda, sin_hotmart, iso_de_nombre = {}, {}, set(), {}
    usados_iso = set()

    # 1) Los 22 históricos primero, en su nombre de toda la vida.
    for nombre in _NOMBRES_HISTORICOS:
        iso = resolver(nombre)
        if not iso:
            sin_hotmart.add(nombre)   # Nicaragua y Cuba: no están en el selector
            continue
        pref = _prefijo_compuesto(iso) if iso in _DISAMBIGUAR else str(
            phonenumbers.country_code_for_region(iso) or "")
        if not pref:
            sin_hotmart.add(nombre)
            continue
        prefijo[nombre] = pref
        moneda[nombre] = MONEDA_HISTORICA.get(nombre, "")
        iso_de_nombre[nombre] = iso
        usados_iso.add(iso)

    # 2) Todo lo demás que Hotmart ofrece y no es histórico.
    for c in crudos:
        iso = c["iso"]
        if iso in usados_iso or iso in _IGNORAR_ISO:
            continue
        pref = _prefijo_compuesto(iso) if iso in _DISAMBIGUAR else str(
            phonenumbers.country_code_for_region(iso) or "")
        if not pref:
            continue
        nombre = (c.get("en") or c.get("es") or iso).strip()
        if not nombre or nombre in prefijo:
            continue
        prefijo[nombre] = pref
        iso_de_nombre[nombre] = iso
        usados_iso.add(iso)

    return prefijo, moneda, sin_hotmart, iso_de_nombre


def _cache_leer() -> list[dict]:
    try:
        return json.loads(CACHE_PAISES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _cache_guardar(crudos: list[dict]) -> None:
    try:
        CACHE_PAISES.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PAISES.write_text(json.dumps(crudos, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def descubrir_paises(pg) -> list[dict]:
    """[{iso, en, es}] tal como los ofrece HOY el selector de país del checkout
    (`pg` con el checkout YA abierto). Cada botón del selector ya trae su propio
    código ISO (`iso-code`): no hace falta escribir nada en el buscador ni adivinar
    cómo se llama un país en el checkout, alcanza con leerlos todos de una."""
    btn = pg.query_selector("button[class*=country]")
    if not btn:
        raise RuntimeError("sin botón de país")
    btn.click(timeout=8000)
    pg.wait_for_timeout(1000)
    items = pg.query_selector_all("button.country-select-options")
    out = []
    for it in items:
        iso = (it.get_attribute("iso-code") or "").strip().upper()
        if not iso:
            continue
        en_el = it.query_selector(".country-select__englishName")
        es_el = it.query_selector(".country-select__localName")
        out.append({"iso": iso,
                    "en": (en_el.inner_text().strip() if en_el else ""),
                    "es": (es_el.inner_text().strip() if es_el else "")})
    try:
        pg.keyboard.press("Escape")
    except Exception:  # noqa: BLE001
        pass
    return out


def _paises_de_arranque() -> tuple[dict, dict, set, dict]:
    """Al importar el módulo NO hay navegador abierto: se usa el último descubrimiento
    guardado en disco. Si todavía no existe ninguno (instalación nueva, antes del
    primer scrapeo), se cae a los 19 de siempre para que nada quede roto mientras
    tanto — scrapear() lo reemplaza por la lista completa en cuanto corre una vez."""
    crudos = _cache_leer()
    if crudos:
        return construir_paises(crudos)
    _RESPALDO = {
        "Argentina": "54", "México": "52", "Chile": "56", "Colombia": "57", "Perú": "51",
        "Uruguay": "598", "Paraguay": "595", "Bolivia": "591", "Ecuador": "593",
        "Guatemala": "502", "Costa Rica": "506", "Panamá": "507", "Honduras": "504",
        "El Salvador": "503", "República Dominicana": "1809", "Puerto Rico": "1787",
        "España": "34", "Estados Unidos": "1", "Brasil": "55",
    }
    return dict(_RESPALDO), dict(MONEDA_HISTORICA), {"Venezuela", "Nicaragua", "Cuba"}, {}


PREFIJO, MONEDA, SIN_HOTMART, ISO_DE_NOMBRE = _paises_de_arranque()

# Cada país usa su símbolo: S/ en Perú, ₡ en Costa Rica, Q en Guatemala, Gs en
# Paraguay, RD$ en Dominicana, B/. en Panamá. Sin esto solo se leían los de "$".
# OJO con el \xa0 del separador de miles: Hotmart escribe "₡4<NBSP>782,00" con espacio
# duro, no con espacio común. Si se pierde ese carácter de la clase, el match corta en
# "₡4" y Costa Rica se cae de la tabla sin avisar. Va escrito como escape \xa0 y no como
# el carácter literal justamente para que ningún editor lo normalice a espacio común.
# Además hay dos ÓRDENES distintos. América escribe el símbolo adelante ("$213.44"),
# pero Europa lo escribe DETRÁS: España muestra "Total de 10,00 €". Con sólo el patrón
# de símbolo-adelante, España no matcheaba el total y el scraper agarraba un "€ 80"
# suelto de otra parte de la página -> el validador lo descartaba y el país quedaba
# sin precio. Por eso hay dos alternativas.
_NUM = r"\d{1,3}(?:[.,\xa0 ]\d{3})*(?:[.,]\d{2})?"
_SIMBOLO = r"(?:US\$|RD\$|R\$|B/\.|S/\.?|Gs\.?|Bs\.?|[$€₡Q£L])"
PRECIO = re.compile(rf"{_SIMBOLO}\s?{_NUM}|{_NUM}\s?{_SIMBOLO}")


# Tipos de cambio SOLO para validar, nunca para calcular el precio que se publica.
# Sirven para descartar lecturas absurdas: España llegó a leerse "€ 80" cuando el
# curso son 24 USD, porque el regex agarró el importe de otro elemento.
FX_APROX = {
    "€": 0.92, "S/": 3.7, "Q": 7.8, "₡": 510, "B/.": 1, "Bs": 6.9, "Gs": 7300,
    "RD$": 60, "L": 25, "R$": 5.4,
}

# Rango en USD aceptable para el importe del curso. Antes estaba escrito a mano dentro
# de _plausible; se saca acá porque ahora también lo usan los países de moneda USD.
USD_MIN, USD_MAX = 5, 60


def _a_numero(txt: str) -> tuple[str, float] | None:
    """('símbolo', importe) de un texto tipo 'B/. 12.00'. None si no se puede leer.
    Se separó de _plausible para poder validar también los países que cobran en USD."""
    t = txt.replace("\xa0", " ").strip()
    # Símbolo ADELANTE ("$213.44") — el formato de América.
    m = re.match(r"([^\d]+)\s?([\d.,  ]+)", t)
    if m:
        simbolo, n = m.group(1).strip(), m.group(2).strip()
    else:
        # Símbolo DETRÁS ("10,00 €") — el formato de España. Sin esta rama el texto
        # arrancaba con dígito, [^\d]+ no matcheaba, se devolvía None y el país entero
        # se descartaba por "implausible" aunque el importe estuviera perfecto.
        m = re.match(r"([\d.,  ]+)\s?([^\d]+)$", t)
        if not m:
            return None
        simbolo, n = m.group(2).strip(), m.group(1).strip()
    n = n.replace(" ", "")
    # el ultimo separador con 2 digitos detras son decimales
    n = re.sub(r"[.,](\d{2})$", r".\1", n)
    n = re.sub(r"[.,](?=\d{3})", "", n)
    try:
        return simbolo, float(n)
    except ValueError:
        return None


def _plausible(txt: str, pais: str = "") -> bool:
    leido = _a_numero(txt)
    if not leido:
        return False
    simbolo, valor = leido
    if simbolo in FX_APROX:
        usd = valor / FX_APROX[simbolo]
        return USD_MIN <= usd <= USD_MAX   # fuera de ese rango es lectura mala
    # Las monedas con "$" son ambiguas ($ argentino vs dólar) y antes pasaban SIEMPRE
    # sin ningún control. En los países que cobran en USD el "$" no es ambiguo: si ahí
    # se cuela un importe en pesos (17.117 en vez de 9,99) se publicaba tal cual y el
    # lead recibía un precio inventado. Por eso ahora se valida el rango en esos países.
    if MONEDA.get(pais) == "USD":
        return USD_MIN <= valor <= USD_MAX
    return True


# Dónde empieza la línea del total: "Total de $213.44", "Total: R$ 57,00", "Total ₡4 782,00".
# Sólo marca la POSICIÓN; el importe lo extrae PRECIO, que es el único que entiende los
# separadores raros de Hotmart (el espacio duro \xa0 de "₡4<NBSP>782,00", el "Gs.", el
# "B/."). Un patrón numérico propio acá cortaba en "₡4" y tiraba a Costa Rica y España
# fuera de la tabla.
RE_TOTAL = re.compile(r"Total\s*(?:de|:)?\s*", re.I)


def _precio_principal(pg) -> str:
    """El importe QUE PAGA EL CLIENTE: el TOTAL, con impuestos incluidos.

    Antes devolvía el primer precio que encontraba y en México eso era el precio
    BASE sin IVA: la página muestra "$184.00 · IVA incluido ($29.44) · Total de
    $213.44" y se publicaba 184. A un lead se le cotizó 184 y el checkout le iba a
    cobrar 213,44. Mismo error que tener el precio escrito a mano, pero disfrazado
    de dato real.

    Por eso ahora se busca PRIMERO la línea del total (con su etiqueta), y recién
    si no aparece se cae a los selectores, que quedan como respaldo."""
    # 1. La línea de "Total" en el texto: es la única que dice explícitamente lo que
    #    se cobra. Se toma la ÚLTIMA (el total final va abajo del resumen).
    try:
        cuerpo = pg.inner_text("body")
    except Exception:  # noqa: BLE001
        cuerpo = ""
    # Se toma la ÚLTIMA aparición: el total final va al pie del resumen.
    for etiqueta in reversed(list(RE_TOTAL.finditer(cuerpo or ""))):
        m = PRECIO.search(cuerpo, etiqueta.end(), etiqueta.end() + 40)
        if m:
            return m.group().replace("\xa0", " ").strip()

    # 2. Respaldo: selectores de total/resumen. 'price' queda al final porque suele
    #    ser el precio sin impuestos.
    for sel in ("[class*=total] [class*=value]", "[class*=Total]", "[class*=summary]",
                "[class*=price]:not([class*=bump])"):
        for e in pg.query_selector_all(sel):
            t = (e.inner_text() or "").strip()
            m = PRECIO.search(t)
            if m:
                return m.group().replace("\xa0", " ").strip()
    m = PRECIO.findall(cuerpo)
    return m[0].replace("\xa0", " ").strip() if m else ""


def _precios_bump(pg) -> list[dict]:
    """[{"nombre": ..., "precio": ...}] de cada order bump del checkout (los productos
    adicionales con checkbox, ej. "Micro Verdes | Curso Complementario").

    Cada order bump vive en un contenedor con la clase EXACTA "order-bump" (las
    sub-partes internas se llaman "order-bump__algo", con guion bajo doble, así que
    el selector de clase exacta no las trae duplicadas). Adentro aparecen DOS precios:
    el ancla tachada primero y el de oferta (el que se cobra si el lead lo tilda)
    al final — por eso se toma el ÚLTIMO precio del bloque, igual que
    _precio_principal toma el ÚLTIMO "Total" y no el subtotal sin descuento."""
    out = []
    try:
        for e in pg.query_selector_all(".order-bump"):
            texto = e.inner_text() or ""
            lineas = [l.strip() for l in texto.splitlines() if l.strip()]
            if not lineas:
                continue
            nombre = lineas[0]
            precios = list(PRECIO.finditer(texto))
            if not precios:
                continue
            precio = precios[-1].group().replace("\xa0", " ").strip()
            out.append({"nombre": nombre, "precio": precio})
    except Exception:  # noqa: BLE001
        pass
    return out


def scrapear(url: str, limite: int | None = None, solo: list[str] | None = None,
             max_min: int = 30, reporte: dict | None = None,
             previa: dict | None = None, cursor: int = 0,
             bumps_out: dict | None = None) -> dict:
    """Recorre los países y devuelve {prefijo: {pais, precio, moneda}}.

    `solo` / `max_min` / `reporte` son opcionales y no cambian el comportamiento por
    defecto: sin pasarlos hace exactamente lo de siempre (todos los países, o los
    primeros `limite`).

    `bumps_out`: si se pasa un dict, se lo completa con {iso: [precios de los order
    bumps]} por cada país visitado esta corrida. Pensado para `vigilar_precio.py`
    (un solo país testigo) — pedirlo para los 207 países alargaría mucho la corrida
    completa sin necesidad real, ya que Eugenia nunca le dice el precio de un bump
    a un lead (eso lo maneja Hotmart adentro del checkout).

    Con 219 países no entran todos en una corrida (`max_min`, 8-12 min normalmente):
    `previa` es la tabla que YA se sabía (de R2) — se usa como base y se completa/
    actualiza con lo que dé esta corrida, así nunca se pierde un país por no llegar a
    re-leerlo hoy. `cursor` es por dónde arrancar la lista esta vez: `main()` lo guarda
    y lo avanza entre corridas para que, repartido en varias horas, se termine
    cubriendo TODO en vez de leer para siempre los primeros N y nunca los demás.
    """
    from playwright.sync_api import sync_playwright
    global PREFIJO, MONEDA, SIN_HOTMART, ISO_DE_NOMBRE

    salida: dict = {k: v for k, v in (previa or {}).items() if not str(k).startswith("_")}
    fallos: dict = {}
    # Tope de tiempo propio. La Tarea Programada tiene un límite de 72 h y la política
    # es IgnoreNew: si una corrida se colgaba esperando la red, se quedaba "En ejecución"
    # tres días y TODAS las corridas siguientes se descartaban sin ejecutarse. Cortando
    # solo acá, la del día siguiente arranca limpia.
    fin = time.monotonic() + max_min * 60

    b = pg = None
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
            pg = b.new_page(locale="es-ES")

            def abrir() -> None:
                pg.goto(url, wait_until="networkidle", timeout=60000)
                pg.wait_for_timeout(2500)

            # Si el primer goto fallaba (red lenta al arrancar la PC), la excepción subía
            # hasta main() y se perdía la corrida entera. Ahora se reintenta una vez.
            for intento in (1, 2):
                try:
                    abrir()
                    break
                except Exception as e:
                    if intento == 2:
                        fallos["__checkout__"] = f"no abrió el checkout: {str(e)[:120]}"
                        _log(f"  no se pudo abrir el checkout: {str(e)[:120]}")
                        if reporte is not None:
                            reporte["fallos"] = fallos
                            reporte["intentados"] = 0
                        return salida
                    time.sleep(5)

            # Descubrir en vivo QUÉ países ofrece Hotmart hoy — el mismo navegador que ya
            # está abierto para leer precios, así que sale gratis. Si falla (cambiaron
            # el checkout, sin red), se sigue con lo que ya había en PREFIJO (el último
            # descubrimiento bueno, cacheado en disco) en vez de abortar la corrida.
            try:
                crudos = descubrir_paises(pg)
                if crudos:
                    _cache_guardar(crudos)
                    PREFIJO, MONEDA, SIN_HOTMART, ISO_DE_NOMBRE = construir_paises(crudos)
                    _log(f"  {len(PREFIJO)} países ofrece hoy el checkout "
                        f"({len(SIN_HOTMART)} sin Hotmart: {', '.join(sorted(SIN_HOTMART)) or '—'})")
            except Exception as e:  # noqa: BLE001
                _log(f"  no pude releer la lista de países ({str(e)[:100]}); "
                    f"sigo con los {len(PREFIJO)} que ya tenía")

            if solo:
                orden_base = [p for p in solo if p in PREFIJO]
            else:
                orden_base = list(PREFIJO)[:limite] if limite else list(PREFIJO)
            # Arrancar por el cursor y dar toda la vuelta: así una corrida que solo
            # llega a la mitad no repite SIEMPRE los primeros y nunca toca los últimos.
            cursor = cursor % len(orden_base) if orden_base else 0
            orden = orden_base[cursor:] + orden_base[:cursor]

            def elegir(iso: str) -> str:
                btn = pg.query_selector("button[class*=country]")
                if not btn:
                    raise RuntimeError("sin botón de país")
                btn.click(timeout=8000)
                pg.wait_for_timeout(600)
                opt = pg.query_selector(f'button.country-select-options[iso-code="{iso}"]')
                if not opt:
                    raise RuntimeError(f"país '{iso}' no está en el selector hoy")
                opt.click(timeout=8000)
                pg.wait_for_timeout(2200)
                if bumps_out is not None:
                    bumps_out[iso] = _precios_bump(pg)
                return _precio_principal(pg)

            intentados = exitos = 0
            for nombre in orden:
                if time.monotonic() > fin:
                    fallos["__timeout__"] = f"corte por tiempo tras {max_min} min"
                    _log(f"  corte por tiempo ({max_min} min): quedaron países sin leer")
                    break
                if nombre in SIN_HOTMART:
                    _log(f"    {nombre:24s} sin Hotmart (no está en el checkout) -> se saltea")
                    continue
                iso = ISO_DE_NOMBRE.get(nombre)
                if not iso:
                    fallos[nombre] = "sin ISO resuelto (revisar construir_paises)"
                    _log(f"    {nombre:24s} sin ISO resuelto -> se saltea")
                    continue
                intentados += 1
                p = ""
                ultimo_error = ""
                # El panel a veces queda en un estado raro y el clic siguiente se cuelga.
                # Recargar la página lo resetea; sin este reintento se perdían 8 países.
                for intento in (1, 2):
                    try:
                        p = elegir(iso)
                        break
                    except Exception as e:
                        ultimo_error = f"{type(e).__name__}: {str(e)[:120]}"
                        if intento == 2:
                            _log(f"    {nombre:24s} error: {str(e)[:50]}")
                            break
                        try:
                            abrir()
                        except Exception as e2:
                            # Antes este goto de recuperación estaba fuera del try: si la
                            # página no volvía, explotaba la corrida entera y se perdían
                            # los países que ya se habían leído bien.
                            ultimo_error = f"recarga falló: {str(e2)[:100]}"
                            _log(f"    {nombre:24s} no se pudo recargar: {str(e2)[:50]}")
                            break
                p = " ".join(p.split())
                if p and _plausible(p, nombre):
                    # "$444.00" a secas no dice nada: puede ser pesos o dólares. Se le
                    # agrega la moneda o el lead no sabe cuánto le van a cobrar.
                    mon = MONEDA.get(nombre, "")
                    if mon and mon not in p:
                        p = f"{p} {mon}"
                    salida[PREFIJO[nombre]] = {"pais": nombre, "precio": p, "moneda": mon}
                    exitos += 1
                    _log(f"    {nombre:24s} {p}")
                elif p:
                    # Ya había un precio de antes (de una corrida anterior): NO se borra
                    # por un fallo transitorio de HOY, se deja el que había.
                    fallos[nombre] = f"implausible: {p}"
                    _log(f"    {nombre:24s} descartado por implausible: {p}")
                else:
                    fallos[nombre] = ultimo_error or "sin precio legible"
                    _log(f"    {nombre:24s} sin precio legible")
            if reporte is not None:
                reporte["fallos"] = fallos
                reporte["intentados"] = intentados
                reporte["exitos"] = exitos
                reporte["total_paises"] = len(orden_base)
                # Próximo cursor: justo después del último de la lista ROTADA que se
                # llegó a intentar (éxito o no — reintentar un fallo duro every single
                # run no ayuda; si sigue fallando, el próximo ciclo lo vuelve a probar).
                reporte["cursor_siguiente"] = (cursor + intentados) % len(orden_base) if orden_base else 0
        finally:
            # Sin el finally, cualquier error dejaba el chromium vivo y a la corrida
            # siguiente le quedaba el proceso zombie comiendo RAM.
            if b:
                try:
                    b.close()
                except Exception:
                    pass
    return salida


CURSOR_FILE = ROOT / "state" / "precios_cursor.json"


def _cursor_leer(clave: str) -> int:
    try:
        return int(json.loads(CURSOR_FILE.read_text(encoding="utf-8")).get(clave, 0))
    except Exception:  # noqa: BLE001
        return 0


def _cursor_guardar(clave: str, valor: int) -> None:
    try:
        d = {}
        if CURSOR_FILE.is_file():
            d = json.loads(CURSOR_FILE.read_text(encoding="utf-8"))
        d[clave] = valor
        CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        CURSOR_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _tabla_previa(clave: str) -> dict:
    """La tabla que YA está en R2 para esta clave, o {} si no hay/falla la lectura.
    Sirve de base para no perder países que hoy no llegan a re-scrapearse (ver
    scrapear(previa=...))."""
    # 19/11: SIEMPRE con wrangler desde la carpeta del Worker (su .env tiene el token de la
    # cuenta de Eugenia). armar_stock.r2_get va por la puerta de GitHub cuando PUERTA_R2_URL
    # está en el .env, y la puerta NO abre wa/precios_pais*: volvía {} y cada corrida subía
    # solo los países de esa hora (hidroponía quedó sin Argentina/México/Colombia).
    try:
        p = subprocess.run(["npx", "wrangler", "r2", "object", "get", f"{BUCKET}/{clave}", "--remote", "--pipe"],
                           cwd=WDIR, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180, shell=(sys.platform == "win32"))  # en Linux, shell=True con lista corre solo "npx"
        return json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else {}
    except Exception:  # noqa: BLE001
        return {}


def subir(tabla: dict, key: str, checkout: str = "") -> bool:
    tmp = WDIR / "_precios_tmp.json"
    # Sello de tiempo: sin esto el worker no puede saber si la tabla es de hace 2 horas
    # o de hace 2 semanas, y termina cotizando un precio viejo como si fuera de hoy.
    # Con la marca puede negarse a decir un precio cuando el dato esta vencido.
    con_sello = dict(tabla)
    con_sello["_meta"] = {
        "scrapeado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ts": int(datetime.now(timezone.utc).timestamp()),
        "paises": len([k for k in tabla if not k.startswith("_")]),
        "checkout": checkout or CHECKOUT_CFG,
    }
    tmp.write_text(json.dumps(con_sello, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(["npx", "wrangler", "r2", "object", "put", f"{BUCKET}/{key}",
                        "--file", str(tmp), "--remote"],
                       cwd=WDIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", shell=(sys.platform == "win32"))  # en Linux, shell=True con lista corre solo "npx"
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        # Antes el error de wrangler se tiraba a la basura: solo se veía "no subió a R2"
        # sin decir por qué (token vencido, sin red, bucket mal). Así no se podía arreglar.
        _log(f"  wrangler rc={r.returncode} {((r.stderr or r.stdout) or '').strip()[:300]}")
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="",
                    help="scrapear SOLO este checkout (por defecto se recorren todos los nichos)")
    ap.add_argument("--nicho", help="scrapear solo este nicho")
    ap.add_argument("--limite", type=int, help="probar con pocos países")
    ap.add_argument("--paises", help="solo estos países, separados por coma")
    ap.add_argument("--salida", help="dónde escribir el JSON (por defecto analisis/precios_checkout.json)")
    ap.add_argument("--max-min", type=int, default=30,
                    help="tope de minutos de scrapeo antes de cortar (por defecto 30)")
    ap.add_argument("--sin-subir", action="store_true")
    a = ap.parse_args()

    solo = [s.strip() for s in a.paises.split(",") if s.strip()] if a.paises else None
    if solo:
        desconocidos = [s for s in solo if s not in PREFIJO]
        if desconocidos:
            _log(f"países desconocidos (revisar tildes): {', '.join(desconocidos)}")
        if not [s for s in solo if s in PREFIJO]:
            return 1

    # QUÉ SE VA A SCRAPEAR. Sin --url se recorren TODOS los nichos que tengan checkout:
    # cada producto tiene su propia tabla de precios por país y Eugenia cotiza los dos.
    if a.url:
        objetivos = [(a.nicho or "manual", a.url, "wa/precios_pais.json"
                      if not a.nicho or a.nicho == "hidroponia"
                      else f"wa/precios_pais_{a.nicho}.json")]
    else:
        objetivos = [o for o in nichos_con_checkout() if o[0] not in PRODUCTOS_EXTRA]
        extras = productos_extra()
        if a.nicho:
            objetivos = [o for o in objetivos if o[0] == a.nicho]
            extras = [o for o in extras if o[0] == a.nicho]
    if a.url:
        extras = []
    if not objetivos and not extras:
        _log("sin URL de checkout: revisar el checkout del nicho en la pestaña Nicho")
        return 1

    # El tope de minutos es del PROCESO, no de cada nicho: con dos nichos y --max-min 25
    # sin repartir, la tarea tardaba 50 y se pisaba con la corrida siguiente.
    por_nicho = (max(8, a.max_min // len(objetivos)) if a.max_min else a.max_min) if objetivos else 0
    if len(objetivos) > 1:
        _log(f"{len(objetivos)} nichos con checkout · {por_nicho} min para cada uno")

    peor, estados = 0, {}
    for nombre, url, clave in objetivos:
        rc_n = _correr_uno(nombre, url, clave, solo, a, por_nicho, estados)
        peor = max(peor, rc_n)
    # Los cursos extra van al final y con su propio tope. Si fallan queda anotado en el
    # estado, pero NO cambian el código de salida: ese avisa del precio que cotiza el chat.
    solo_extras = not objetivos
    for nombre, url, clave in extras:
        rc_n = _correr_uno(nombre, url, clave, solo, a,
                           (a.max_min if solo_extras else MIN_POR_EXTRA), estados)
        if solo_extras:
            peor = max(peor, rc_n)

    try:
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(json.dumps({
            "cuando": datetime.now().isoformat(timespec="seconds"),
            "nichos": estados,
            "exit_code": peor,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return peor


def _correr_uno(nombre: str, url: str, clave: str, solo, a, max_min: int,
                estados: dict) -> int:
    """Scrapea UN checkout y sube su tabla. Devuelve el exit code de ESE nicho.

    Un nicho que falla NO puede tumbar al otro: cada uno escribe su archivo y su estado,
    y main() se queda con el peor código. Antes, con un solo objetivo, cualquier fallo
    terminaba la corrida entera.
    """
    _log(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} [{nombre}] checkout: {url}")
    reporte: dict = {}
    # 219 países no entran en una corrida de 8-12 min: se parte de lo que YA está en R2
    # (no se pierde nada de lo ya sabido) y se arranca por donde quedó la vez pasada
    # (no se estanca leyendo siempre los primeros N y nunca los últimos).
    previa = _tabla_previa(clave) if not a.sin_subir else {}
    # 19/11: sin la tabla previa, subir lo de esta corrida BORRA el resto de los países. Si no
    # se pudo leer, se scrapea igual pero no se sube (salvo que R2 no tenga nada todavía).
    sin_previa = not a.sin_subir and not previa
    cursor = _cursor_leer(clave)
    # El scrapeo entero envuelto: cualquier excepción no prevista (playwright sin
    # navegador, chromium que no arranca) terminaba en un traceback que con pythonw.exe
    # no se veía en ningún lado, y la tarea igual quedaba marcada como terminada.
    try:
        tabla = scrapear(url, a.limite, solo, max_min, reporte, previa=previa, cursor=cursor)
    except Exception as e:
        tabla = dict(previa)
        reporte["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        _log(f"scrapeo abortado: {reporte['error']}")

    # Solo una corrida REAL (todos los países, subiendo a R2) mueve el cursor
    # compartido: un chequeo manual (--sin-subir, --paises, --limite) no debe hacerle
    # perder el lugar a la próxima corrida automática.
    if "cursor_siguiente" in reporte and not a.sin_subir and not solo and not a.limite:
        _cursor_guardar(clave, reporte["cursor_siguiente"])

    intentados = reporte.get("intentados") or len(solo or (list(PREFIJO)[:a.limite] if a.limite else PREFIJO))
    exitos = reporte.get("exitos", intentados if not reporte.get("error") else 0)
    total = reporte.get("total_paises", len(PREFIJO))
    _log(f"\n{len(tabla)} países con precio en total ({exitos} nuevos/actualizados de "
        f"{intentados} intentados esta corrida · {total} países ofrece Hotmart hoy)")

    estado = {
        "cuando": datetime.now().isoformat(timespec="seconds"),
        "checkout": url,
        "clave_r2": clave,
        "leidos": len(tabla),
        "intentados": intentados,
        "fallos": reporte.get("fallos", {}),
        "error": reporte.get("error", ""),
        "subido_r2": None,
    }

    # El JSON se escribe SIEMPRE que haya algo, y ANTES de intentar subir: si wrangler
    # fallaba, antes no quedaba nada local para revisar qué se había leído.
    # Un archivo POR NICHO: con nombre fijo, el segundo pisaba la tabla del primero y
    # quedaba una sola para revisar.
    destino = (Path(a.salida) if a.salida
               else ROOT / "analisis" / f"precios_checkout_{nombre}.json")
    if tabla:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(tabla, ensure_ascii=False, indent=1), encoding="utf-8")
        _log(f"tabla escrita en {destino}")

    rc = 0
    if not tabla:
        _log("no se pudo leer ningún precio")
        rc = 1
    elif intentados and exitos * 2 < intentados:
        # Se mira el ÉXITO DE ESTA CORRIDA (no el total acumulado en R2, que con 219
        # países crece de a poco entre corridas por diseño): si de lo que se INTENTÓ
        # ahora menos de la mitad salió bien, algo anda mal HOY (Hotmart cambió el
        # checkout, la red está mala), y hay que avisar aunque la tabla total tenga
        # buena pinta por lo ya scrapeado en corridas anteriores.
        _log(f"MUY POCOS países salieron bien esta corrida ({exitos}/{intentados}): revisar")
        rc = 2

    filas = len([k for k in (tabla or {}) if not str(k).startswith("_")])
    if tabla and not a.sin_subir and sin_previa and filas < 100:
        _log(f"⚠ no subo: no pude leer la tabla de R2 y esta corrida trae solo {filas} países "
             f"(subirla borraría el resto)")
        estado["subido_r2"] = False
        rc = rc or 3
    elif tabla and not a.sin_subir:
        ok = subir(tabla, clave, url)
        estado["subido_r2"] = ok
        _log("subido a R2" if ok else "⚠ no subió a R2")
        if not ok and rc == 0:
            # Scrapeo bien pero R2 quedó viejo = el lead sigue viendo el precio de antes.
            # Antes esto devolvía 0 y la tarea figuraba "correcta" con el dato podrido.
            rc = 3

    estado["exit_code"] = rc
    # El estado lo escribe main() con TODOS los nichos juntos, después del bucle: si cada
    # uno escribiera el archivo, el último borraba el diagnóstico de los anteriores.
    estados[nombre] = estado
    return rc


if __name__ == "__main__":
    sys.exit(main())
