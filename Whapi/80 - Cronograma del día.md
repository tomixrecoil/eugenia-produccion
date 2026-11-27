---
tags: [whapi, operacion, horarios]
---

# Cronograma de un día (hora Argentina, UTC−3)

| Hora ART | UTC | Qué corre | Dónde | Certeza |
|---|---|---|---|---|
| Todo el día | | **Eugenia contesta cada mensaje** en segundos | Worker (webhook) | 🟡 |
| Cada 10 min | | Cron del Worker: cola de Instagram (`queue/<fecha>.json`, `publish_at`) y stock | Worker | ✅ |
| 01:00 | 04:00 | Catalogar fuentes de TikTok | GitHub `fuentes.yml` | ✅ |
| 02:00 | 05:00 | Producir reels (cupo repartido al nicho con menos stock, hasta 20 en stock) | GitHub `producir.yml` | ✅ |
| ~02:30 | ~05:30 | Subir a YouTube lo ya publicado (`subir_youtube_nube.py`) | GitHub `producir.yml` | ✅ |
| 06:00 | 09:00 | Publicación del stock (hora 1 por defecto) | Worker | ✅ (`toggles.HORAS_DEFAULT`) |
| 07:00 | 10:00 | Descubrir carritos abandonados → `/ingest` | GitHub `carritos.yml` | ✅ |
| 08:00 | 11:00 | Mails de recuperación de carritos | Worker `eugenia-mail-recuperacion` | ✅ |
| 09:00 | 12:00 | `schedule_times` de hidroponía (PC) | PC | ✅ (`niches/hidroponia.yaml`) |
| 18:00 | 21:00 | Publicación del stock (hora 2) + `schedule_times` de ambos nichos | Worker / PC | ✅ |
| Al publicar cada reel | | Aviso por WhatsApp a Tomix | `notify.whatsapp` | ✅ |
| Cuando prende la PC | | Tareas `AgenteMarketing_*` (vigilancia, precios, recordatorio…) | Windows | ✅ nombres |
