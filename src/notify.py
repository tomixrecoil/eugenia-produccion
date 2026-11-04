"""Alertas por email cuando el pipeline se queda sin recursos (keys agotadas, sin voz).

ANTI-REPETICIÓN PERSISTENTE
---------------------------
Antes el "no repetir el mismo aviso" era un `set()` en memoria: cada proceso
(pipeline, webapp, tarea programada) arrancaba con el set vacío, así que el mismo
problema avisaba una vez por corrida… y en un proceso largo como la webapp avisaba
UNA sola vez y nunca más, aunque el problema siguiera días después. Resultado real:
se agotó la voz de ElevenLabs y el aviso nunca volvió a salir.

Ahora el registro vive en state/avisos.json (compartido por TODOS los procesos) con
una ventana horaria: el mismo dedup_key no se repite antes de ALERT_DEDUP_HORAS
(12 h por defecto), pero pasada la ventana vuelve a avisar mientras el problema siga.
"""
from __future__ import annotations

import json
import os
import smtplib
import time
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from src.logging_setup import get_logger

log = get_logger()

ROOT = Path(__file__).resolve().parent.parent

# Registro en disco de los avisos ya mandados: {dedup_key: {ts, asunto, veces}}.
# Va en state/ junto al resto del estado del agente (se conserva entre reinicios).
AVISOS_PATH = ROOT / "state" / "avisos.json"

# Cada cuántas horas se puede REPETIR el mismo aviso. 12 h = si algo sigue roto a la
# mañana siguiente, vuelve a sonar; y a la vez un pipeline que corre 8 veces por día
# no manda 8 mails iguales. Se puede cambiar sin tocar código con ALERT_DEDUP_HORAS.
VENTANA_HORAS_DEFAULT = 12.0

_sent: set[str] = set()  # claves avisadas en ESTE proceso (informativo; el gate real es el archivo)

# El emoji del asunto se elige por lo que dice el aviso, no es siempre el mismo.
# Antes TODOS los mails arrancaban con "⚠️ [Agente Marketing]": el remitente ya se
# llama Agente Marketing (era repetir el nombre) y el ⚠️ fijo hacía que un aviso
# bueno ("precio actualizado") pareciera un problema. Primera coincidencia gana.
_EMOJIS = (
    ("💲", ("precio", "checkout", "cotiza")),
    ("💰", ("venta", "compra", "cobro", "factura", "hotmart")),
    ("🔇", ("sin voz", "elevenlabs", "audio", "doblaj")),
    ("🧠", ("gemini", "cuota", "api key", "token")),
    ("🩺", ("revisar", "vigilancia", "salud", "chequeo", "disco")),
    ("🎬", ("reel", "video", "publicar", "publicac")),
    ("💬", ("whatsapp", "lead", "comentario", "mensaje")),
    ("⏰", ("recordatorio", "pendiente", "vence", "programad", "impag")),
    ("🚨", ("agotad", "fallo", "falló", "error", "roto", "caíd", "caid", "no pude")),
)
_EMOJI_DEFAULT = "📣"


def _emoji(subject: str, body: str = "") -> str:
    """Elige el emoji del asunto según de qué habla el aviso.

    Mira PRIMERO el asunto y recién después el cuerpo: si no, un aviso de
    "Tareas programadas: revisar" salía con 💲 solo porque en el cuerpo aparecía
    el nombre de la tarea `AgenteMarketing_precios`.
    """
    for donde in (subject, body):
        texto = (donde or "").lower()
        for icono, claves in _EMOJIS:
            if any(k in texto for k in claves):
                return icono
    return _EMOJI_DEFAULT


def _ventana_horas(explicita: float | None = None) -> float:
    if explicita is not None:
        try:
            return max(0.0, float(explicita))
        except (TypeError, ValueError):
            pass
    try:
        return max(0.0, float(os.getenv("ALERT_DEDUP_HORAS") or VENTANA_HORAS_DEFAULT))
    except (TypeError, ValueError):
        return VENTANA_HORAS_DEFAULT


def _asegurar_env() -> None:
    """Carga el .env si el proceso no lo cargó (scripts sueltos, tareas de Windows).

    Sin esto, `alert()` se iba por la rama "faltan GMAIL_ECOSISTEMA_USER/PASS" y el
    aviso moría en el log: justo el caso donde MÁS falta que llegue el mail.
    NO pisa variables ya presentes en el entorno (override=False)."""
    if os.getenv("GMAIL_ECOSISTEMA_USER") and os.getenv("GMAIL_ECOSISTEMA_PASS"):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:  # noqa: BLE001  — si falta python-dotenv el flujo sigue igual que antes
        pass


def _leer_registro() -> dict:
    """Lee state/avisos.json. Ante cualquier problema devuelve {} (nunca rompe el aviso:
    peor que repetir un mail es no mandarlo)."""
    try:
        if AVISOS_PATH.exists():
            data = json.loads(AVISOS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001  (json corrupto, permisos, archivo a medio escribir)
        pass
    return {}


def _escribir_registro(data: dict) -> None:
    """Guarda el registro de forma atómica: se escribe un .tmp y recién ahí se reemplaza.
    Hay varios procesos escribiendo (pipeline + webapp + tareas), y con escritura directa
    uno podía leer el archivo a medio escribir y perder todo el historial de avisos."""
    try:
        AVISOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = AVISOS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, AVISOS_PATH)
    except Exception as e:  # noqa: BLE001
        log.debug("No pude guardar el registro de avisos: %s", str(e)[:120])


def avisos_registrados() -> dict:
    """Todo el registro tal cual está en disco (para paneles/diagnóstico)."""
    return _leer_registro()


def ultimo_aviso(dedup_key: str) -> float | None:
    """Epoch del último envío de ese aviso, o None si nunca se mandó.
    Sirve para que otros módulos sepan que un problema ya se reportó (ej. vigilancia)."""
    reg = _leer_registro().get(dedup_key) or {}
    try:
        return float(reg.get("ts")) if reg.get("ts") else None
    except (TypeError, ValueError):
        return None


def _enviar_whatsapp(subject: str, body: str) -> bool:
    """Respaldo del mail: se manda al WhatsApp del dueño.

    Hizo falta porque la contraseña de aplicación de Gmail quedó inválida cuando se
    cambió la clave de la cuenta (535 Username and Password not accepted) y las
    alertas no llegaban a NINGÚN lado: la vigilancia corría al pedo.

    Solo funciona dentro de la ventana de 24h de WhatsApp (o sea, si el dueño le
    escribió al número del negocio hace menos de un día). Si no, WhatsApp lo rechaza
    y queda registrado en el log.
    """
    destino = (os.getenv("ALERT_WHATSAPP") or "").strip()
    if not destino:
        return False
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_ID")
    if not token or not phone_id:
        return False
    try:
        import requests
        ver = os.getenv("META_GRAPH_VERSION", "v21.0")
        texto = f"{_emoji(subject, body)} *{subject}*\n\n{body}"[:3900]
        r = requests.post(
            f"https://graph.facebook.com/{ver}/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "to": destino,
                  "type": "text", "text": {"preview_url": False, "body": texto}},
            timeout=30)
        if r.status_code == 200:
            log.info("ALERTA enviada por WhatsApp a %s: %s", destino, subject)
            return True
        log.warning("WhatsApp rechazó la alerta [%s]: %s", r.status_code, r.text[:160])
    except Exception as e:  # noqa: BLE001
        log.warning("No pude avisar por WhatsApp: %s", str(e)[:120])
    return False


def _enviar_mail(subject: str, body: str) -> bool:
    """Solo el envío por Gmail, sin caer a WhatsApp si falla (eso lo decide quien
    llama). Separado de _enviar() para poder usarlo como respaldo DESDE whatsapp()."""
    user = os.getenv("GMAIL_ECOSISTEMA_USER")
    pw = os.getenv("GMAIL_ECOSISTEMA_PASS")
    to = os.getenv("ALERT_EMAIL", "")
    if not user or not pw:
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"{_emoji(subject, body)} {subject}"
        msg["From"] = formataddr(("Agente Marketing", user))
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(user, pw)
            srv.sendmail(user, [to], msg.as_string())
        log.info("ALERTA enviada a %s: %s", to, subject)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("No pude enviar por mail '%s' (%s)", subject, str(e)[:110])
        return False


def _enviar(subject: str, body: str) -> bool:
    user = os.getenv("GMAIL_ECOSISTEMA_USER")
    pw = os.getenv("GMAIL_ECOSISTEMA_PASS")
    to = os.getenv("ALERT_EMAIL", "")
    if not user or not pw:
        log.warning("ALERTA no enviada (faltan GMAIL_ECOSISTEMA_USER/PASS): %s", subject)
        return _enviar_whatsapp(subject, body)
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"{_emoji(subject, body)} {subject}"
        msg["From"] = formataddr(("Agente Marketing", user))
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(user, pw)
            srv.sendmail(user, [to], msg.as_string())
        log.info("ALERTA enviada a %s: %s", to, subject)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("No pude enviar la alerta '%s' por mail (%s) -> pruebo WhatsApp.",
                    subject, str(e)[:110])
        return _enviar_whatsapp(subject, body)


def whatsapp(subject: str, body: str) -> bool:
    """Manda un WhatsApp directo al dueño (ALERT_WHATSAPP) Y TAMBIÉN un mail de
    respaldo, sin la ventana anti-repetición de alert(): esto es para avisos de
    RUTINA (ej. "se publicó un reel"), donde cada uno es un evento distinto y
    legítimo, no una anomalía a deduplicar.

    Por qué manda los DOS canales: la API de WhatsApp devuelve 200 (éxito) aunque
    el mensaje se pierda después — medido el 23/08: si el dueño no le escribió al
    número en las últimas 24h, Meta lo descarta en silencio con el error 131047
    ("re-engagement message") y el código nunca se entera, porque ese fallo llega
    async por webhook, no en la respuesta del POST. El mail no tiene esa ventana,
    así que es la red de seguridad: si el WhatsApp se pierde, el aviso llega igual.
    Devuelve True si salió por AL MENOS uno de los dos."""
    ok_wa = _enviar_whatsapp(subject, body)
    ok_mail = False if _mails_apagados() else _enviar_mail(subject, body)
    return ok_wa or ok_mail


def _mails_apagados() -> bool:
    """Tomix (01/11): "basta de mails" — los avisos al prender la PC eran casi todos
    falsos positivos. Apagados por default; se vuelven a prender con AVISOS_MAIL=1 en el
    .env (config.write_env). Lo que sigue andando se ve en el panel (Salud)."""
    _asegurar_env()
    return os.getenv("AVISOS_MAIL", "0").strip() != "1"


def alert(subject: str, body: str, dedup_key: str | None = None,
          ventana_horas: float | None = None, dry: bool = False) -> bool:
    """Envía un email de alerta, como máximo una vez cada `ventana_horas` por dedup_key.

    Compatible con las llamadas de siempre: alert(asunto, cuerpo, dedup_key="x").
    Devuelve True si el mail salió (antes devolvía None; nadie usaba el retorno).

    dry=True: no manda nada ni toca el registro, solo loguea lo que haría (para probar).
    """
    key = dedup_key or subject
    if _mails_apagados():
        log.info("Aviso no enviado (avisos por mail apagados): %s", subject)
        return False
    ventana = _ventana_horas(ventana_horas)
    ahora = time.time()

    reg = _leer_registro()
    entrada = reg.get(key) if isinstance(reg.get(key), dict) else {}
    try:
        ultimo = float(entrada.get("ts") or 0)
    except (TypeError, ValueError):
        ultimo = 0.0
    faltan = (ultimo + ventana * 3600) - ahora

    if ultimo and faltan > 0:
        # Todavía dentro de la ventana: no se manda, pero se cuenta para que el próximo
        # mail diga cuántas veces se repitió (da idea de la gravedad).
        entrada["veces"] = int(entrada.get("veces") or 0) + 1
        entrada["ultimo_intento"] = ahora
        reg[key] = entrada
        if not dry:
            _escribir_registro(reg)
        log.info("Alerta '%s' silenciada (ya se avisó hace %.1f h; se repite en %.1f h).",
                 key, (ahora - ultimo) / 3600, faltan / 3600)
        return False

    veces = int(entrada.get("veces") or 0)
    cuerpo = body
    if veces:
        cuerpo += (f"\n\n---\nEste mismo problema se repitió {veces} vez/veces desde el "
                   f"último aviso (se silenciaron para no llenarte la casilla).")
    if ultimo:
        cuerpo += f"\nÚltimo aviso igual: {time.strftime('%Y-%m-%d %H:%M', time.localtime(ultimo))}."

    if dry:
        log.info("[dry] Alerta que se mandaría -> %s | %s", subject, cuerpo.replace("\n", " ")[:200])
        return False

    _asegurar_env()
    if not _enviar(subject, cuerpo):
        # No se marca como enviado a propósito: si falló el SMTP (o faltan credenciales)
        # queremos que el próximo intento lo vuelva a probar, no que quede silenciado 12 h.
        return False

    _sent.add(key)
    reg[key] = {"ts": ahora, "asunto": subject, "veces": 0,
                "fecha": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ahora))}
    _escribir_registro(reg)
    return True
