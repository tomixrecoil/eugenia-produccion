---
tags: [whapi, github, automatizacion]
---

# GitHub Actions (todo ✅)

| Repo | Workflow | Cuándo | Qué hace | Timeout |
|---|---|---|---|---|
| `eugenia-produccion` | `fuentes.yml` "Catalogar fuentes" | `0 4 * * *` = 01:00 ART + manual | Baja 8 videos nuevos por nicho y revisa 15 fuentes sin verificar (Gemini) | 40 min |
| `eugenia-produccion` | `producir.yml` "Producir reels" | `0 5 * * *` = 02:00 ART + manual (`nicho`, `cantidad`) | Produce reels y los deja en el stock de R2 | 75 min (cuida los 2.000 min/mes) |
| `eugenia-produccion` | `producir.yml` → paso **Subir a YouTube lo publicado** | después de producir (corre aunque falle) | `subir_youtube_nube.py`. Input `solo_youtube` = subir sin producir | — |
| `eugenia-produccion` | `diagnostico.yml` | manual | Prueba las 5 cuentas de ElevenLabs (~4 caracteres c/u) | 5 min |
| `eugenia-carritos` | `carritos.yml` | `0 10 * * *` = 07:00 ART + manual | Carritos abandonados → `/ingest` | — |

- `fuentes` y `producir` comparten `concurrency: group: produccion` → nunca escriben R2 a la vez.
- Ambos acceden a R2 solo por la puerta (`PUERTA_R2_URL` variable, `PUERTA_R2_KEY` secreto).
- Desde el 02/11/2026 ambos leen la bóveda (`BOVEDA_PRODUCCION_KEY`) y los ajustes de nicho de R2 antes de arrancar.
- Logs como artifact `agent.log` (3 días).
- `eugenia-produccion` es un **export**: se edita en `marketing-agent` y se vuelve a exportar con `exportar_produccion.py`.
