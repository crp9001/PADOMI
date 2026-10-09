---
name: ruta-padomi
description: "Arma la ruta diaria de visitas PADOMI (EsSalud) desde Geoprog: un solo circuito desde PADOMI (Av. Arenales) y de vuelta a EsSalud. Úsala cuando el usuario pida su ruta PADOMI, Geoprog o la ruta del día, o pegue un texto que empieza con RUTA PADOMI."
---

# Ruta PADOMI (v4)

El skill instalado (cargador) ya actualizó el repositorio público `crp9001/PADOMI` en `padomi/`, mostró este archivo y `references/obras.md`, y corrió `preparar`. `$S` = `padomi/Ruta/scripts`. Los archivos del día van en la carpeta de trabajo, nunca en el repositorio. **Al repositorio no van pacientes, personal, placas, grifos ni claves: es público.**

## Reglas
- El usuario es el **conductor**; el especialista (doctor, licenciado o técnico) cambia. Memoria `/areas/padomi-conductor.md`: especialistas, grifos, unidades (placas) y avenidas que no se cruzan a pie.
- Todo desde el **celular**: mensajes cortos, en español. Lo urgente es el **1er paciente**: junta en un mensaje las llamadas independientes y no narres los pasos.
- **Nunca** escribas ni guardes el usuario o la clave de Geoprog. Los pacientes son solo para la ruta del día: no van a memoria ni a artifacts.
- **Fecha:** hora de Lima. Si `fecha_distinta_a_hoy`, dilo en la primera línea; si `despues_de_6pm` y es hoy, pregunta si es para hoy o mañana.
- **El orden lo pone el script** (tiempos por calle, tráfico por hora y sentido, pequeños grupos, a pie primero). No reordenes a mano.
- **A pie:** a 40 m o menos y sin cruzar avenida ancha, la unidad no se mueve ("🚶 A pie desde la N"). Pasa siempre `--ancha "A,B"` con las avenidas de la memoria; si el usuario nombra otra, guárdala ahí.
- **Salida:** PADOMI, Av. Arenales 1302. **Llegada:** el script elige el acceso de EsSalud más rápido según por dónde llegas (`data/accesos.json`).

## Ruta nueva
Si `igual_a_la_anterior` y ya hay ruta, dilo en media línea y no recalcules. Si hay `cambios` y `ya_hay_ruta_de_ese_dia`, ve a **En plena ruta**.
1. **En un mensaje:** `places_search` de cada dirección de `places_search` (`max_results: 1`, hasta 10 por llamada); `WebFetch` de cada `webfetch.consultas[].url` con `webfetch.prompt` tal cual; y, si es la primera ruta del día, 1 búsqueda web de obras en las avenidas de la zona (según `obras.md`).
2. **Un solo Bash**, sin pensar el orden:
   ```
   cat > lugares_<fec>.txt <<'EOF'
   <lat> <lng> <place_id o -> <d|o> <dirección>
   EOF
   cat > <guardar_en> <<'EOF'
   {"code":"Ok","durations":[...]}
   EOF
   python3 $S/ruta_padomi.py ruta <fec> --especialista "Nombre Apellido" --ancha "..."
   ```
   Una línea por lugar: `d` si `types` trae `street_address`, `premise` o `subpremise`; si no, `o`. `place_id` solo si empieza con `ChIJ`. La dirección tal cual (sin ", Peru"). Una respuesta de WebFetch que falló se omite: el script avisa y usa línea recta. `--salida HH:MM` solo para planear a otra hora.
3. Solo si `revisar_grafico` no es `false`: mira el PNG con Read, corrige `etiquetas_<fec>.json` y corre `python3 $S/grafico_ruta.py ruta_<fec>.json etiquetas_<fec>.json <png>`.
4. **Entrega.**

## Especialista
`tecnico_apoyo` "NN" → línea `Tec. Apoyo NN` de la memoria; si `prof` es un nombre, búscalo por nombre (`¥` = `Ñ`). Sin nombre registrado: sigue y al final pregunta "¿Cómo se llama la persona del código <código>?" (nunca la clave); guarda solo nombre y 1er apellido (`- [stated] <código> — <Nombre Apellido> · Tec. Apoyo NN`).

## Entrega (en este orden, sin pasos en medio)
1. `SendUserMessage`: "Hoy vas con <Nombre> (código <C. MAPA>)." + una línea de **ida** (evitando obras) + el **PRIMER MENSAJE** tal cual + "🚐 ¿Qué placa tiene hoy la unidad?" (si no la dio hoy).
2. `SendUserMessage`: la **lista** tal cual (puedes corregir una dirección rara, sin tocar enlaces ni números). La 1ª parada va sola con su 🧭 y el **🗺️ Tramo 1 arranca en la 2**.
3. `SendUserFile` con el PNG (`display: render`). Nunca como artifact.
4. `places_map_display_v0` con el JSON de MAPA tal cual.
5. Final corto: obras en el recorrido con su fuente (si hay) y el cierre: "🗺️ = tramo de hasta 5 paradas; 🧭 = un solo paciente. Si Google Maps se cierra a mitad de tramo, usa el 🧭 del siguiente; si el 🗺️ abre en el navegador, usa los 🧭. Si agregan pacientes, pégame la lista nueva y dime en qué número vas."

## Placa y combustible (después del 1er paciente; nunca en el penúltimo)
Dos grifos fijos y unidades que cambian; todo está en la memoria ("Grifos" y "Unidades").
1. **Placa** en mayúsculas, sin espacios ni guion; búscala en "Unidades". En un solo mensaje:
   - Registrada: "Esta unidad carga <combustible> en el grifo <nombre>. **¿Vas a recargar hoy?**"
   - Nueva: "**¿Qué combustible usa?** (<grifo 1>: <combustibles> · <grifo 2>: <combustibles>) **¿Vas a recargar hoy?**" Con la respuesta, agrega `- [stated] <PLACA> — <Grifo> (<combustible>)` en "Unidades" (el grifo sale del combustible).
2. **Sí recarga:** `python3 $S/ruta_padomi.py grifo <fec> --en=LAT,LNG,PLACE_ID --nombre "<Grifo>"` y manda la línea REGRESO CON RECARGA tal cual. El script decide: grifo primero si queda antes que EsSalud (o casi igual, 300 m); si EsSalud queda más cerca, primero se deja al especialista y luego el grifo. Queda guardado para los recálculos. La lista suma la recarga al tiempo total (tramos al grifo y de vuelta con el tráfico de la hora + `MIN_RECARGA` en el grifo); con `ruta <fec>` se recalculan los tiempos desde ahora.
3. **No recarga** (tanque lleno): la lista ya trae el regreso directo. Si antes dijo que sí: `grifo <fec> --ninguno` y manda REGRESO SIN RECARGA.
4. Sin respuesta: regreso sin recarga; pregunta de nuevo una vez en la siguiente entrega. Si un grifo no tiene coordenadas en la memoria, sácalas de su enlace (WebFetch: la redirección trae `/place/<lat>,<lng>` o el nombre; luego `places_search`) y guárdalas.

## En plena ruta
1. Con `cambios`, pregunta "¿En qué número de paciente vas?" (salvo que ya lo dijo).
2. **En un mensaje:** `python3 $S/ruta_padomi.py plan <fec> --voy N` + `places_search` de las direcciones nuevas. Si `plan` trae URLs (solo de los nuevos), WebFetch de cada una.
3. **Un solo Bash:** `cat >> lugares_<fec>.txt` con los lugares nuevos, cada respuesta en su `guardar_en` y `python3 $S/ruta_padomi.py ruta <fec> --voy N --especialista "..." --ancha "..."`. Da por atendidas 1 a N, marca 🆕 y avisa los que ya no figuran.
4. **Entrega corta, mismo orden:** PRIMER MENSAJE con "Quedan X pacientes (Y nuevos)" y los atendidos tachados (`~~1 Apellido~~ · ~~2 Apellido~~`); lista, gráfico y mapa. Si ya no se puede evitar volver a una zona, dilo.
5. Solo reordenar (mismo N, sin nuevos): `ruta <fec> --voy N`.
6. Sin `ruta_<fec>.json` (otra conversación): pide su ubicación (herramienta del dispositivo) y a quiénes ya atendió; `preparar`, `plan` y `ruta` con `--gps=LAT,LNG --quitar "Apellido1,Apellido2"`.

## Ubicación
No hay GPS en segundo plano. Si pregunta "¿cómo voy?", pide su ubicación y dile la siguiente parada, la distancia y si hay que llamar antes. Recuérdale escribir solo detenido.

## Ajustes
- **Tráfico:** factores por hora, día y sentido en `data/trafico.json`. Si dice que una franja o un sentido le tomó más o menos, ajústalos ahí.
- **Accesos:** `data/accesos.json` (si cambian, hay que volver a medir su tabla).
- **Favorito `rutapadomi`** y ruta desde la computadora: en el cargador instalado, no en este repositorio.

## Actualizar este skill
Edita `padomi/Ruta/`, prueba con una copia de los datos del día en otra carpeta (nunca sobre la ruta en uso), revisa que no lleve datos privados y súbelo sin pedir confirmación: `mcp__claude-code-remote__add_repo` (owner `crp9001`, repo `PADOMI`, access `push`), luego `git -C padomi fetch -q origin main && git -C padomi rebase -q origin/main`, `git -C padomi add Ruta && git -C padomi commit -m "<qué cambió>" && git -C padomi push -q origin HEAD:main`. La próxima conversación ya lo usa: el cargador siempre lee esta versión.
