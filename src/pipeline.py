"""
Orquestador end-to-end:

  descubrir ganadores -> descargar -> Gemini (análisis) -> [audio/doblaje + mockup]
                      -> copy -> Meta (publicar)

Cada ganador se procesa de forma independiente; si uno falla, se sigue con el resto.
Los artefactos (descripción, copy, video final) se guardan en output/<niche>/<video_id>/.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import config
from config import Niche, Secrets
from src import (analyze, copywrite, discover, download, dubbing, publish,
                 publish_ig, state, subtitles, videoedit, voiceover)
# Publicar NO se hace más acá: hay un solo camino (src/publisher.py) que junta
# FB + IG + YouTube + botón de WhatsApp + guard anti-inglés + idempotencia. El bloque
# propio que había en process_video() no subía a YouTube (los reels del pipeline se
# perdían el canal entero) y escribía el historial con su formato particular.
from src import publisher
from src.logging_setup import get_logger

log = get_logger()

ROOT = Path(__file__).resolve().parent.parent


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_analysis(text: str) -> tuple[str, str]:
    """Separa la salida de Gemini en (transcripción, descripción visual)."""
    parts = re.split(r"===\s*DESCRIPCIÓN DEL VIDEO", text, maxsplit=1)
    transcription = re.sub(r"===.*?===", "", parts[0], flags=re.DOTALL).strip()
    visual = parts[1].strip() if len(parts) > 1 else text
    return transcription, visual


def _process_media(video_path: Path, analysis_text: str, niche: Niche,
                   secrets: Secrets, out_dir: Path,
                   voz: str = "auto") -> tuple[Path | None, str]:
    """Aplica doblaje/voz y mockup. Devuelve (video_final, nota).
    video_final = None significa: descartar este video (no publicar).

    `voz`: "auto" = la cascada de siempre (Antonio -> Charon -> Antoni). Ver el porqué
           del orden en el comentario de la cascada, más abajo.
           "antonio" = alias de "auto" (queda por compatibilidad con llamadores viejos:
           antes existían dos órdenes distintos, ahora es uno solo). NO saca los
           respaldos: si Antonio no está disponible en ninguna cuenta, sigue habiendo
           voz en español antes que descartar el reel.

    Un solo camino (02/11): la decisión de doblar/narrar de abajo define que un video
    EN INGLÉS se TRADUCE y se le REEMPLAZA el audio, mientras que uno MUDO recibe un
    guion nuevo mezclado sobre su ambiente.
    """
    if niche.audio_mode != "auto" and not niche.add_mockup:
        return video_path, "sin_cambios"

    final = video_path
    note = "audio_original"

    if niche.audio_mode == "auto":
        transcription, visual = _split_analysis(analysis_text)
        cls = dubbing.classify_audio(transcription or analysis_text,
                                     secrets.gemini_api_key, secrets.gemini_model)
        dur = videoedit.probe_duration(video_path)
        lang, has_speech = cls["language"], cls["has_speech"]

        needs_dub = has_speech and lang not in ("es", "none")
        needs_vo = (not has_speech) and niche.voiceover_when_silent

        if needs_dub and niche.english_policy == "discard":
            log.info("Video con voz en '%s' y política=descartar -> se salta.", lang)
            return None, f"descartado_{lang}"

        if needs_dub or needs_vo:
            mode = "translate" if needs_dub else "describe"
            source = (transcription if needs_dub else visual) or analysis_text
            # Si el análisis ya trajo la TRADUCCIÓN AL ESPAÑOL, se usa esa como base:
            # es más fiel al original que volver a traducir desde cero.
            if needs_dub:
                m_trad = re.search(r"TRADUCCIÓN AL ESPAÑOL\s*:?\s*(.+?)(?====|\Z)",
                                   analysis_text, re.DOTALL | re.IGNORECASE)
                if m_trad:
                    trad = m_trad.group(1).strip()
                    if trad and "ya está en español" not in trad.lower() and len(trad) > 40:
                        source = trad
                        log.info("Uso la traducción que ya hizo el análisis (%d chars).", len(trad))
            script = dubbing.spanish_script(mode, source, dur,
                                            secrets.gemini_api_key, secrets.gemini_model,
                                            video_id=out_dir.name, nicho=niche.name)
            (out_dir / "guion_voz.txt").write_text(script, encoding="utf-8")
            # Voz: ElevenLabs, todas las cuentas en orden. Si ninguna responde el reel
            # se DESCARTA: nunca se publica el audio original (inglés/crudo).
            vo = None
            alignment = {}   # timing por carácter -> subtítulos perfectamente sincronizados

            # CASCADA DE VOZ (invertida el 22/08/2026, decisión de Tomix):
            #   1. ANTONIO (ElevenLabs) en TODAS las cuentas.
            #   2. GOOGLE AI STUDIO / CHARON en sus cuentas, si NINGUNA de Antonio pudo.
            #   3. ANTONI (voz gratis) solo como último recurso, cuando ya no queda nada.
            #
            # Charon mutaba de voz DENTRO de un mismo reel: sintetiza frase por frase
            # (necesario para el timing real de los subtítulos) y cada llamada es una
            # generación independiente sin semilla fija, así que el timbre no es estable
            # entre frases. Se suma que el tier gratis de la API de TTS es de solo 10
            # pedidos por día POR CUENTA: un reel de 15-20 frases puede agotar una cuenta
            # a mitad de camino y saltar a la siguiente en silencio, empeorando la
            # mutación. Antonio sintetiza el guion COMPLETO en una sola llamada: no tiene
            # ese problema. Antes Charon era la voz principal (con Antonio de respaldo);
            # ahora es al revés y Charon queda de resguardo si las 5 cuentas de
            # ElevenLabs se quedaron sin cuota el mismo día.
            #
            # El orden importa y antes estaba mal: una cuenta que no podía usar Antonio
            # —plan free, voz de biblioteca— reintentaba EN ESA MISMA CUENTA con Antoni y
            # daba eso por bueno, sin probar las otras dos cuentas que sí podían. El reel
            # salía con otra voz y la marca sonaba distinta. Pasó con dos reels ya
            # publicados. Ahora un 402 se trata como "esta cuenta no sirve, probá la
            # siguiente" (VozNoDisponible), no como "usá otra voz".
            def _charon():
                from src import voz_charon
                v, al = voz_charon.sintetizar_con_timing(script, out_dir / "voz.wav")
                log.info("Voz por Charon (Google AI Studio) + timing medido.")
                return v, al

            def _eleven(permitir_gratis: bool):
                for idx, ek in enumerate(voiceover.eleven_keys(), 1):
                    try:
                        v, al = voiceover.synthesize_timed(
                            script, ek, niche.elevenlabs_voice,
                            niche.elevenlabs_model, out_dir / "voz.mp3",
                            speed=getattr(niche, "voice_speed", 1.0),
                            permitir_voz_gratis=permitir_gratis)
                        log.info("Voz por ElevenLabs (cuenta %d)%s.", idx,
                                 " CON VOZ GRATIS" if permitir_gratis else " + timestamps")
                        return v, al
                    except voiceover.VozNoDisponible as e:
                        log.info("Cuenta %d no puede con la voz pedida (%s) -> pruebo la siguiente.",
                                 idx, str(e)[:60])
                    except Exception as e:  # noqa: BLE001
                        log.warning("ElevenLabs cuenta %d falló (%s).", idx, str(e)[:90])
                return None, {}

            # "auto" y "antonio" son hoy el mismo orden (ver docstring): Antonio primero,
            # Charon de resguardo. No se saca ninguno de los dos: sin respaldo, un 402
            # o una cuenta sin cuota descartaría el reel entero.
            # 10/11 (Tomix: "charon no vende"): Charon FUERA. Antonio -> Antoni.
            intentos = [("ElevenLabs/Antonio", lambda: _eleven(False))]
            # El último recurso va SIEMPRE al final.
            intentos.append(("voz gratis (Antoni)", lambda: _eleven(True)))

            for nombre, fn in intentos:
                try:
                    vo, alignment = fn()
                except Exception as e:  # noqa: BLE001
                    log.warning("%s falló (%s).", nombre, str(e)[:110])
                    vo = None
                if vo is not None:
                    break
            if vo is None:
                log.error("Ninguna cuenta de ElevenLabs pudo generar la voz -> descarto "
                          "el reel.")
            if vo is not None:
                # Si la voz ES más larga que el video, EXTENDER el video (congela el
                # último cuadro) ANTES de mezclar, para que la voz/CTA no se CORTEN.
                # Bug real: el reel de Chipre se cortó porque la voz medía ~9s más.
                vdur = videoedit.probe_duration(vo)
                if vdur + 0.4 > videoedit.probe_duration(final):
                    final = videoedit.extend_to_duration(final, vdur + 0.4, out_dir / "extendido.mp4")
                elif needs_dub:
                    # Al revés: la voz TERMINA ANTES que el video (típico al acelerarla).
                    # Como el doblaje reemplaza el audio, el resto quedaría en silencio
                    # absoluto -> se recorta el video al largo de la voz + un respiro.
                    final = videoedit.trim_to_duration(final, vdur + 1.2,
                                                       out_dir / "recortado.mp4")
                if needs_dub:
                    # Video con voz en INGLÉS: reemplazar el audio (sacar el inglés).
                    final = videoedit.replace_audio(final, vo, out_dir / "con_voz.mp4")
                    note = "doblado_es"
                else:
                    # Video MUDO/ambiente: mezclar la voz SOBRE el sonido de fondo,
                    # conservando el ASMR (agua, cosecha). NO borrar el ambiente.
                    final = videoedit.mix_voice_over(final, vo, out_dir / "con_voz.mp4")
                    note = "voz_generada_es"
                # SUBTÍTULOS quemados: la mayoría mira los reels SIN sonido. El timing
                # sale del alignment de ElevenLabs (exacto, sin transcribir).
                if alignment:
                    ass = subtitles.construir_ass(
                        alignment, out_dir / "subs.ass",
                        font=niche.subtitle_font, font_size=niche.subtitle_font_size,
                        outline=niche.subtitle_outline, margin_v=niche.subtitle_margin_v,
                        karaoke=niche.subtitle_karaoke, popin=niche.subtitle_popin,
                        colores=niche.subtitle_colores, emojis=niche.subtitle_emojis,
                        emoji_map=niche.subtitle_emoji_map,
                        palabras_por_grupo=niche.subtitle_palabras,
                        color=niche.subtitle_color,
                        minusculas=niche.subtitle_minusculas)
                    if ass:
                        final = videoedit.burn_subtitles(final, ass, out_dir / "con_subs.mp4")
                        note += "+subs"
            else:
                # REGLA DE ORO: sin voz en español NO se publica. Nunca sale inglés/crudo.
                log.error("Voz ES no generada (fallaron TODAS las cuentas de ElevenLabs) -> "
                          "DESCARTO el reel; no se publica el audio original.")
                from src import notify
                notify.alert(
                    "Sin voz para los reels",
                    "Fallaron TODAS las cuentas de ElevenLabs: los reels se descartan (nunca se "
                    "publica inglés). Hay que recargar creditos.",
                    dedup_key="voz_exhausted")
                return None, ("descartado_sin_voz_" + (lang if needs_dub else "mudo"))
        else:
            note = "audio_en_espanol"  # ya estaba en español o sin cambios

    if niche.add_mockup:
        mk = ROOT / niche.mockup_file
        if mk.exists():
            final = videoedit.overlay_last_secs(
                final, mk, niche.mockup_seconds, out_dir / "final.mp4",
                niche.mockup_scale, niche.mockup_position)
            note += "+mockup"
        else:
            log.warning("Mockup no encontrado (%s) -> se omite el overlay.", mk)

    # LOGO de la marca: va ÚLTIMO para que quede por encima de todo (subtítulos y
    # mockup incluidos) y visible durante todo el video.
    if niche.add_logo and niche.logo_file:
        lg = ROOT / niche.logo_file
        if lg.exists():
            final = videoedit.overlay_logo(final, lg, out_dir / "con_logo.mp4",
                                           niche.logo_scale, niche.logo_position)
            note += "+logo"
        else:
            log.warning("Logo no encontrado (%s) -> se omite.", lg)

    return final, note


def process_video(video: discover.VideoMeta, niche: Niche, secrets: Secrets,
                  dry_run: bool,
                  archivo_local: Path | None = None, voz: str = "auto",
                  reusar_analisis: bool = False) -> dict:
    """Produce UN reel del video de origen."""
    out_dir = ROOT / "output" / niche.name / video.id
    out_dir.mkdir(parents=True, exist_ok=True)
    dl_dir = ROOT / "downloads" / niche.name

    # 1. Descargar — salvo que el video ya esté en disco (tanda desde una carpeta).
    #    Se resuelve acá y no en un script aparte a propósito: todo lo que viene
    #    después (guard de idioma, doblaje, subtítulos, mockup, logo, guard
    #    anti-inglés del publisher) tiene que ser EL MISMO camino.
    if archivo_local is not None:
        video_path = Path(archivo_local)
        log.info("Video local: %s (no se descarga nada).", video_path.name)
    else:
        video_path = download.download_video(video.url, dl_dir)

    # 2. Gemini: análisis frame-by-frame.
    # `reusar_analisis`: para los videos que el modelo por defecto bloquea (finish_reason
    # RECITATION devuelve texto vacío). El análisis se consigue aparte con otro modelo,
    # se deja escrito acá y el pipeline sigue de largo con TODO lo demás igual.
    propio = out_dir / "descripcion_gemini.txt"
    cacheado = propio if (reusar_analisis and propio.is_file()
                          and len(propio.read_text(encoding="utf-8").strip()) > 500) else None
    if cacheado is not None:
        description = cacheado.read_text(encoding="utf-8")
        log.info("Reuso el análisis guardado en %s (%d chars): no llamo a Gemini.",
                 cacheado.name, len(description))
    else:
        description = analyze.analyze_video(
            video_path=video_path,
            prompt=niche.gemini_prompt,
            api_key=secrets.gemini_api_key,
            model=secrets.gemini_model,
        )
    (out_dir / "descripcion_gemini.txt").write_text(description, encoding="utf-8")

    # 2.5 Audio (doblaje/voz) + mockup del producto
    final_video, media_note = _process_media(video_path, description, niche, secrets, out_dir,
                                             voz=voz)
    if final_video is None:
        log.info("Ganador %s descartado por política de audio.", video.id)
        # Mismo esquema que el resto del historial (antes esta rama escribía
        # 'meta_reel_id', un nombre que ya nadie más usaba: era uno de los 15 formatos).
        return {"processed_at": _stamp(), "tiktok_url": video.url,
                "views": video.view_count, "title": video.title,
                "media": media_note, "facebook_id": None, "instagram_id": None,
                "instagram_queued": None, "youtube_id": None,
                "publish_state": "DESCARTADO",
                "skipped": media_note, "dry_run": dry_run}

    # El guion de voz, si este video tuvo (29/08, a pedido de Tomix): _process_media ya
    # lo escribió en disco unos pasos atrás (linea ~120, "guion_voz.txt") si el video
    # llevaba dob/voz en off. Se lee de ahí en vez de que _process_media lo devuelva
    # por separado: cambiar esa función (protegida, "anda") para un dato que ya queda
    # en disco es más riesgo del que hace falta.
    guion_path = out_dir / "guion_voz.txt"
    script = guion_path.read_text(encoding="utf-8").strip() if guion_path.is_file() else ""

    # 3. Copy de Facebook Ads (motor OpenAI o Gemini según el nicho)
    copy = copywrite.generate_copy(
        description=description,
        system_prompt=niche.gpt_prompt,
        engine=niche.copy_engine,
        openai_key=secrets.openai_api_key,
        openai_model=secrets.openai_model,
        gemini_key=secrets.gemini_api_key,
        gemini_model=secrets.gemini_model,
        cta_link=niche.cta_link,
        # Sin semilla siempre salía la MISMA estructura (la primera): los 58 copys
        # publicados tienen todos la misma forma. Con el id del video como semilla
        # cada reel rota entre las 5 estructuras.
        seed=str(out_dir.name),
        nicho=niche.name,
        script=script,
    )
    (out_dir / "copy_final.txt").write_text(copy, encoding="utf-8")
    # La nota de audio queda EN DISCO. Sin esto, un reel producido en dry-run (que no
    # entra al historial) después no se puede publicar: el guard anti-inglés pregunta
    # en qué idioma quedó, no lo encuentra y lo bloquea. Pasó con los 8 de Variety.
    (out_dir / "media.txt").write_text(media_note, encoding="utf-8")
    log.info("Artefactos guardados en %s (media: %s)", out_dir, media_note)

    # 3.5 Normalizar a specs seguras para Instagram/Facebook Reels
    final_video = videoedit.normalize_for_publish(final_video, out_dir / "publicar.mp4")

    # 4. Publicar. TODO lo de publicar vive en src/publisher.py: FB + IG + YouTube,
    #    botón de WhatsApp, guard anti-inglés (media_note tiene que empezar con
    #    doblado_es/voz_generada_es/audio_en_espanol) e idempotencia. En dry_run valida
    #    igual pero no toca ninguna API ni el historial.
    #    OJO: se le pasa media=media_note explícito porque el video recién se produjo y
    #    todavía no está en el historial; sin eso el guard no sabría en qué idioma quedó.
    res = publisher.publicar_reel(
        out_dir.name, niche, secrets,
        copy=copy, media=media_note,
        extra={"tiktok_url": video.url, "views": video.view_count, "title": video.title},
        dry_run=dry_run)
    if res.get("saltado"):
        log.info("Publicación de %s: %s%s", out_dir.name, res["saltado"],
                 f" ({res['error']})" if res.get("error") else "")

    record = publisher.persistible(res)      # el esquema único, sin ok/saltado/error
    record["dry_run"] = dry_run              # clave que ya traían los registros viejos
    if res.get("saltado") not in (None, "dry_run", "ya_publicado"):
        # El publisher NO anota el historial cuando corta antes de publicar (guard
        # anti-inglés, falta el mp4): así el reel se puede re-doblar y reintentar.
        # El pipeline SÍ tiene que anotarlo o volvería a descargar y a mandarle el mismo
        # video a Gemini en cada corrida, quemando cuota. Se anota con el motivo.
        record.setdefault("processed_at", _stamp())
        record.setdefault("media", media_note)
        record["skipped"] = res["saltado"]
        record.setdefault("publish_state", "DESCARTADO")
    return record


VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def run_carpeta(carpeta: Path, niche: Niche, secrets: Secrets, dry_run: bool = True,
                voz: str = "auto",
                limit: int | None = None, rehacer: bool = False,
                reusar_analisis: bool = False) -> list[dict]:
    """Procesa TODOS los videos de una carpeta del disco con el pipeline de siempre.

    Existe porque el agente solo sabía entrar por TikTok (descubrir -> descargar) y a
    veces la fuente ya está bajada a mano. Es la MISMA `process_video` de siempre: lo
    único que cambia es de dónde sale el archivo. Así no se pierde ningún guard.

    El id de cada reel es el nombre del archivo normalizado (`Rucula.mp4` -> `rucula`),
    para que el historial y la idempotencia funcionen igual que con los de TikTok.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        raise FileNotFoundError(f"No existe la carpeta: {carpeta}")
    archivos = sorted(p for p in carpeta.iterdir()
                      if p.is_file() and p.suffix.lower() in VIDEO_EXT)
    if limit:
        archivos = archivos[:limit]
    if not archivos:
        log.warning("No hay videos en %s", carpeta)
        return []

    hechos = _ya_generados(niche.name)
    log.info("Carpeta %s: %d videos | voz=%s | dry_run=%s",
             carpeta, len(archivos), voz, dry_run)

    resultados = []
    for i, arch in enumerate(archivos, 1):
        vid = re.sub(r"[^a-z0-9]+", "_", arch.stem.lower()).strip("_") or f"local_{i}"
        if vid in hechos and not rehacer:
            log.info("[%d/%d] %s ya está producido (output/%s/%s) -> lo salto.",
                     i, len(archivos), arch.name, niche.name, vid)
            continue
        log.info("[%d/%d] === %s -> id '%s' ===", i, len(archivos), arch.name, vid)
        meta = discover.VideoMeta(id=vid, url=arch.as_uri(), title=arch.stem,
                                  view_count=0, like_count=0, fuente=str(carpeta))
        try:
            rec = process_video(meta, niche, secrets, dry_run=dry_run,
                                archivo_local=arch, voz=voz,
                                reusar_analisis=reusar_analisis)
            rec["archivo_origen"] = arch.name
            resultados.append(rec)
        except Exception as e:  # noqa: BLE001
            log.error("[%d/%d] %s FALLÓ: %s", i, len(archivos), arch.name, str(e)[:200])
            resultados.append({"id": vid, "archivo_origen": arch.name,
                               "publish_state": "ERROR", "skipped": str(e)[:200]})
    return resultados


def _ya_generados(niche_name: str) -> set[str]:
    """IDs que ya tienen el video terminado en disco (output/<nicho>/<id>/publicar.mp4),
    aunque nunca se hayan publicado."""
    carpeta = ROOT / "output" / niche_name
    if not carpeta.is_dir():
        return set()
    return {d.name for d in carpeta.iterdir() if (d / "publicar.mp4").is_file()}


def _winners_de_carpeta(carpeta: Path, processed_ids: set, cuantos: int) -> list[discover.VideoMeta]:
    """Los videos de una carpeta local como si fueran "ganadores" descubiertos: mismo
    esquema que discover.find_winners, para que run() no tenga que distinguir de dónde
    salió cada uno. Sin vistas ni likes (no hay TikTok detrás): view_count queda en 0.

    El id sale del nombre de archivo normalizado, igual que en run_carpeta(), así el
    historial y la idempotencia (`already`) funcionan igual que con los de TikTok."""
    if not carpeta.is_dir():
        log.warning("Carpeta local de fuentes no existe: %s", carpeta)
        return []
    archivos = sorted(p for p in carpeta.iterdir()
                      if p.is_file() and p.suffix.lower() in VIDEO_EXT)
    out = []
    for i, arch in enumerate(archivos, 1):
        vid = re.sub(r"[^a-z0-9]+", "_", arch.stem.lower()).strip("_") or f"local_{i}"
        if vid in processed_ids:
            continue
        out.append(discover.VideoMeta(id=vid, url=arch.as_uri(), title=arch.stem,
                                      view_count=0, like_count=0, fuente=str(carpeta),
                                      local_path=str(arch)))
        if len(out) >= cuantos:
            break
    return out


def run(niche: Niche, secrets: Secrets, dry_run: bool = False,
        limit: int | None = None, saltear_generados: bool = False,
        uno_por_fuente: bool = False) -> None:
    already = state.processed_ids(niche.name)
    if saltear_generados:
        # Para que un dry-run traiga un video NUEVO en vez de rehacer el que ya está
        # producido y esperando. Apagado por defecto: si hace falta regenerar uno
        # (p.ej. salió sin doblar), se corre sin esta opción y lo vuelve a hacer.
        hechos = _ya_generados(niche.name)
        if hechos:
            log.info("Saltéo %d video(s) que ya están producidos en disco.", len(hechos))
            already = already | hechos
    cuantos = limit or (1 if uno_por_fuente else niche.top_k)
    if niche.solo_carpeta_local and (niche.carpeta_local or "").strip():
        # Única fuente: la carpeta local. No se toca TikTok/YouTube aunque tengan URL.
        log.info("Fuente: SOLO carpeta local (%s) — TikTok/YouTube apagados.", niche.carpeta_local)
        winners = _winners_de_carpeta(Path(niche.carpeta_local), already, cuantos)
    else:
        winners = discover.find_winners(
            profile_url=config.fuentes_de(niche),
            scan_count=niche.scan_count,
            # Con uno_por_fuente, top_k es cuántos SACAR DE CADA slot (no en total).
            top_k=cuantos,
            min_views=niche.min_views,
            processed_ids=already,
            uno_por_fuente=uno_por_fuente,
        )
    if not winners:
        return

    ok, fail = 0, 0
    for video in winners:
        log.info("=" * 60)
        log.info("Procesando ganador %s (%s vistas)", video.id, f"{video.view_count:,}")
        try:
            archivo_local = Path(video.local_path) if video.local_path else None
            record = process_video(video, niche, secrets, dry_run,
                                   archivo_local=archivo_local)
            if not dry_run:
                # El publisher ya escribió lo suyo apenas salió cada plataforma (para
                # que un corte no se lleve puesto un id). Esto se MERGEA encima en vez
                # de pisar: si el registro de disco quedó más completo que el que
                # devolvió process_video, no se pierde nada.
                previo = state.load_processed(niche.name).get(video.id) or {}
                previo.update(record)
                state.mark_processed(niche.name, video.id, previo)
            ok += 1
        except Exception as e:
            fail += 1
            log.exception("Falló %s: %s", video.id, e)

    log.info("=" * 60)
    log.info("Listo. OK=%d  Fallidos=%d  (dry_run=%s)", ok, fail, dry_run)
