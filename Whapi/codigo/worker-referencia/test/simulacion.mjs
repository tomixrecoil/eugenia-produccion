import w, { hmacHex } from "../src/index.js";
const store = new Map();
const R2 = {
  async get(k){ if(!store.has(k)) return null; const v=store.get(k); return {text:async()=>v, body:v}; },
  async put(k,v){ store.set(k, typeof v==="string"?v:String(v)); },
  async head(k){ return store.has(k)?{}:null; },
};
const env = { R2, WHATSAPP_TOKEN:"t", WHATSAPP_PHONE_ID:"PID", META_APP_SECRET:"sec", WA_VERIFY_TOKEN:"vt", GROQ_API_KEY:"g1", GROQ_API_KEY_2:"g2", OWNER_NUMBERS:"5492940000000" };
store.set("config/eugenia/venta_bonsai.txt","Te llamas EUGENIA. Precio {{PRECIO}} USD.");
store.set("config/eugenia/bonsai.json", JSON.stringify({precio:"19.97", descuento:80}));
const enviados=[]; let groqCalls=0;
globalThis.fetch = async (url, opt) => {
  const b = JSON.parse(opt.body);
  if (url.includes("groq")) { groqCalls++; if (opt.headers.Authorization==="Bearer g1") return new Response("{}",{status:429});
    const sys=b.messages[0].content; const first=!b.messages.some(m=>m.role==="assistant");
    return new Response(JSON.stringify({choices:[{message:{content: first? "**Buenas tardes** 🌿 Eugenia es mi nombre. ¿Ya tienes un bonsái? https://pay.hotmart.com/T97313346W?checkoutMode=10" : "Son 20 USD, pago único 🌿 [aquí](https://pay.hotmart.com/T97313346W?checkoutMode=10)"}}]}),{status:200}); }
  enviados.push(b); return new Response(JSON.stringify({messages:[{id:"wamid.out"+enviados.length}]}),{status:200});
};
const ctxs=[]; const ctx={waitUntil:p=>ctxs.push(p)};
// verify
let r = await w.fetch(new Request("https://x/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=42"), env, ctx);
console.log("verify", r.status, await r.text());
r = await w.fetch(new Request("https://x/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=MAL&hub.challenge=42"), env, ctx);
console.log("verify mal", r.status);
const mk = (m, field="messages") => ({object:"whatsapp_business_account",entry:[{id:"W",changes:[{field,value:m}]}]});
async function post(body, firmar=true){ const s=JSON.stringify(body); const h={"content-type":"application/json"}; if(firmar) h["x-hub-signature-256"]="sha256="+await hmacHex("sec",s);
  const r=await w.fetch(new Request("https://x/webhook/whatsapp",{method:"POST",headers:h,body:s}),env,ctx); await Promise.all(ctxs.splice(0)); return r.status; }
console.log("sin firma", await post(mk({}), false));
const m1 = {messaging_product:"whatsapp",contacts:[{profile:{name:"Sylvana"},wa_id:"5215512345678"}],messages:[{from:"5215512345678",id:"wamid.1",type:"text",text:{body:"Hola, quiero aprender las técnicas del Bonsái"},referral:{source_type:"ad",source_id:"AD1"}}]};
console.log("msg1", await post(mk(m1)));
console.log("dup", await post(mk(m1)));
const m2 = {...m1, messages:[{from:"5215512345678",id:"wamid.2",type:"text",text:{body:"cuánto sale?"}}]};
console.log("msg2", await post(mk(m2)));
console.log(JSON.stringify(enviados,null,1));
console.log("groq calls", groqCalls);
// echo -> pausa
console.log("eco", await post(mk({message_echoes:[{from:"549294",to:"5215512345678",id:"wamid.e1",type:"text",text:{body:"te escribo yo"}}]},"smb_message_echoes")));
const n=enviados.length;
await post(mk({...m1, messages:[{from:"5215512345678",id:"wamid.3",type:"text",text:{body:"ok"}}]}));
console.log("enviados tras eco (debe ser igual):", n, enviados.length);
// owner
store.set("stock/index.json", JSON.stringify([{nicho:"bonsai"},{nicho:"bonsai"},{nicho:"hidroponia"}]));
await post(mk({messages:[{from:"5492940000000",id:"wamid.o",type:"text",text:{body:"stock"}}]}));
console.log("owner:", enviados.at(-1).text.body);
// status failed
await post(mk({statuses:[{id:"wamid.out1",status:"failed",recipient_id:"549",errors:[{code:131047,title:"Re-engagement message"}]}]}));
console.log("fallos:", store.get("wa/fallos.json"));
// /v/ guard
console.log("/v guard", (await w.fetch(new Request("https://x/v/wa/clientes.json"),env,ctx)).status);
console.log(JSON.parse(store.get("wa/conv/5215512345678.json")).historial.map(h=>h.rol+": "+h.texto).join("\n"));
