"""Actualiza rubros y descripciones de proveedores para mejorar busqueda.

Patron: upsert — crea rubro si no existe, no duplica.
Objetivo: que si un usuario busca un producto especifico y no esta en catalogo,
encuentre al proveedor que lo ofrece y pueda contactarlo directamente.

Ejecutar: python scripts/update_rubros_descriptions.py
"""

import httpx
import os

APP_URL = os.getenv("APP_URL", "https://apu-marketplace-app.q8waob.easypanel.host")
API_KEY = os.getenv("API_KEY", "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Mapping: ID Proveedor (dataset) → DB ID
PROV_DB = {
    1: 3314, 2: 3315, 3: 3316, 4: 3317, 6: 3319,
    7: 3320, 8: 3321, 9: 3322, 10: 3323, 11: 3324,
    12: 3325, 13: 3326, 14: 3327, 15: 3328, 16: 3329,
    17: 3330, 18: 3331, 19: 3332, 20: 3333, 21: 3334,
    22: 3335, 23: 3336, 24: 3337, 25: 3338, 26: 3339,
    27: 3340, 29: 3342, 30: 3343, 31: 3344, 32: 3345,
    33: 3346, 34: 3347, 35: 3348, 36: 3349, 37: 3350,
    38: 3351, 39: 3352, 40: 3353, 41: 3354, 42: 3355,
    43: 3356, 44: 3357, 45: 3358, 46: 3359, 48: 3361,
    49: 3362, 50: 3363, 51: 3364, 52: 3365, 54: 3367,
    55: 3368, 56: 3369, 57: 3370, 58: 3371, 59: 3372,
    60: 3373, 61: 3374, 62: 3375, 63: 3376, 64: 3377,
    65: 3378, 66: 3379, 67: 3380, 68: 3381, 69: 3382,
    70: 3383, 71: 3384, 72: 3385, 73: 3386, 74: 3387,
    75: 3388, 76: 3389, 77: 3390, 78: 3391, 79: 3392,
    80: 3393, 82: 3395, 83: 3396, 84: 3397,
}

# ── Rubros completos con category_key ────────────────────────
RUBROS = [
    # Acermax
    (1, "Calaminas", "techos", "Calamina plana, ondulada, rectangular, trapezoidal y trapezoidal alto; teja americana, colonial y espanola; cumbreras"),
    (1, "Metalmecanica", "acero", "Corte, plegado y cilindrado de planchas de acero"),
    # Aceros Arequipa
    (2, "Acero de construccion", "acero", "Acero corrugado, estribos, clavos, alambres, conectores mecanicos"),
    (2, "Mallas / Perfiles", "acero", "Mallas electrosoldadas, perfiles de acero, planchas y tubos"),
    # Aceros Torrico
    (3, "Calaminas", "techos", "Calaminas zinc-alum, pre-pintadas, corrugadas; teja americana/colonial"),
    (3, "Perfiles metalicos", "acero", "Perfiles en C y U, pernos auto-perforantes, clavos galvanizados"),
    # Acustica.bo
    (4, "Acustica", "aislantes", "Soluciones acusticas para viviendas, oficinas, industrias"),
    # Bacheo.com.bo
    (6, "Asfalto", "agregados", "Asfalto frio EZ Street para mantenimiento vial y obras"),
    # Lab. Batercon
    (7, "Laboratorio", "maquinaria", "Pruebas integridad pilotes, rotura probetas, analisis granulometrico, esclerometria"),
    # Barrientos Teran Consultores
    (8, "Postensado", "prefabricados", "Anclajes Freyssinet/OVM, cordon pretensado grado 270K, vainas metalicas"),
    (8, "Consultoria estructural", "acero", "Calculo y diseno estructural, postensado de vigas para puentes y losas"),
    # Boliviaven
    (9, "Metalmecanica", "acero", "Naves industriales, estructural, hidroelectrico, HVAC, automatizacion"),
    # Cemento Camba
    (10, "Cemento", "cemento", "Cemento y materiales de construccion"),
    # Cerabol
    (11, "Porcelanato / Ceramica", "ceramica", "Ceramicas, porcelanatos, marmoles, piedras, revestimientos, semi gres"),
    # Ceramica Dorado
    (12, "Ladrillos / Bloques", "ceramica", "Ladrillos, tejas, bloques, losetas, rejillas, pisos de hormigon"),
    (12, "Calaminas galvanizadas", "techos", "Calaminas galvanizadas y de color"),
    # Ceratech
    (13, "Techos / Pisos", "techos", "Techo Shingle TAMKO, alfombras americanas, porcelanato, tableros OSB"),
    # Cimal
    (14, "Maderas / Tableros", "madera", "MDF, melaminicos, venestas, multilaminados, aglomerado"),
    (14, "Puertas", "madera", "Puertas HDF, placa, tablero, marcos"),
    # Construpanel
    (15, "Aislacion", "aislantes", "Termo Spray, muros termoacusticos, Phono Spray"),
    # Corinsa
    (16, "Gaviones", "acero", "Malla hexagonal, alambre de puas, gaviones y colchonetas"),
    # DJ Importaciones
    (17, "Pisos flotantes", "ceramica", "LAMIWOOD; cielos falsos DECORAM"),
    # Duralit
    (18, "Cubiertas fibrocemento", "techos", "Teja ondulada, espanola, Ondina, Residencial; Eterboard Drywall"),
    (18, "Tanques plasticos", "sanitario", "Tanques plasticos para agua"),
    # ECEBOL
    (19, "Cemento", "cemento", "IP-30 e IP-40, sacos 50Kg, Big Bag 1.5Tn, granel 27Tn"),
    # Electrored
    (20, "Materiales electricos", "electrico", "Importacion y distribucion de materiales electricos"),
    # Eurocable
    (21, "Calefaccion", "electrico", "Piso radiante electrico, calefactores para exteriores"),
    # Faboce
    (22, "Ceramica / Porcelanato", "ceramica", "Tecnogranito, porcelanato, tecnogres, gres porcelanico, lapados"),
    # Facil Cementos Adhesivos
    (23, "Adhesivos / Morteros", "cemento", "Cemento cola ceramica/porcelanato, pega ladrillo, revoque fino"),
    # Famequi
    (24, "Maquinaria construccion", "maquinaria", "Tanques hidropulmon, mezcladoras, guinches, vibradoras, elevadores"),
    # Faragauss Bolivia
    (25, "Puesta a tierra", "electrico", "Acoplamiento magneto activo, sistemas de tierra fisica, pararrayos"),
    # Ferrotodo
    (26, "Acero / Metalmecanica", "acero", "Tubos, perfiles galvanizados, alambres, mallas, discos abrasivos"),
    # Galindo Ingenieria
    (27, "Ingenieria estructural", "acero", "Diseno/calculo, sismica, patologia estructural, consultoria"),
    # Grupo R&N
    (29, "Geosinteticos", "impermeabilizantes", "Geomallas, geotextil, geomembrana, geoceldas, geodrenes"),
    (29, "Impermeabilizacion", "impermeabilizantes", "Sistemas de impermeabilizacion y drenaje vertical"),
    # Hansa
    (30, "Obras industriales", "acero", "Naves industriales, equipamientos, sistemas contraincendios"),
    # Hidronyx
    (31, "Tanques / Septicas", "sanitario", "Tanques bicapa/tricapa 300-10000L, camaras septicas, bebederos"),
    # ICI Ltda.
    (32, "Gas natural", "sanitario", "Medidores domesticos/comerciales/industriales, reguladores, valvulas"),
    # IMCAR (Dist. Sika)
    (33, "Obra fina / SIKA", "impermeabilizantes", "Lavamanos, inodoros, griferia, porcelanatos, impermeabilizantes SIKA"),
    # Importadora Alarcon
    (34, "Tuberias PVC", "plomeria", "Canerias agua fria/caliente, desague, polipropileno, gas domiciliario"),
    # Importadora Duran
    (35, "Acabados / Pisos", "ceramica", "Policarbonato, pisos flotantes SPC/HDF, cielos falsos PVC, LED"),
    # Importadora Z. Santos
    (36, "Postensado / Puentes", "prefabricados", "Vainas corrugadas, cordon 270K, anclajes Freyssinet/OVM"),
    # INGCO Bolivia
    (37, "Herramientas", "herramientas", "Electricas, manuales, neumaticas, de banco, generadores, bombas"),
    # Inno Domotics
    (38, "Domotica", "electrico", "Automatizacion, home theater, asesoramiento tecnico"),
    # Innoplack
    (39, "Drywall / Perfiles", "acero", "Perfiles acero galvanizado, placas yeso estandar/humedad/fuego"),
    (39, "Cubiertas", "techos", "Teja flexiteja y espanola de fibrocemento"),
    # Inkaforte (Brizio)
    (40, "Cemento cola", "cemento", "Inkaforte ceramica y porcelanato, alta adherencia"),
    # Intermec S.R.L.
    (41, "Estructuras metalicas", "acero", "Tinglados, coliseos, galpones, cubiertas policarbonato"),
    (41, "Cielos falsos", "techos", "GALVATEX, YESOTEX, PVC, Drywall"),
    (41, "Vidrio templado", "vidrios", "Fachadas vidrio templado/reflectivo, aluminio compuesto"),
    # Isocret
    (42, "Viguetas pretensadas", "prefabricados", "Styropor expandido, hormigon industrial, postes curvos"),
    # Isolcruz
    (43, "Aislacion isotermica", "aislantes", "EPS, poliuretano, poliisocianurato, muros termoacusticos"),
    # Las Lomas
    (44, "Acero de construccion", "acero", "Fierro DEDINI corrugado y liso, planchas, angulares, pletinas"),
    # Mamut
    (45, "Pisos sostenibles", "ceramica", "Baldosa EPDM, pavimento continuo, piso podotactil, poliuretano"),
    # Maqualq S.R.L.
    (46, "Alquiler equipos", "maquinaria", "Andamios, puntales, compactadora, mezcladora, vibradora"),
    # Marcav
    (48, "Geomembrana", "impermeabilizantes", "Geomembrana y geotextil; termofusion tuberias HDPE"),
    # Monopol
    (49, "Pinturas", "pintura", "Latex arquitectonico, anticorrosivo, marcacion vial, barnices"),
    # Monterrey
    (50, "Acero / Metalmecanica", "acero", "Acero construccion, calaminas, mallas, perfiles, tubos, electrodos"),
    # Nueva Esperanza S.R.L.
    (51, "Aridos", "agregados", "Arena, grava, entregas en obra"),
    # Picmetrica S.R.L.
    (52, "Construccion", "prefabricados", "Obra fina/gruesa, llave en mano, diseno de interiores"),
    # Plasticos Carmen
    (54, "Tanques", "sanitario", "Bicapa Campeon 300-20000L; tuberia HDPE agua potable/riego"),
    # Plastiforte
    (55, "Tuberias HDPE", "plomeria", "SUPERTUBO 20-1200mm, geomembrana, tanques, silos"),
    # Plussteel
    (56, "Drywall / Perfiles", "acero", "Perfileria acero galvanizado, Drywall, Steelframe, aluminio compuesto"),
    # Postcrete
    (57, "Postensado", "prefabricados", "Losas y fundaciones postensadas, viguetas pretensadas"),
    # Pretbol Constructora
    (58, "Prefabricados hormigon", "prefabricados", "Losetas hexagonales, pavimento rigido, cordones de acera"),
    # Pretensa
    (59, "Viguetas pretensadas", "prefabricados", "Losas huecas, Plastoformo EPS, Tabiplast antisismico"),
    # PT Orias S.R.L.
    (60, "Postensado", "prefabricados", "Losas postensadas, sistemas estructurales, estructuras especiales"),
    # Quark
    (61, "Software", "herramientas", "Software QUARK para costos y presupuestos de construccion"),
    # Quasar Solutions
    (62, "Puesta a tierra", "electrico", "ILLAPA cemento conductivo, Bentonita Ultra Gel, EcoGel, Terranova"),
    # Ready Mix / SOBOCE
    (63, "Hormigon premezclado", "cemento", "H15-H45 para diversas aplicaciones"),
    (63, "Cemento", "cemento", "Eco Fuerte Plus, IP-30, IP-40, Puzolanico"),
    # REMOC Cimentaciones
    (64, "Cimentaciones", "prefabricados", "Pilotes in-situ y CFA, construccion civil, estructuras metalicas"),
    # Roca Fuerte Aridos
    (65, "Aridos", "agregados", "Arenas y gravas para hormigon, aridos pavimento, piedras, cascote"),
    # SACOCI S.R.L.
    (66, "Demolicion / Alquiler", "maquinaria", "Demolicion, voladura, alquiler maquinaria pesada, metalmecanica"),
    # San Rafael
    (67, "Bombas / Pozos", "sanitario", "Bombas de agua, perforacion de pozos, mantenimiento"),
    # Sanear
    (68, "Tanques / Saneamiento", "sanitario", "Tanques bicapa/tricapa, fosas septicas, camaras, banos quimicos"),
    # Sobopret / SOBOCE
    (69, "Viguetas pretensadas", "prefabricados", "Sobopret con complementos Styropor"),
    # Sokolmet
    (70, "Alquiler maquinaria", "maquinaria", "Maquinaria pesada, andamios modulares, puntales, compactadoras"),
    # Synergy
    (71, "Drywall / Sistemas", "acero", "Perfileria, placas yeso, cielo falso PVC, impermeabilizantes, PVC"),
    # TechoBol S.R.L.
    (72, "Calaminas", "techos", "Prepintadas, onduladas, trapezoidales, zincalum; policarbonatos"),
    # Tecnohidro
    (73, "Bombas / Pozos", "sanitario", "Bombas sumergibles/industriales, perforacion pozos 4-12 pulgadas"),
    # Tecnoplan S.R.L.
    (74, "Impermeabilizacion", "impermeabilizantes", "Membrana asfaltica para losas, terrazas, piscinas, tanques"),
    # Tecnopreco
    (75, "Viguetas pretensadas", "prefabricados", "BUNKER, TATAKE, TITAN; graderias, bloques, cordones, baldosas"),
    # Tektron
    (76, "Materiales en seco", "aislantes", "Placas yeso, Drywall, Steel Frame, lana vidrio, SPC/HDF"),
    # Terra Foundations
    (77, "Cimentaciones profundas", "prefabricados", "Pilotes, micropilotes, anclajes, muros pantalla, mejoramiento suelos"),
    # Termocruz
    (78, "Aislacion termica", "aislantes", "Camaras frigorificas industriales, aislamiento de canerias"),
    # Termovid PVC
    (79, "Carpinteria PVC / Aluminio", "vidrios", "Termopanel, persianas, carpinteria aluminio, vidrio templado/laminado"),
    # Tigre
    (80, "Tuberias / Cables", "plomeria", "PVC agua fria/caliente, HDPE, cables cobre/aluminio, desague"),
    # Turf Brasil / Mundo Pisos
    (82, "Acabados / Pisos", "ceramica", "Cesped sintetico, muros verdes, cielo falso PVC, pisos vinilicos SPC"),
    # Valkure Bolivia
    (83, "Adhesivos", "cemento", "Pega ladrillo alta adherencia"),
    # Vitral CBBA
    (84, "Arte / Decoracion", "vidrios", "Vitrales, murales modulares, estructuras luminicas"),
]

# ── Descripciones enriquecidas (solo donde cambia significativamente) ──
# Formato: (prov_id, nueva_descripcion_con_keywords)
# Solo actualizamos si la nueva desc agrega valor de busqueda
DESCRIPTION_UPDATES = {
    8: "Postensado de puentes y edificios; anclajes Freyssinet/OVM, cordon pretensado grado 270K, vainas metalicas; calculo y diseno estructural",
    12: "Ladrillos, tejas, bloques, losetas, rejillas, pisos y baldosas de hormigon; calaminas galvanizadas y de color; complementos para losas",
    18: "Cubiertas fibrocemento: teja ondulada, espanola, Ondina, Residencial; placas Eterboard para Drywall; tanques plasticos para agua",
    29: "Geosinteticos: geomallas, geotextil, geomembrana, geoceldas, geodrenes; sistemas de impermeabilizacion y drenaje vertical; demolicion de rocas",
    33: "Distribuidores oficiales Sika: impermeabilizantes, aditivos; lavamanos, inodoros, griferia, porcelanatos, pisos flotantes SPC-PVC",
    39: "Perfiles acero galvanizado para cerchas y cielo falso; placas de yeso Drywall estandar, humedad y fuego; teja flexiteja y espanola fibrocemento",
    41: "Estructuras metalicas: tinglados, coliseos, galpones; cielos falsos GALVATEX/YESOTEX/PVC/Drywall; vidrio templado/reflectivo, aluminio compuesto",
    63: "Hormigon premezclado H15-H45; cemento Eco Fuerte Plus, IP-30, IP-40, puzolanico. Linea: 800-103-606",
}


def main():
    print(f"Actualizando rubros y descripciones en {APP_URL}...")

    with httpx.Client(verify=False, timeout=15) as c:
        # Step 1: Create rubros (upsert — API skips if exists)
        print(f"\n1. Creando {len(RUBROS)} rubros...")
        created = 0
        skipped = 0
        errors = 0

        for prov_id, rubro, cat_key, desc in RUBROS:
            db_id = PROV_DB.get(prov_id)
            if not db_id:
                print(f"  ! Prov {prov_id}: no tiene mapping a DB ID")
                errors += 1
                continue

            payload = {
                "supplier_id": db_id,
                "rubro": rubro,
                "description": desc,
                "category_key": cat_key,
            }
            resp = c.post(
                f"{APP_URL}/api/v1/integration/supplier-rubros",
                json=payload, headers=HEADERS,
            )
            if resp.status_code == 200:
                data = resp.json()
                action = data.get("action", "created")
                if action == "skipped":
                    skipped += 1
                else:
                    created += 1
            else:
                errors += 1
                if errors <= 3:
                    print(f"  ! Rubro '{rubro}' prov {db_id}: HTTP {resp.status_code}")

        print(f"  Rubros: {created} creados, {skipped} existentes, {errors} errores")

        # Step 2: Update descriptions where enriched
        print(f"\n2. Actualizando {len(DESCRIPTION_UPDATES)} descripciones...")
        updated = 0

        for prov_id, new_desc in DESCRIPTION_UPDATES.items():
            db_id = PROV_DB.get(prov_id)
            if not db_id:
                continue

            # Send only description — SupplierUpdateIn allows partial updates
            resp = c.put(
                f"{APP_URL}/api/v1/integration/suppliers/{db_id}",
                json={"description": new_desc},
                headers=HEADERS,
            )
            if resp.status_code == 200:
                updated += 1
            else:
                print(f"  ! Prov {db_id}: HTTP {resp.status_code}")

        print(f"  Descripciones actualizadas: {updated}")

        # Step 3: Verify
        print(f"\n3. Verificacion")
        resp = c.get(f"{APP_URL}/api/v1/integration/suppliers?limit=1", headers=HEADERS)
        print(f"  Total proveedores activos: {resp.json().get('total', '?')}")

    print("\nDone.")


if __name__ == "__main__":
    main()
