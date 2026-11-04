---
tags: [whapi, backend, pc]
---

# Backend — PC `marketing-agent` (Windows "MYX")

## Estructura conocida (✅ referencias)

```
marketing-agent/
├── .env                      credenciales (+ .env.bak_*)
├── config.py                 (exportado a eugenia-produccion)
├── webapp.py                 panel web → [[50 - Frontend - Panel web]]
├── cloudflare-worker/        código + wrangler.toml del Worker de Eugenia
├── nube/                     copias vivas de los workflows (producir.yml…)
├── exportar_produccion.py    genera el repo eugenia-produccion
├── analisis/COMENTARIOS_IG.md
├── niches/*.yaml  prompts/*  src/*  state/*
├── monitor_ventas.py         avisa ventas
├── sync_precios.py           scrapea precios por país del checkout de Hotmart
├── encolar_stock.py, productor_diario.py, programar_semana.py, postear_ganadores.py
├── leer_emails.py, drive_cursos.py
├── src/local_tts.py          cliente del XTTS local (voz de Eugenia)
├── CUENTAS_API.md, VAULT_CREDENCIALES.md
└── PANEL_KEY.txt
```

## Tareas programadas de Windows (✅ `config.py:969-979`)

Prefijo `AgenteMarketing_`: `boletos` (mails), `precios` (escaneo de precios), `precio_watch`,
`recordatorio` (diario), `vigilancia` (salud), `topup`, y una por nicho para producción.

## Qué parte del WhatsApp depende de la PC

| Depende de la PC | No depende (nube) |
|---|---|
| Editar prompts/reglas/credenciales | Contestar mensajes (Worker) |
| Producir reels con carpeta local | Publicar del stock (Worker cron) |
| Notas de voz XTTS | Carritos (GitHub + Worker) |
| Subir ventas de Hotmart al panel | Comentarios IG → DM (Worker) |
| Alertas de `notify.py` desde tareas locales | Producción diaria (GitHub) |
