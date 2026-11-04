# Eugenia — producción en la nube

Arma los reels de hidroponía y bonsái todos los días a las 02:00 (Argentina) y los deja
en el stock de R2. Publicarlos lo hace el Worker de Cloudflare, no esto.

Este repo es una COPIA PARCIAL de `marketing-agent`, generada con `exportar_produccion.py`.
No se edita acá: se cambia allá y se vuelve a exportar.

Acá NO hay datos de clientes ni credenciales. Las claves son secrets de GitHub y R2 se
toca solo a través de la puerta `eugenia-puerta-r2`, que no deja ver los datos de clientes.

Probar uno a mano: Actions → "Producir reels" → Run workflow (nicho y cantidad 1).
