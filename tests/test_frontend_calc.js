/**
 * Verifica que el calculo del navegador coincida con el del backend.
 *
 * El navegador y el servidor redondean distinto si uno no tiene cuidado:
 *   (10.555).toFixed(2)  -> "10.55"   porque el double vale 10.55499...
 *   apu_round(10.555, 2) -> 10.56     (medio-arriba sobre el decimal)
 *
 * Un centavo de diferencia aparece recien al guardar, y en un presupuesto
 * eso hace desconfiar de todo el numero. Estos casos estan calculados con
 * el backend (app/services/apu_engine.py::apu_round) y fijan la equivalencia.
 */
const fs = require('fs');

const src = fs.readFileSync('frontend/public/assets/app.js', 'utf8');
const apuRoundSrc = src.match(/function apuRound\(value, decimals = 2\)[\s\S]*?\n}/);
const subtotalSrc = src.match(/function apuLineSubtotal\(quantity, priceUnit\)[\s\S]*?\n}/);

if (!apuRoundSrc || !subtotalSrc) {
    console.error('FALLA: no se encontraron apuRound/apuLineSubtotal en app.js');
    process.exit(1);
}
eval(apuRoundSrc[0] + '\n' + subtotalSrc[0]);

let pass = 0, fail = 0;
function check(nombre, real, esperado) {
    const ok = Math.abs(real - esperado) < 1e-9;
    if (ok) { pass++; console.log('  OK    ' + nombre); }
    else { fail++; console.log(`  FALLA ${nombre}: dio ${real}, se esperaba ${esperado}`); }
}

console.log('=== redondeo medio-arriba, igual que el backend ===');
// Casos donde toFixed() del navegador da DISTINTO que el backend.
check('10.555 -> 10.56 (toFixed daria 10.55)', apuRound(10.555, 2), 10.56);
check('24.345 -> 24.35 (toFixed daria 24.34)', apuRound(24.345, 2), 24.35);
check('2.675  -> 2.68  (toFixed daria 2.67)',  apuRound(2.675, 2), 2.68);

console.log('=== casos donde ambos coinciden ===');
check('7.2 se mantiene', apuRound(7.2, 2), 7.2);
check('7.034999... -> 7.03', apuRound(7.034999999999999, 2), 7.03);
check('0.0625 -> 0.06', apuRound(0.0625, 2), 0.06);

console.log('=== medio hacia arriba, alejandose del cero ===');
check('2.5 -> 3', apuRound(2.5, 0), 3);
check('3.5 -> 4', apuRound(3.5, 0), 4);
check('-2.5 -> -3', apuRound(-2.5, 0), -3);

console.log('=== rendimientos con 3 decimales ===');
check('0.125 -> 0.125', apuRound(0.125, 3), 0.125);
check('1.0005 -> 1.001', apuRound(1.0005, 3), 1.001);

console.log('=== valores raros no deben romper ===');
check('null -> 0', apuRound(null, 2), 0);
check('undefined -> 0', apuRound(undefined, 2), 0);
check('texto -> 0', apuRound('no es numero', 2), 0);
check('Infinity -> 0', apuRound(Infinity, 2), 0);
check('cero -> 0', apuRound(0, 2), 0);

console.log('=== subtotal de linea: rendimiento x precio ===');
// 0.125 bolsas de cemento por m2 a 57.60 Bs
check('0.125 x 57.60 = 7.20', apuLineSubtotal(0.125, 57.60), 7.20);
check('2 x 18.75 = 37.50', apuLineSubtotal(2, 18.75), 37.50);
check('1 x 10.555 = 10.56', apuLineSubtotal(1, 10.555), 10.56);
check('3 x 8.115 = 24.35', apuLineSubtotal(3, 8.115), 24.35);
check('sin datos = 0', apuLineSubtotal(null, null), 0);

console.log('=== una suma de muchas lineas no debe derivar ===');
// 4000 lineas redondeando en cada paso, como hace el motor
let acumulado = 0;
for (let i = 0; i < 2000; i++) acumulado = apuRound(acumulado + apuLineSubtotal(0.125, 57.60), 2);
for (let i = 0; i < 2000; i++) acumulado = apuRound(acumulado + apuLineSubtotal(1, 18.75), 2);
check('2000x7.20 + 2000x18.75 = 51900', acumulado, 51900);

console.log(`\n${pass} pasaron, ${fail} fallaron`);
process.exit(fail ? 1 : 0);
