# Mapa base del gráfico

- `vias_lima.json`: vías principales de Lima y Callao (expresas y arteriales), simplificadas.
  Datos © colaboradores de OpenStreetMap, licencia ODbL (https://www.openstreetmap.org/copyright),
  tomados de github.com/unimauro/lima-en-movimiento (`data/arteries.geojson`).
- `distritos_lima.json`: límites distritales de Lima y Callao (IGN), simplificados,
  tomados de github.com/joseluisq/peru-geojson-datasets.

`grafico_ruta.py` los dibuja tenues debajo de la ruta. Si faltan, el gráfico sale sin fondo.

# Tráfico

- `trafico.json`: factor por franja horaria (días de semana; sábado y domingo más bajos) y por sentido
  respecto al centro de Lima (de mañana hacia el centro va cargado; de tarde, saliendo). Son estimados:
  se ajustan con lo que el conductor reporte.

# Accesos de EsSalud

- `accesos.json`: los 3 accesos para el regreso y una tabla de 24 puntos alrededor de EsSalud (0.8, 2.5 y
  6 km, en 8 direcciones) con los segundos por calle hasta cada acceso (OSRM, respeta el sentido de las
  calles). El script elige el acceso desde el punto de la tabla más cercano a la última parada, sin
  consultas extra. Si cambian los accesos, hay que volver a medir la tabla.
