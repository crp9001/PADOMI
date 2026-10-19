# Ruta PADOMI · página web (piloto)

Página para que los conductores del piloto armen su ruta sin Claude: `https://jyc.pe/ruta/`.

- `ruta/index.html`: la página. Trae la lista de Geoprog de dos maneras: **selector de enfermero** (el servidor entra solo, ver `geoprog.php`) o, de respaldo, el favorito `rutapadomi` **en el celular**. Los nombres y códigos de los enfermeros no viajan dentro de la página.
- `ruta/api.php`: ingreso por usuario, límite diario por conductor, registro de llegadas y panel del administrador. Al servidor solo llegan coordenadas y minutos de atención.
- `ruta/geoprog.php`: agente que entra a Geoprog con el código del enfermero (en Geoprog usuario = clave = código), lee las citas del día y devuelve solo los campos que la ruta usa. Lo invoca `api.php` con la sesión ya validada; nunca se llama directo.
- `optimizar.php` (consulta a Google Route Optimization) **no está aquí**: lleva la clave y vive solo en el hosting.
- Fuera de la web (`~/padomi_privado/`): llave de Google, usuarios (contraseñas cifradas), sesiones, uso, llegadas y `enfermeros.json` (código → nombre de cada enfermero de Geoprog). Nada de eso va al repositorio.
