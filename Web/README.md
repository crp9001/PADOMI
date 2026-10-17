# Ruta PADOMI · página web (piloto)

Página para que los conductores del piloto armen su ruta sin Claude: `https://jyc.pe/ruta/`.

- `ruta/index.html`: la página. Lee la lista de Geoprog (favorito `rutapadomi`) **en el celular**; nombres, direcciones y teléfonos no salen del teléfono.
- `ruta/api.php`: ingreso por usuario, límite diario por conductor, registro de llegadas y panel del administrador. Al servidor solo llegan coordenadas y minutos de atención.
- `optimizar.php` (consulta a Google Route Optimization) **no está aquí**: lleva la clave y vive solo en el hosting.
- Fuera de la web (`~/padomi_privado/`): llave de Google, usuarios (contraseñas cifradas), sesiones, uso y llegadas. Nada de eso va al repositorio.
