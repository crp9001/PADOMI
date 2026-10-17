<?php
/**
 * Ruta PADOMI · API de la página jyc.pe/ruta (piloto con conductores)
 *
 * Privacidad: la lista de Geoprog se lee en el celular del conductor. Aquí solo llegan coordenadas,
 * minutos de atención y números de parada; nunca nombres, direcciones ni teléfonos.
 *
 * POST JSON con la cabecera "X-Ruta: 1" (bloquea pedidos desde otras páginas). Acciones:
 *   login {usuario, clave} · salir · yo · clave {actual, nueva}
 *   optimizar {inicio, fin, salida, llegada, paradas}   → Google Route Optimization (optimizar.php)
 *   llegada {...estimado y hora real}                    → registro del piloto, sin datos de pacientes
 *   panel                                                → solo administrador
 */
declare(strict_types=1);
ini_set('display_errors', '0');

const DIAS_SESION  = 30;
const MAX_INTENTOS = 6;            // intentos fallidos por IP en 15 minutos
const MAX_PARADAS_PEDIDO = 40;

$priv = dirname(__DIR__, 2) . '/padomi_privado';
$fUsuarios = $priv . '/usuarios.json';
$fTokens   = $priv . '/sesiones.json';
$fIntentos = $priv . '/intentos_login.json';
$fUso      = $priv . '/uso_usuarios.json';
$fPiloto   = $priv . '/piloto.jsonl';
$fGoogle   = $priv . '/uso_google.json';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Robots-Tag: noindex, nofollow');
header('X-Content-Type-Options: nosniff');

function r_salir(int $code, array $d): never
{
    http_response_code($code);
    echo json_encode($d, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function r_leer(string $f, array $def = []): array
{
    if (!is_file($f)) {
        return $def;
    }
    $d = json_decode((string)file_get_contents($f), true);
    return is_array($d) ? $d : $def;
}

/** Lee, modifica y guarda un JSON con bloqueo (dos conductores a la vez no se pisan). */
function r_actualizar(string $f, callable $fn)
{
    $h = fopen($f, 'c+');
    if (!$h) {
        r_salir(500, ['ok' => false, 'error' => 'No se pudo abrir el registro']);
    }
    flock($h, LOCK_EX);
    $txt = stream_get_contents($h);
    $d = json_decode((string)$txt, true);
    if (!is_array($d)) {
        $d = [];
    }
    $res = $fn($d);
    ftruncate($h, 0);
    rewind($h);
    fwrite($h, (string)json_encode($d, JSON_UNESCAPED_UNICODE));
    fflush($h);
    flock($h, LOCK_UN);
    fclose($h);
    @chmod($f, 0600);
    return $res;
}

function r_ip(): string
{
    return substr((string)($_SERVER['REMOTE_ADDR'] ?? '?'), 0, 64);
}

function r_cookie(string $valor, int $expira): void
{
    setcookie('rp_t', $valor, [
        'expires'  => $expira,
        'path'     => '/ruta/',
        'secure'   => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
        'httponly' => true,
        'samesite' => 'Strict',
    ]);
}

function r_hhmm($v): ?string
{
    $v = (string)$v;
    return preg_match('/^([01]\d|2[0-3]):[0-5]\d$/', $v) ? $v : null;
}

/** Usuario de la sesión o null. */
function r_usuario(string $fTokens, array $usuarios): ?array
{
    $t = (string)($_COOKIE['rp_t'] ?? '');
    if (strlen($t) !== 64 || !ctype_xdigit($t)) {
        return null;
    }
    $s = r_leer($fTokens)[hash('sha256', $t)] ?? null;
    if (!$s || ($s['exp'] ?? 0) < time() || empty($usuarios[$s['u']])) {
        return null;
    }
    return ['usuario' => $s['u']] + $usuarios[$s['u']];
}

function r_uso(array $d, string $u, DateTime $hoy): array
{
    $dia = $hoy->format('Y-m-d');
    $mes = $hoy->format('Y-m');
    $x = $d[$u] ?? [];
    return [
        'hoy' => ($x['dia'] ?? '') === $dia ? (int)($x['dia_n'] ?? 0) : 0,
        'mes' => ($x['mes'] ?? '') === $mes ? (int)($x['mes_n'] ?? 0) : 0,
    ];
}

function r_publico(array $yo, array $uso): array
{
    return [
        'ok'         => true,
        'usuario'    => $yo['usuario'],
        'nombre'     => $yo['nombre'] ?? $yo['usuario'],
        'admin'      => !empty($yo['admin']),
        'limite_dia' => (int)($yo['limite_dia'] ?? 80),
        'uso'        => $uso,
    ];
}

// ---------------------------------------------------------------------------

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST' || ($_SERVER['HTTP_X_RUTA'] ?? '') !== '1') {
    r_salir(404, ['ok' => false, 'error' => 'No encontrado']);
}
$in = json_decode((string)file_get_contents('php://input'), true);
if (!is_array($in)) {
    r_salir(400, ['ok' => false, 'error' => 'Pedido inválido']);
}
$accion   = (string)($in['accion'] ?? '');
$usuarios = r_leer($fUsuarios);
$lima     = new DateTimeZone('America/Lima');
$hoy      = new DateTime('now', $lima);

// ---- ingresar
if ($accion === 'login') {
    $ip = r_ip();
    $recientes = r_actualizar($fIntentos, function (array &$d) use ($ip) {
        $lim = time() - 900;
        foreach ($d as $k => $lista) {
            $d[$k] = array_values(array_filter((array)$lista, fn($t) => $t > $lim));
            if (!$d[$k]) {
                unset($d[$k]);
            }
        }
        return count($d[$ip] ?? []);
    });
    if ($recientes >= MAX_INTENTOS) {
        r_salir(429, ['ok' => false, 'error' => 'Demasiados intentos. Espera 15 minutos.']);
    }
    $u   = strtolower(trim((string)($in['usuario'] ?? '')));
    $cl  = (string)($in['clave'] ?? '');
    $reg = $usuarios[$u] ?? null;
    if (!$reg || empty($reg['activo']) && isset($reg['activo']) || !password_verify($cl, (string)($reg['hash'] ?? ''))) {
        r_actualizar($fIntentos, function (array &$d) use ($ip) {
            $d[$ip][] = time();
        });
        usleep(400000);
        r_salir(401, ['ok' => false, 'error' => 'Usuario o contraseña incorrectos']);
    }
    $token  = bin2hex(random_bytes(32));
    $expira = time() + DIAS_SESION * 86400;
    r_actualizar($fTokens, function (array &$d) use ($token, $u, $expira) {
        foreach ($d as $k => $s) {
            if (($s['exp'] ?? 0) < time()) {
                unset($d[$k]);
            }
        }
        $d[hash('sha256', $token)] = ['u' => $u, 'exp' => $expira];
    });
    r_cookie($token, $expira);
    $yo = ['usuario' => $u] + $reg;
    r_salir(200, r_publico($yo, r_uso(r_leer($fUso), $u, $hoy)));
}

$yo = r_usuario($fTokens, $usuarios);
if (!$yo) {
    r_salir(401, ['ok' => false, 'error' => 'Ingresa con tu usuario', 'sin_sesion' => true]);
}

// ---- salir
if ($accion === 'salir') {
    $t = (string)($_COOKIE['rp_t'] ?? '');
    r_actualizar($fTokens, function (array &$d) use ($t) {
        unset($d[hash('sha256', $t)]);
    });
    r_cookie('', time() - 3600);
    r_salir(200, ['ok' => true]);
}

// ---- quién soy
if ($accion === 'yo') {
    r_salir(200, r_publico($yo, r_uso(r_leer($fUso), $yo['usuario'], $hoy)));
}

// ---- cambiar contraseña
if ($accion === 'clave') {
    $nueva = (string)($in['nueva'] ?? '');
    if (!password_verify((string)($in['actual'] ?? ''), (string)$yo['hash'])) {
        r_salir(400, ['ok' => false, 'error' => 'La contraseña actual no coincide']);
    }
    if (mb_strlen($nueva) < 8) {
        r_salir(400, ['ok' => false, 'error' => 'La nueva debe tener al menos 8 caracteres']);
    }
    r_actualizar($fUsuarios, function (array &$d) use ($yo, $nueva) {
        $d[$yo['usuario']]['hash'] = password_hash($nueva, PASSWORD_DEFAULT);
    });
    r_salir(200, ['ok' => true]);
}

// ---- ordenar con Google
if ($accion === 'optimizar') {
    $n = is_array($in['paradas'] ?? null) ? count($in['paradas']) : 0;
    if ($n < 1 || $n > MAX_PARADAS_PEDIDO) {
        r_salir(400, ['ok' => false, 'error' => 'La lista debe tener entre 1 y ' . MAX_PARADAS_PEDIDO . ' paradas']);
    }
    // solo coordenadas y minutos: se descarta cualquier otro dato que viniera
    foreach ($in['paradas'] as $p) {
        if (!is_array($p) || count(array_diff(array_keys($p), ['id', 'lat', 'lng', 'min', 'antes'])) > 0) {
            r_salir(400, ['ok' => false, 'error' => 'Parada con datos no permitidos']);
        }
    }
    $limite = (int)($yo['limite_dia'] ?? 80);
    $u = $yo['usuario'];
    $ok = r_actualizar($fUso, function (array &$d) use ($u, $n, $limite, $hoy) {
        $dia = $hoy->format('Y-m-d');
        $mes = $hoy->format('Y-m');
        $x = $d[$u] ?? [];
        if (($x['dia'] ?? '') !== $dia) {
            $x['dia'] = $dia;
            $x['dia_n'] = 0;
        }
        if (($x['mes'] ?? '') !== $mes) {
            $x['mes'] = $mes;
            $x['mes_n'] = 0;
        }
        if ($x['dia_n'] + $n > $limite) {
            return false;
        }
        $x['dia_n'] += $n;
        $x['mes_n'] += $n;
        $x['ultimo'] = $hoy->format('Y-m-d H:i');
        $d[$u] = $x;
        return true;
    });
    if (!$ok) {
        r_salir(429, ['ok' => false, 'error' => "Llegaste a tu límite de hoy ($limite paradas). Mañana se renueva."]);
    }
    define('PADOMI_INTERNO', true);         // optimizar.php no pide su clave: la sesión ya se validó
    require __DIR__ . '/optimizar.php';     // responde y termina
    exit;
}

// ---- hora real de llegada (piloto)
if ($accion === 'llegada') {
    $real = r_hhmm($in['real_llegada'] ?? '');
    if (!$real) {
        r_salir(400, ['ok' => false, 'error' => 'Escribe la hora real de llegada (HH:MM)']);
    }
    $fila = [
        'registrado'   => $hoy->format('Y-m-d H:i'),
        'fecha'        => preg_match('/^\d{8}$/', (string)($in['fecha'] ?? '')) ? (string)$in['fecha'] : $hoy->format('Ymd'),
        'usuario'      => $yo['usuario'],
        'paradas'      => max(0, min(60, (int)($in['paradas'] ?? 0))),
        'pacientes'    => max(0, min(80, (int)($in['pacientes'] ?? 0))),
        'salida'       => r_hhmm($in['salida'] ?? ''),
        'est_llegada'  => r_hhmm($in['est_llegada'] ?? ''),
        'est_km'       => round(max(0, min(300, (float)($in['est_km'] ?? 0))), 1),
        'est_manejo'   => max(0, min(600, (int)($in['est_manejo'] ?? 0))),
        'real_salida'  => r_hhmm($in['real_salida'] ?? ''),
        'real_llegada' => $real,
        'real_km'      => isset($in['real_km']) && $in['real_km'] !== '' ? round(max(0, min(300, (float)$in['real_km'])), 1) : null,
        'nota'         => mb_substr(trim(strip_tags((string)($in['nota'] ?? ''))), 0, 200),
    ];
    file_put_contents($fPiloto, json_encode($fila, JSON_UNESCAPED_UNICODE) . "\n", FILE_APPEND | LOCK_EX);
    @chmod($fPiloto, 0600);
    r_salir(200, ['ok' => true]);
}

// ---- panel del administrador
if ($accion === 'panel') {
    if (empty($yo['admin'])) {
        r_salir(403, ['ok' => false, 'error' => 'Solo el administrador']);
    }
    $uso = r_leer($fUso);
    $lista = [];
    foreach ($usuarios as $u => $reg) {
        $lista[] = ['usuario' => $u, 'nombre' => $reg['nombre'] ?? $u, 'admin' => !empty($reg['admin']),
                    'limite_dia' => (int)($reg['limite_dia'] ?? 80), 'ultimo' => $uso[$u]['ultimo'] ?? null]
                   + r_uso($uso, $u, $hoy);
    }
    $filas = [];
    if (is_file($fPiloto)) {
        foreach (array_slice(file($fPiloto, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) ?: [], -100) as $l) {
            $x = json_decode($l, true);
            if (is_array($x)) {
                $filas[] = $x;
            }
        }
    }
    $g = r_leer($fGoogle);
    r_salir(200, ['ok' => true, 'usuarios' => $lista, 'llegadas' => array_reverse($filas),
                  'google' => ['hoy' => (int)($g['dia_n'] ?? 0), 'dia' => $g['dia'] ?? null,
                               'mes' => (int)($g['mes_n'] ?? 0), 'mes_id' => $g['mes'] ?? null,
                               'tope_mes' => 4800, 'gratis_mes' => 5000]]);
}

r_salir(400, ['ok' => false, 'error' => 'Acción desconocida']);
