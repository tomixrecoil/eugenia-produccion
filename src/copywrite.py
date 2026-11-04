"""
Generación del copy de Facebook Ads a partir de la descripción de Gemini.
Motor configurable por nicho: OpenAI (ChatGPT) o Gemini (gratis).
"""
from __future__ import annotations

from src.logging_setup import get_logger

log = get_logger()


def _estructura_para(seed: str, nicho: str = "") -> tuple[str, str]:
    """Elige UNA estructura de copy, rotando de forma estable por video.

    El prompt maestro imponía una sola estructura obligatoria, así que los 15 últimos
    posts salieron calcados ("Muchos creen que X… pero en realidad Y"). La mediana de
    likes cayó de 774 a 54. Los dos posts que se viralizaron no usaban esa fórmula.
    """
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent / "prompts"
    # El archivo del nicho si lo tiene (prompts/<nicho>_estructuras.txt), si no el
    # compartido. Las estructuras traen ejemplos de hidroponía (lechugas, macetas), así
    # que un nicho nuevo tiene que poder escribir las suyas sin pisarle las de nadie.
    ruta = base / "estructuras.txt"
    if nicho:
        propia = base / f"{nicho}_estructuras.txt"
        if propia.is_file():
            ruta = propia
    try:
        bloques = ruta.read_text(encoding="utf-8").split("═" * 68)
    except Exception:
        return "", ""
    opciones = [b.strip() for b in bloques if "ESTRUCTURA " in b and "—" in b]
    if not opciones:
        return "", ""
    n = sum(ord(c) for c in str(seed or "x")) % len(opciones)
    elegida = opciones[n]
    nombre = elegida.split("\n", 1)[0].strip()
    return elegida, nombre


def con_estructura(system_prompt: str, seed: str, nicho: str = "") -> tuple[str, str]:
    """Cambia la estructura fija del prompt maestro por la que toca esta vez."""
    bloque, nombre = _estructura_para(seed, nicho)
    if not bloque:
        return system_prompt, ""
    ini = system_prompt.find("ESTRUCTURA OBLIGATORIA")
    # El corte va hasta "FIN ESTRUCTURA" y NO hasta "ESTILO": entre medio vive el
    # bloque de CTA con el link real de compra y el WhatsApp. Cortando en "ESTILO"
    # ese bloque se borraba en cada copy y el LLM terminaba inventando el enlace o
    # dejando un [LINK] sin reemplazar (pasó en 18 posteos ya publicados).
    fin = -1
    if ini >= 0:
        fin = system_prompt.find("FIN ESTRUCTURA", ini)
        if fin < 0:   # prompts viejos que no tienen el marcador
            fin = system_prompt.find("ESTILO", ini)
    if ini < 0 or fin < 0:
        return system_prompt + "\n\n" + bloque, nombre
    return system_prompt[:ini] + bloque + "\n\n" + system_prompt[fin:], nombre


def _user_content(description: str, script: str = "") -> str:
    # El guion de voz (29/08, a pedido de Tomix): antes el copy solo veia la
    # transcripcion+descripcion de Gemini y nunca lo que efectivamente se termino
    # narrando en el reel (el guion puede diferir del audio original si hubo doblaje,
    # o directamente ser nuevo si el video era mudo). Seccion aparte, igual al resto:
    # si no hay guion (video sin voz en off), se lo dice explicito en vez de omitirlo.
    guion_txt = (script or "").strip() or "SIN GUION DE VOZ (este video no lleva narración)"
    return (
        "A continuación está el análisis del video (transcripción + descripción "
        "cuadro a cuadro) generado por otro sistema, MÁS el guion de voz que "
        "efectivamente se narra en el reel. Usalo todo como materia prima para "
        "construir el anuncio siguiendo EXACTAMENTE la estructura indicada:\n\n"
        f"{description}\n\n"
        "=== GUION DE VOZ (lo que efectivamente se narra en este reel) ===\n\n"
        f"{guion_txt}"
    )


def _openai_copy(description, script, system_prompt, api_key, model) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _user_content(description, script)},
        ],
        temperature=0.85,
    )
    return (resp.choices[0].message.content or "").strip()


def _gemini_copy(description, script, system_prompt, api_key, model, nicho: str = "") -> str:
    from src import gemini_client, referencia
    # Referencia de los reels ganadores del nicho como instrucción de sistema.
    sistema_ref = referencia.como_sistema(nicho)
    resp = gemini_client.run(lambda c: gemini_client.generate(
        c, model, [system_prompt + "\n\n" + _user_content(description, script)],
        system=sistema_ref))
    return (resp.text or "").strip()


def generate_copy(
    description: str,
    system_prompt: str,
    engine: str,
    openai_key: str,
    openai_model: str,
    gemini_key: str,
    gemini_model: str,
    cta_link: str = "",
    seed: str = "",
    nicho: str = "",
    script: str = "",
) -> str:
    # SOLO GEMINI (30/08, a pedido de Tomix): OpenAI nunca se pagó — no tenemos ese plan
    # activo — así que no tiene sentido que la cascada lo intente ni como respaldo: si
    # Gemini falla, que falle avisando, no que gaste un llamado a una API que sabemos
    # que va a rebotar con "sin créditos". Antes esto probaba los dos motores; ahora es
    # gemini o nada. `engine`/openai_key/openai_model quedan como parámetros por
    # compatibilidad con quien llama, pero no se usan.
    del engine, openai_key, openai_model
    system_prompt, estructura = con_estructura(system_prompt, seed, nicho)
    if estructura:
        log.info("Copy con %s", estructura)
    motores = [("gemini", lambda: _gemini_copy(description, script, system_prompt, gemini_key,
                                                gemini_model, nicho))]

    copy, ultimo = "", None
    for i, (nombre, fn) in enumerate(motores):
        log.info("Generando copy con %s%s…", nombre.capitalize(),
                 " (el otro motor falló)" if i else "")
        try:
            copy = fn()
        except Exception as e:  # noqa: BLE001
            ultimo = e
            log.warning("%s falló: %s", nombre.capitalize(), str(e)[:130])
            copy = ""
        if copy:
            if i:
                log.warning("El copy salió con %s en vez de %s. Revisá ese motor.",
                            nombre, engine)
            break

    if not copy:
        raise RuntimeError(
            f"Ningún motor pudo escribir el copy (probé {' y '.join(m for m, _ in motores)}). "
            f"Último error: {str(ultimo)[:160]}")
    if cta_link:
        copy = copy.replace("[LINK]", cta_link)
    log.info("Copy generado (%d caracteres).", len(copy))
    return copy
