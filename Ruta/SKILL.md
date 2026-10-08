---
name: ruta-padomi
description: "Arma la ruta diaria de visitas PADOMI (EsSalud) desde Geoprog: un solo circuito desde y hacia PADOMI Av. Arenales. Úsala cuando el usuario pida su ruta PADOMI, Geoprog o la ruta del día, o pegue un texto que empieza con RUTA PADOMI."
---

# Ruta PADOMI (v3)

## Contexto
- El usuario es el **conductor** de una unidad PADOMI; el especialista que va con él (doctor, licenciado o técnico) cambia. Registro de especialistas y preferencias: memoria `/areas/padomi-conductor.md`.
- **Salida y llegada:** PADOMI, Av. Arenales 1302, Jesús María. **Retorno siempre por Av. Arenales** (el script pone un punto de paso en la cdra 5).
- Todo lo hace **desde el celular** mientras trabaja: respuestas cortas, en español, fáciles de leer. Es común que **agreguen pacientes en el camino**.

## Reglas fijas
- **Nunca escribas ni guardes el usuario o la clave** de Geoprog.
- **Pacientes confidenciales:** solo para la ruta del día; no van a memoria ni a artifacts. En el mapa solo número y dirección; en el gráfico PNG sí el 1er apellido.
- **Fecha:** hoy, hora de Lima. Si `fecha_distinta_a_hoy`, dilo en la primera línea; si `despues_de_6pm` y es hoy, pregunta si es para hoy o mañana.
- **El orden lo pone el script** (tiempos reales por calle, pequeños grupos, a pie primero). No lo reordenes a mano ni reescribas los scripts.
- **A pie primero** (pedido del usuario): si el siguiente paciente está a **40 m o menos** y no hay que cruzar una avenida ancha, la unidad no se mueve y el especialista cruza caminando. El script lo marca "🚶 A pie desde la N" y deja esas paradas fuera del 🗺️ del tramo. Avenidas que no se cruzan a pie: lista `AVENIDAS_ANCHAS` del script + las de la sección "Avenidas que no se cruzan a pie" de la memoria, que pasas siempre con `--ancha "A,B"`. Si el usuario nombra otra, guárdala ahí.
- **Rápido:** junta en un mensaje las llamadas que no dependen entre sí; no copies pacientes ni tiempos a mano más que lo indicado; no narres los pasos.

## Scripts
Este archivo y los scripts vienen del repositorio público `crp9001/PADOMI`, carpeta `Ruta/`, que el skill instalado clona sin pedir acceso (`<repo>` = la carpeta donde quedó, por ejemplo `<carpeta de trabajo>/padomi`). `$S` = `<repo>/Ruta/scripts`; las referencias están en `<repo>/Ruta/references/`. Los archivos del día (citas, lugares, tiempos, ruta, PNG) van en la carpeta de trabajo, nunca dentro de `<repo>`. **Nada de pacientes, nombres del personal, claves ni direcciones internas va al repositorio: es público.** Corre desde la carpeta de trabajo con Python 3 + matplotlib (si falta: `pip install --break-system-packages matplotlib`). Los tiempos por calle del día quedan en `tiempos_<fec>.json`: en plena ruta solo se consultan los pacientes nuevos.

## Ruta nueva
1. **Texto a archivo:** el `RUTA PADOMI {...}` suele llegar como adjunto (Glob `*`). Si no, guárdalo tal cual con Write en `ruta_padomi.txt`. Nunca lo pases a JSON a mano.
2. **En un mensaje:** `python3 $S/ruta_padomi.py preparar <archivo>` + leer `/areas/padomi-conductor.md`.
   - `igual_a_la_anterior` y ya hay ruta: dilo en media línea y no recalcules.
   - `cambios` y `ya_hay_ruta_de_ese_dia`: ve a **En plena ruta**.
3. **En un mensaje, en paralelo:** `places_search` de todas las direcciones de `places_search` (`max_results: 1`, hasta 10 por llamada); `WebFetch` de cada `webfetch.consultas[].url` con su `prompt` tal cual; y 1 búsqueda web de obras en las avenidas de la zona (lee antes `references/obras.md`).
4. **Write**, sin pensar el orden:
   - `lugares_<fec>.json`: lista con `address`, `latitude`, `longitude`, `types` y `place_id` (solo si empieza con `ChIJ`; si no, omítelo).
   - Cada respuesta de WebFetch (solo `{"code":"Ok","durations":[...]}`) en su `guardar_en`. Si una falla, sigue: el script avisa.
5. `python3 $S/ruta_padomi.py ruta <fec> --especialista "Nombre Apellido" [--ancha "..."] [--salida HH:MM]` → resumen, **lista para el chat** y **argumentos del mapa**; guarda la ruta y el PNG. `--salida` solo si sale a otra hora que ahora (planear la víspera o ensayar).
6. **Solo si `revisar_grafico` no es `false`**, mira el PNG con Read; corrige `etiquetas_<fec>.json` (nunca `ruta_<fec>.json`) y corre `python3 $S/grafico_ruta.py ruta_<fec>.json etiquetas_<fec>.json <png>`.
7. **Entrega** (abajo).

**Tráfico (lo hace el script):** cada tramo usa el tiempo de calle sin tráfico × un factor según la hora en que se maneja (hora punta mañana y tarde más alto, mediodía y tarde medio), el día (sábado y domingo más bajo) y el sentido: de mañana, ir hacia el centro va cargado y salir del centro va a contraflujo; de tarde, al revés. La lista trae una línea 🚦 con la ida y el regreso. Los factores están en `<repo>/Ruta/data/trafico.json`: si el usuario dice que una franja o un sentido le tomó más o menos de lo estimado, ajústalos ahí (y súbelo con git).

El script cruza el pin de Geoprog con la dirección de Google (misma calle y número, a 300 m o menos; si no, deja el pin y avisa REVISAR), junta en una parada a pacientes del mismo edificio y limpia direcciones mal escritas.

## Especialista
- `tecnico_apoyo` "NN" → línea `Tec. Apoyo NN` del registro; si `prof` es un nombre, búscalo por nombre (`¥` = `Ñ`).
- Con nombre: "Hoy vas con <Nombre Apellido> (código <C. MAPA>)" y pásalo en `--especialista`.
- Sin nombre: sigue con la ruta y al final pregunta "¿Cómo se llama la persona del código <código>?" (si no sabes el código, pregunta el C. MAPA, nunca la clave). Guarda solo **nombre y 1er apellido**: reemplaza "SIN NOMBRE" o agrega `- [stated] <código> — <Nombre Apellido>` (+ ` · Tec. Apoyo NN`). Con una lista nueva del personal, misma regla; sin nombre o "LIBRE" queda "SIN NOMBRE (preguntar)".

## Entrega (lo urgente primero: el usuario sale apenas tiene el primer paciente)
Apenas termina `ruta`, en este orden y sin pasos en medio:
1. **`SendUserMessage` con el PRIMER MENSAJE** que imprimió el script, tal cual, antecedido por "Hoy vas con <Nombre> (código <C. MAPA>)." y una línea de **ida** (PADOMI → primera parada, evitando obras). Con eso ya pueden salir.
2. **`SendUserMessage` con la lista para el chat** tal cual (puedes corregir una dirección rara, sin tocar enlaces ni números). En "Tramos", la 1ª parada va sola con su 🧭 (la del primer mensaje) y el **🗺️ Tramo 1 arranca en la 2** (2 a 5; luego 6 a 10…): al terminar la 1, se abre el tramo 1 (pedido del usuario). En plena ruta igual: la siguiente parada va con su 🧭 y el tramo 1 empieza en la que sigue.
3. **Gráfico:** `SendUserFile` con el PNG (`display: render`). Nunca como artifact. Lleva de fondo, tenue, el mapa con los distritos y las vías principales (`<repo>/Ruta/data/`), con los números y colores de tramo encima.
4. **Mapa:** `places_map_display_v0` con los argumentos del script, tal cual.
5. **Respuesta final, corta:** una línea de **retorno** (última parada → Av. Arenales → cdra 13), obras en el recorrido con su fuente si las hay, y el **cierre:** "🗺️ = tramo de hasta 5 paradas; 🧭 = un solo paciente. Si Google Maps se cierra a mitad de tramo, usa el 🧭 del siguiente; si el 🗺️ abre en el navegador, usa los 🧭. Avísame en el penúltimo (<apellido>) por el combustible. Si agregan pacientes, pégame la lista nueva y dime en qué número vas."

## En plena ruta
1. Si hay `cambios` y ruta del día, pregunta **"¿En qué número de paciente vas?"** (de la última lista), salvo que ya lo haya dicho.
2. **En un mensaje:** `python3 $S/ruta_padomi.py plan <fec> --voy N` + `places_search` de las direcciones nuevas (si hay).
   - Si `plan` dice que no hay consultas, no hagas WebFetch. Si trae URLs (solo de los nuevos), WebFetch de cada una y Write en su `guardar_en`.
3. Agrega los lugares nuevos a `lugares_<fec>.json` sin borrar los anteriores y corre `python3 $S/ruta_padomi.py ruta <fec> --voy N --especialista "..."`. Da por atendidas 1 a N, sigue desde N+1, marca 🆕 y avisa los que ya no figuran.
4. **Entrega corta, en el mismo orden de Entrega:** primero el PRIMER MENSAJE (la siguiente parada) con "Quedan X pacientes (Y nuevos)" y una línea con los atendidos tachados (`~~1 Apellido~~ · ~~2 Apellido~~`); luego la lista, el gráfico (atendidos en gris y tachados) y el mapa (el script ya arma el día 1 con los atendidos tachados y el día 2 con lo que falta). El combustible pasa a la nueva penúltima. Si ya no se puede evitar volver a una zona, dilo y explica qué grupo debió ir junto.
5. **Solo reordenar** (mismo N, sin nuevos, por ejemplo con otra `--ancha`): corre solo `ruta <fec> --voy N`.
6. **Sin `ruta_<fec>.json`** (otra conversación): pide su ubicación (herramienta del dispositivo) y a quiénes ya atendió; `preparar` con la lista, luego `plan` y `ruta` con `--gps=LAT,LNG --quitar "Apellido1,Apellido2"` (con `=` porque la latitud es negativa).

## Combustible (penúltimo paciente)
Pregunta "¿Vas a recargar combustible antes de regresar a PADOMI?". **Sí:** si la memoria no tiene su combustible y grifo preferido, pregúntalo una vez y guárdalo; busca 2 o 3 grifos de ese tipo sobre el camino de regreso, abiertos a esa hora, y da el 🧭 del que no obligue a desviarse (`https://www.google.com/maps/dir/?api=1&travelmode=driving&dir_action=navigate&destination=<lat>,<lng>&destination_place_id=<place_id>`) y el de regreso. **No:** recuérdale el 🧭 del último paciente y el de regreso.

## Ubicación
No hay GPS en segundo plano. Si pregunta "¿cómo voy?", pide su ubicación con la herramienta del dispositivo y dile la siguiente parada, la distancia y si hay que llamar antes. Recuérdale escribir solo detenido.

## Favorito y computadora
Para reinstalar el favorito `rutapadomi`, el error "DOCTYPE … is not valid JSON" o sacar la ruta desde la computadora: está en la sección "Favorito" del skill instalado en la cuenta (el cargador), no en este repositorio.

## Actualizar este skill
Cuando el usuario pida una mejora: edita los archivos en `<repo>/Ruta/`, pruébala con una copia de los datos del día en una carpeta aparte (nunca sobre la ruta que el usuario está usando), revisa que no lleve datos de pacientes ni del personal, y súbela: `mcp__claude-code-remote__add_repo` (owner `crp9001`, repo `PADOMI`, access `push`) y luego `git -C <repo> fetch origin main`, `git -C <repo> add Ruta && git -C <repo> commit -m "<qué cambió>" && git -C <repo> push origin main`. La próxima conversación ya la usa. No hace falta zip ni botón "Actualizar"; eso solo si cambia el cargador (el SKILL.md instalado en la cuenta).
