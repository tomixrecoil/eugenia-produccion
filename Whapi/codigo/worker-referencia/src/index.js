// Worker de referencia para replicar a Eugenia (WhatsApp Cloud API + coexistencia).
// NO es una copia del Worker en producción (ese vive en marketing-agent/cloudflare-worker,
// en la PC): es una implementación limpia y completa del mismo pipeline, para arrancar de cero.
// Ver Whapi/61 - Código de referencia - Worker WhatsApp.md

const GRAPH = (env) => `https://graph.facebook.com/${env.GRAPH_VERSION || "v21.0"}`;
const MODELOS = ["openai/gpt-oss-20b", "qwen/qwen3.6-27b", "groq/compound-mini"];
const PAUSA_HUMANO_MS = 12 * 3600 * 1000; // si Tomix escribe a mano, el bot calla 12 h
const MAX_HISTORIAL = 20;

// ---------------------------------------------------------------- utilidades
const enc = new TextEncoder();

async function hmacHex(secreto, cuerpo) {
  const k = await crypto.subtle.importKey("raw", enc.encode(secreto), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const firma = await crypto.subtle.sign("HMAC", k, enc.encode(cuerpo));
  return [...new Uint8Array(firma)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function igualSeguro(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

async function leerJSON(env, key, def) {
  const o = await env.R2.get(key);
  if (!o) return def;
  try { return JSON.parse(await o.text()); } catch { return def; }
}

const guardarJSON = (env, key, data) =>
  env.R2.put(key, JSON.stringify(data), { httpMetadata: { contentType: "application/json" } });

// País -> zona horaria (para el saludo por hora local). Ampliar según tu público.
const ZONAS = [
  ["549", "America/Argentina/Buenos_Aires"], ["54", "America/Argentina/Buenos_Aires"],
  ["52", "America/Mexico_City"], ["57", "America/Bogota"], ["51", "America/Lima"],
  ["56", "America/Santiago"], ["58", "America/Caracas"], ["593", "America/Guayaquil"],
  ["591", "America/La_Paz"], ["595", "America/Asuncion"], ["598", "America/Montevideo"],
  ["506", "America/Costa_Rica"], ["502", "America/Guatemala"], ["503", "America/El_Salvador"],
  ["504", "America/Tegucigalpa"], ["505", "America/Managua"], ["507", "America/Panama"],
  ["34", "Europe/Madrid"], ["1", "America/New_York"],
];
const PAIS = { "54": "Argentina", "52": "México", "57": "Colombia", "51": "Perú", "56": "Chile", "58": "Venezuela" };

function contextoLocal(waId) {
  const [pref, tz] = ZONAS.find(([p]) => waId.startsWith(p)) || ["", "America/Argentina/Buenos_Aires"];
  const hora = Number(new Intl.DateTimeFormat("es", { hour: "numeric", hour12: false, timeZone: tz }).format(new Date()));
  const saludo = hora < 12 ? "Buen día" : hora < 20 ? "Buenas tardes" : "Buenas noches";
  const pais = PAIS[pref.slice(0, 2)] || PAIS[pref] || "";
  return { tz, hora, saludo, pais };
}

// ---------------------------------------------------------------- WhatsApp API
async function waPost(env, body) {
  const r = await fetch(`${GRAPH(env)}/${env.WHATSAPP_PHONE_ID}/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.WHATSAPP_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ messaging_product: "whatsapp", ...body }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) console.log("WA error", r.status, JSON.stringify(j).slice(0, 300));
  return j;
}

const enviarTexto = (env, to, texto, preview = true) =>
  waPost(env, { recipient_type: "individual", to, type: "text", text: { preview_url: preview, body: texto.slice(0, 4096) } });

const marcarLeidoYEscribiendo = (env, wamid) =>
  waPost(env, { status: "read", message_id: wamid, typing_indicator: { type: "text" } });

// ---------------------------------------------------------------- Groq
async function groq(env, mensajes) {
  const claves = [env.GROQ_API_KEY, env.GROQ_API_KEY_2, env.GROQ_API_KEY_3].filter(Boolean);
  for (const modelo of MODELOS) {
    for (const clave of claves) {
      try {
        const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
          method: "POST",
          headers: { Authorization: `Bearer ${clave}`, "Content-Type": "application/json" },
          body: JSON.stringify({ model: modelo, messages: mensajes, temperature: 0.7, max_tokens: 700 }),
        });
        if (r.status === 429 || r.status >= 500) continue; // sin cupo o caído: siguiente cuenta
        if (!r.ok) break;                                   // error del modelo: siguiente modelo
        const j = await r.json();
        const txt = j.choices?.[0]?.message?.content?.trim();
        if (txt) return txt;
      } catch (e) { console.log("groq", modelo, String(e).slice(0, 120)); }
    }
  }
  return null;
}

// ---------------------------------------------------------------- nicho y prompt
function detectarNicho(texto, referral) {
  const t = `${texto} ${referral?.headline || ""} ${referral?.body || ""}`.toLowerCase();
  if (/bons[aá]i|[aá]rbol|alambr|poda/.test(t)) return "bonsai";
  if (/hidrop|cultiv|lechug|nft|torre|nutrient/.test(t)) return "hidroponia";
  return null;
}

// Origen de Hotmart (config.sck): máx 30, sin "_", separador "-". Solo para links de hotmart.
function conOrigen(texto, origen) {
  return texto.replace(/https:\/\/pay\.hotmart\.com\/[^\s]+/g, (u) =>
    u.includes("sck=") ? u : `${u}${u.includes("?") ? "&" : "?"}sck=${origen.slice(0, 30)}`);
}

async function armarPrompt(env, nicho, conv, ctx) {
  const cfg = await leerJSON(env, `config/eugenia/${nicho}.json`, {});
  let sistema = (await env.R2.get(`config/eugenia/venta_${nicho}.txt`).then((o) => o?.text())) || "";
  sistema = sistema
    .replaceAll("{{PRECIO}}", cfg.precio || "")
    .replaceAll("{{QUE_INCLUYE}}", cfg.que_incluye || "")
    .replaceAll("{{DATOS_COBRO}}", cfg.datos_cobro || "");

  const situacion = [];
  situacion.push(`Hora local del cliente: ${ctx.hora}h → saludo "${ctx.saludo}".`);
  if (ctx.pais) situacion.push(`País probable: ${ctx.pais}.`);
  if (!conv.historial.some((m) => m.rol === "eugenia")) situacion.push("Es el PRIMER mensaje de la charla.");
  if (conv.link_enviado) situacion.push("Ya se le mandó precio y enlace antes: no lo repitas salvo que lo pida.");
  if (conv.origen?.tipo === "ad") situacion.push("Llegó desde un anuncio que ya lo saludó: no te presentes de nuevo.");
  const ultimo = conv.historial.at(-1)?.texto?.toLowerCase() || "";
  if (/caro|descuento|no me alcanza|no tengo (la )?plata|no tengo dinero/.test(ultimo) && cfg.descuento)
    situacion.push(`Mencionó el precio: puedes decir UNA vez que hay un ${cfg.descuento}% de descuento ya aplicado. Sin urgencia.`);
  if (ctx.pais === "Argentina" && cfg.transferencia_ar)
    situacion.push(`Si quiere pagar desde Argentina, ofrece transferencia: ${cfg.transferencia_ar}`);

  const msgs = [{ role: "system", content: `${sistema}\n\n[SITUACIÓN]\n${situacion.join("\n")}${cfg.catalogo ? `\n\nCATÁLOGO:\n${cfg.catalogo}` : ""}` }];
  for (const m of conv.historial.slice(-MAX_HISTORIAL)) {
    msgs.push({ role: m.rol === "cliente" ? "user" : "assistant", content: m.texto });
  }
  return { msgs, cfg };
}

// ---------------------------------------------------------------- reglas post-proceso
function postProceso(texto, conv, cfg) {
  let t = texto.trim().replace(/^["“]|["”]$/g, "");
  t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, "$2"); // markdown link -> URL pelada
  t = t.replace(/\*\*?([^*]+)\*\*?/g, "$1");                  // sin negritas/asteriscos
  if (cfg.precio) t = t.replace(/\b\d{1,3}(?:[.,]\d{1,2})?\s?(?:USD|d[oó]lares)/gi, `${cfg.precio} USD`);
  const links = [...new Set(t.match(/https?:\/\/\S+/g) || [])];
  const esPrimero = !conv.historial.some((m) => m.rol === "eugenia");
  if (esPrimero && links.length) { for (const l of links) t = t.replaceAll(l, ""); return { cuerpo: t.trim(), link: null }; }
  let link = links[0] || null;
  if (link) for (const l of links) t = t.replaceAll(l, "");    // un solo link, y va aparte
  t = t.replace(/\n{3,}/g, "\n\n").trim();
  if (t.length > 600) t = t.slice(0, t.lastIndexOf(" ", 600)) + "…";
  return { cuerpo: t, link };
}

// ---------------------------------------------------------------- flujo de un mensaje
async function procesarMensaje(env, msg, contacto) {
  const waId = msg.from;
  // 1) dedupe por wamid
  if (await env.R2.head(`wa/vistos/${msg.id}`)) return;
  await env.R2.put(`wa/vistos/${msg.id}`, "1");

  // 2) dueño -> órdenes
  const duenos = (env.OWNER_NUMBERS || "").split(",").map((s) => s.trim()).filter(Boolean);
  const texto = msg.type === "text" ? msg.text.body
    : msg.type === "button" ? msg.button.text
    : msg.type === "interactive" ? (msg.interactive.button_reply?.title || msg.interactive.list_reply?.title || "")
    : msg.type === "image" ? `[envió una imagen]${msg.image?.caption ? " " + msg.image.caption : ""}`
    : msg.type === "audio" ? "[envió un audio]" : `[${msg.type}]`;
  if (duenos.includes(waId)) return ordenDueno(env, waId, texto);

  // 3) estado de la charla
  const key = `wa/conv/${waId}.json`;
  const conv = await leerJSON(env, key, { wa_id: waId, historial: [], creado: new Date().toISOString() });
  conv.historial.push({ rol: "cliente", t: new Date().toISOString(), texto, wamid: msg.id });
  conv.ultimo_entrante = new Date().toISOString();
  if (msg.referral && !conv.origen) conv.origen = { tipo: msg.referral.source_type, ad_id: msg.referral.source_id, ctwa_clid: msg.referral.ctwa_clid };
  conv.nicho = conv.nicho || detectarNicho(texto, msg.referral) || env.NICHO_DEFAULT || "hidroponia";
  if (contacto?.profile?.name) conv.nombre_perfil = contacto.profile.name; // NO usar como nombre real

  const pausado = conv.pausado_hasta && Date.parse(conv.pausado_hasta) > Date.now();
  const comprador = conv.comprador === true;
  if (pausado || comprador && !/acceso|no me lleg|contrase/i.test(texto)) { await guardarJSON(env, key, conv); return; }

  // 4) leído + escribiendo
  await marcarLeidoYEscribiendo(env, msg.id);

  // 5) prompt + LLM
  const ctx = contextoLocal(waId);
  const { msgs, cfg } = await armarPrompt(env, conv.nicho, conv, ctx);
  const crudo = await groq(env, msgs);
  if (!crudo) { await guardarJSON(env, key, conv); return; } // sin respuesta: mejor callar que mandar basura

  // 6) reglas + origen
  const { cuerpo, link } = postProceso(crudo, conv, cfg);
  const linkFinal = link ? conOrigen(link, "wa-euge") : null;

  // 7) enviar (texto, pausa, link solo -> se ve la tarjeta del curso)
  const salidas = [];
  if (cuerpo) salidas.push(await enviarTexto(env, waId, cuerpo, false));
  if (linkFinal) {
    await new Promise((r) => setTimeout(r, 1500));
    salidas.push(await enviarTexto(env, waId, linkFinal, true));
    conv.link_enviado = true;
  }
  const wamids = salidas.map((s) => s?.messages?.[0]?.id).filter(Boolean);
  conv.historial.push({ rol: "eugenia", t: new Date().toISOString(), texto: [cuerpo, linkFinal].filter(Boolean).join("\n\n"), wamid: wamids.join(",") });
  conv.historial = conv.historial.slice(-60);
  await guardarJSON(env, key, conv);
}

async function procesarEco(env, eco) {
  // Tomix contestó desde la app del celular (coexistencia): se guarda y Eugenia se pausa.
  const key = `wa/conv/${eco.to}.json`;
  const conv = await leerJSON(env, key, { wa_id: eco.to, historial: [] });
  if (conv.historial.some((m) => m.wamid === eco.id)) return;
  conv.historial.push({ rol: "humano", t: new Date().toISOString(), texto: eco.text?.body || `[${eco.type}]`, wamid: eco.id });
  conv.pausado_hasta = new Date(Date.now() + PAUSA_HUMANO_MS).toISOString();
  await guardarJSON(env, key, conv);
}

async function procesarEstado(env, st) {
  if (st.status !== "failed") return;
  const code = st.errors?.[0]?.code;
  console.log("WA failed", st.recipient_id, code, st.errors?.[0]?.title);
  const log = await leerJSON(env, "wa/fallos.json", []);
  log.push({ t: new Date().toISOString(), to: st.recipient_id, wamid: st.id, code, title: st.errors?.[0]?.title });
  await guardarJSON(env, "wa/fallos.json", log.slice(-500));
}

// ---------------------------------------------------------------- modo dueño
async function ordenDueno(env, waId, texto) {
  const t = texto.trim().toLowerCase();
  let r;
  if (t === "stock") {
    const idx = await leerJSON(env, "stock/index.json", []);
    const por = idx.reduce((a, x) => ((a[x.nicho] = (a[x.nicho] || 0) + 1), a), {});
    r = `Stock: ${Object.entries(por).map(([n, c]) => `${n} ${c}`).join(" · ") || "vacío"}`;
  } else if (t.startsWith("pausa ")) {
    const tel = t.split(" ")[1];
    const k = `wa/conv/${tel}.json`;
    const c = await leerJSON(env, k, { wa_id: tel, historial: [] });
    c.pausado_hasta = new Date(Date.now() + 30 * 24 * 3600 * 1000).toISOString();
    await guardarJSON(env, k, c); r = `Eugenia pausada con ${tel}.`;
  } else if (t.startsWith("reanudar ")) {
    const tel = t.split(" ")[1];
    const k = `wa/conv/${tel}.json`;
    const c = await leerJSON(env, k, null);
    if (c) { c.pausado_hasta = null; await guardarJSON(env, k, c); }
    r = `Eugenia reanudada con ${tel}.`;
  } else {
    r = "Órdenes: stock · pausa <tel> · reanudar <tel>";
  }
  await enviarTexto(env, waId, r, false);
}

// ---------------------------------------------------------------- HTTP
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);

    // Videos públicos para Instagram: SOLO reels/<nombre plano>.mp4 (nunca wa/…)
    if (url.pathname.startsWith("/v/")) {
      const key = decodeURIComponent(url.pathname.slice(3));
      if (!/^reels\/[\w.-]+\.mp4$/.test(key)) return new Response("no", { status: 404 });
      const o = await env.R2.get(key);
      return o ? new Response(o.body, { headers: { "content-type": "video/mp4" } }) : new Response("no", { status: 404 });
    }

    if (url.pathname === "/webhook/whatsapp") {
      if (req.method === "GET") {
        const ok = url.searchParams.get("hub.mode") === "subscribe" && url.searchParams.get("hub.verify_token") === env.WA_VERIFY_TOKEN;
        return ok ? new Response(url.searchParams.get("hub.challenge")) : new Response("forbidden", { status: 403 });
      }
      if (req.method === "POST") {
        const crudo = await req.text();
        const firma = (req.headers.get("x-hub-signature-256") || "").replace("sha256=", "");
        if (!firma || !igualSeguro(firma, await hmacHex(env.META_APP_SECRET, crudo))) return new Response("firma", { status: 401 });
        let body; try { body = JSON.parse(crudo); } catch { return new Response("json", { status: 400 }); }
        ctx.waitUntil(despachar(env, body)); // responder 200 YA; el trabajo sigue en segundo plano
        return new Response("ok");
      }
    }

    if (url.pathname === "/salud") return new Response("ok");
    return new Response("not found", { status: 404 });
  },

  async scheduled(evento, env, ctx) {
    // Acá va el cron (cada 10 min): publicar la cola de Instagram, seguimientos, etc.
    console.log("cron", evento.cron, new Date().toISOString());
  },
};

async function despachar(env, body) {
  if (body.object !== "whatsapp_business_account") return;
  for (const entry of body.entry || []) {
    for (const ch of entry.changes || []) {
      const v = ch.value || {};
      try {
        if (ch.field === "messages") {
          for (const st of v.statuses || []) await procesarEstado(env, st);
          for (const m of v.messages || []) {
            const contacto = (v.contacts || []).find((c) => c.wa_id === m.from);
            await procesarMensaje(env, m, contacto);
          }
        } else if (ch.field === "smb_message_echoes") {
          for (const e of v.message_echoes || []) await procesarEco(env, e);
        }
      } catch (e) { console.log("despachar", String(e).slice(0, 300)); }
    }
  }
}

export { postProceso, detectarNicho, conOrigen, contextoLocal, hmacHex };
