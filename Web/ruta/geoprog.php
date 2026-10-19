<?php
/**
 * Ruta PADOMI · módulo Geoprog (agente de ingreso a EsSalud)
 *
 * Lo invoca api.php con la acción "geoprog", DESPUÉS de validar la sesión del
 * conductor del piloto. Nunca se llama directo: exige la constante PADOMI_INTERNO,
 * que solo define api.php una vez comprobada la sesión (igual que optimizar.php).
 *
 * Entra a Geoprog con el código del enfermero (en Geoprog usuario = clave = código),
 * lee las citas del día de ese profesional y las devuelve a la página con la MISMA
 * forma que producía el favorito del celular: {fec, prof, rows:[{cod_pac,...}]}.
 *
 * Privacidad y seguridad:
 *   - Los códigos de los enfermeros viven solo aquí, en padomi_privado/enfermeros.json.
 *     A la página se le mandan nombres y un id derivado (sha1), nunca el código.
 *   - Solo se guardan de los pacientes los campos que la ruta necesita.
 *   - Solo entra para conductores con sesión válida del piloto.
 *
 * Variables y funciones que hereda de api.php: $in, $yo, $priv, $hoy,
 *   r_leer(), r_actualizar(), r_salir().
 */
declare(strict_types=1);

if (!defined('PADOMI_INTERNO')) {
    r_salir(403, ['ok' => false, 'error' => 'Acceso no permitido']);
}

const GEO_BASE   = 'http://padomimbk.essalud.gob.pe/geoprog/';
const GEO_MAX    = 60;   // tope de pacientes que aceptamos de una lista
const GEO_CAMPOS = ['cod_pac', 'paciente', 'nom_via', 'ref_dom', 'nom_dst', 'telfs', 'edad', 'coordy', 'coordx'];

$fEnf = $priv . '/enfermeros.json';          // { "<codigo>": "<Nombre Apellido>" }
$geo  = (string)($in['geo'] ?? '');

/** Normaliza un código de Geoprog: solo dígitos, 3 a 6. */
function geo_cod($v): ?string
{
    $v = preg_replace('/\D+/', '', (string)$v);
    return ($v !== '' && strlen($v) >= 3 && strlen($v) <= 6) ? $v : null;
}

/** id público y estable de un código, para no mandar el código al navegador. */
function geo_id(string $cod): string
{
    return substr(hash('sha256', 'padomi|' . $cod), 0, 10);
}

/** Petición a Geoprog reutilizando una misma "cookie jar" (la sesión PHPSESSID). */
function geo_pide(string $url, array $post, string $jar, int $t = 20): array
{
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => http_build_query($post),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_COOKIEJAR      => $jar,
        CURLOPT_COOKIEFILE     => $jar,
        CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_TIMEOUT        => $t,
        CURLOPT_USERAGENT      => 'RutaPADOMI/1.0',
    ]);
    $cuerpo = curl_exec($ch);
    $http   = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err    = curl_error($ch);
    curl_close($ch);
    return ['cuerpo' => (string)$cuerpo, 'http' => $http, 'err' => $err];
}

// ---------------------------------------------------------------- diag: ¿el servidor alcanza Geoprog?
if ($geo === 'diag') {
    $ch = curl_init(GEO_BASE);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_TIMEOUT        => 20,
        CURLOPT_USERAGENT      => 'RutaPADOMI/1.0',
    ]);
    $cuerpo = (string)curl_exec($ch);
    $http   = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err    = curl_error($ch);
    curl_close($ch);
    r_salir(200, [
        'ok'        => $http === 200,
        'alcanza'   => $http === 200,
        'http'      => $http,
        'error'     => $err ?: null,
        'es_login'  => stripos($cuerpo, 'funclogin.js') !== false,
    ]);
}

// ---------------------------------------------------------------- lista de enfermeros para el selector
if ($geo === 'lista') {
    $enf = r_leer($fEnf);
    $out = [];
    foreach ($enf as $cod => $nombre) {
        $cod = (string)$cod;
        $out[] = ['id' => geo_id($cod), 'nombre' => (string)$nombre];
    }
    usort($out, fn($a, $b) => strcoll($a['nombre'], $b['nombre']));
    r_salir(200, ['ok' => true, 'enfermeros' => $out]);
}

// ---------------------------------------------------------------- agregar un enfermero (código + nombre)
if ($geo === 'agregar') {
    $cod = geo_cod($in['codigo'] ?? '');
    $nom = trim((string)($in['nombre'] ?? ''));
    $nom = preg_replace('/\s+/', ' ', strip_tags($nom));
    if (!$cod) {
        r_salir(400, ['ok' => false, 'error' => 'El código debe tener de 3 a 6 dígitos']);
    }
    if (mb_strlen($nom) < 3 || mb_strlen($nom) > 60) {
        r_salir(400, ['ok' => false, 'error' => 'Escribe el nombre y apellido del enfermero']);
    }
    r_actualizar($fEnf, function (array &$d) use ($cod, $nom) {
        $d[$cod] = $nom;
    });
    r_salir(200, ['ok' => true, 'id' => geo_id($cod), 'nombre' => $nom]);
}

// ---------------------------------------------------------------- traer las citas del día
if ($geo === 'traer') {
    $fec = (string)($in['fec'] ?? '');
    if (!preg_match('/^\d{8}$/', $fec)) {
        r_salir(400, ['ok' => false, 'error' => 'Elige la fecha de la ruta']);
    }

    // el código sale de un enfermero guardado (por id) o de uno escrito a mano
    $enf = r_leer($fEnf);
    $cod = null;
    $nombreGuardado = '';
    if (!empty($in['id'])) {
        $buscado = (string)$in['id'];
        foreach ($enf as $c => $nombre) {
            if (geo_id((string)$c) === $buscado) {
                $cod = (string)$c;
                $nombreGuardado = (string)$nombre;
                break;
            }
        }
        if ($cod === null) {
            r_salir(400, ['ok' => false, 'error' => 'Ese enfermero ya no está en la lista']);
        }
    } else {
        $cod = geo_cod($in['codigo'] ?? '');
        if (!$cod) {
            r_salir(400, ['ok' => false, 'error' => 'Elige un enfermero o escribe su código']);
        }
        $nombreGuardado = (string)($enf[$cod] ?? '');
    }

    $jar = tempnam(sys_get_temp_dir(), 'geo');
    if ($jar === false) {
        r_salir(500, ['ok' => false, 'error' => 'No se pudo preparar la conexión']);
    }

    try {
        // 1) ingresar: usuario = clave = código
        $login = geo_pide(GEO_BASE . 'login.php', ['usuario' => $cod, 'pass' => $cod], $jar);
        if ($login['http'] === 0) {
            r_salir(502, ['ok' => false, 'error' => 'El servidor no pudo conectarse a Geoprog. ' . ($login['err'] ?: ''), 'sin_alcance' => true]);
        }
        $jl = json_decode($login['cuerpo'], true);
        $resp = is_array($jl) ? (string)($jl['resp'] ?? '') : '';
        if ($resp !== '1') {
            $msg = [
                '0'  => 'El código no entró a Geoprog (usuario o clave incorrectos).',
                '-2' => 'Ese código no tiene acceso autorizado en Geoprog.',
                '-1' => 'Geoprog reportó un error de conexión de datos.',
            ][$resp] ?? 'No se pudo ingresar a Geoprog con ese código.';
            r_salir(502, ['ok' => false, 'error' => $msg]);
        }

        // 2) nombre del profesional (lo que Geoprog muestra como cuenta)
        $prof = $nombreGuardado;
        $ini = geo_pide(GEO_BASE . 'inicio.php', [], $jar);
        if ($ini['http'] === 200 && preg_match('/id=["\']prof["\'][^>]*value=["\']([^"\']*)["\']/i', $ini['cuerpo'], $m)) {
            $prof = trim(html_entity_decode($m[1], ENT_QUOTES, 'UTF-8'));
        } elseif ($ini['http'] === 200 && preg_match('/value=["\']([^"\']*)["\'][^>]*id=["\']prof["\']/i', $ini['cuerpo'], $m)) {
            $prof = trim(html_entity_decode($m[1], ENT_QUOTES, 'UTF-8'));
        }

        // 3) citas del día
        $cit = geo_pide(GEO_BASE . 'getcitasprof.php', ['fec' => $fec], $jar);
        if ($cit['http'] !== 200) {
            r_salir(502, ['ok' => false, 'error' => 'Geoprog no devolvió las citas (código ' . $cit['http'] . ').']);
        }
        $jc = json_decode($cit['cuerpo'], true);
        if (!is_array($jc)) {
            r_salir(502, ['ok' => false, 'error' => 'La respuesta de Geoprog no se entendió. Vuelve a intentar.']);
        }
        $filas = isset($jc['rows']) && is_array($jc['rows']) ? $jc['rows'] : $jc;

        // solo los campos que la ruta necesita; nada más sale de aquí
        $rows = [];
        foreach ($filas as $f) {
            if (!is_array($f)) {
                continue;
            }
            $r = [];
            foreach (GEO_CAMPOS as $k) {
                $r[$k] = isset($f[$k]) ? $f[$k] : '';
            }
            $rows[] = $r;
            if (count($rows) >= GEO_MAX) {
                break;
            }
        }

        r_salir(200, ['ok' => true, 'fec' => $fec, 'prof' => $prof, 'rows' => $rows]);
    } finally {
        @unlink($jar);
    }
}

r_salir(400, ['ok' => false, 'error' => 'Acción de Geoprog desconocida']);
