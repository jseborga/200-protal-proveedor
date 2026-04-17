"""Actualiza todos los proveedores con el dataset maestro completo.

Usa SupplierUpdateIn (partial update) — solo envia campos que cambian.
Patron: upsert — busca por nombre, actualiza existente, crea si no existe.

Ejecutar: python scripts/update_all_suppliers.py
"""

import httpx
import os
import json

APP_URL = os.getenv("APP_URL", "https://apu-marketplace-app.q8waob.easypanel.host")
API_KEY = os.getenv("API_KEY", "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

CITY_TO_DEPT = {
    "LPZ": "La Paz",
    "EL ALTO": "La Paz",
    "SCZ": "Santa Cruz",
    "CBBA": "Cochabamba",
    "ORU": "Oruro",
    "PSI": "Potosi",
    "TJA": "Tarija",
    "CHQ": "Chuquisaca",
    "NACIONAL": "Nacional",
}


def parse_cities(raw: str) -> list[str]:
    """Parse city strings like 'CBBA, LPZ/ORU, SCZ/TJA/CBBA' into flat list."""
    cities = set()
    for part in raw.split(","):
        for city in part.strip().split("/"):
            c = city.strip()
            if c:
                cities.add(c)
    return sorted(cities)


# Dataset completo: (user_id, db_id, name, trade_name, cities_raw, phone, phone2, email, website, description, categories)
SUPPLIERS = [
    (1, 3314, "Acermax", "Acermax", "LPZ, EL ALTO, SCZ",
     "+591 67007501", "+591 2 2830778", "info@acermax.com.bo", "www.acermax.com.bo",
     "Fabrica de calaminas plana/ondulada/trapezoidal, teja americana/colonial/espanola, cumbreras; corte, plegado y cilindrado de planchas de acero",
     ["acero", "techos"]),

    (2, 3315, "Aceros Arequipa", "Aceros Arequipa", "SCZ, LPZ, CBBA, EL ALTO",
     "+591 76303499", "+591 77641656", None, None,
     "Produccion de acero de construccion, estribos corrugados, clavos, alambres, conectores mecanicos, mallas electrosoldadas, perfiles, planchas y tubos",
     ["acero", "ferreteria"]),

    (3, 3316, "Aceros Torrico", "Aceros Torrico", "LPZ, SCZ, CBBA",
     "+591 78970158", "+591 78504206", None, "www.acerostorrico.com",
     "Fabrica calaminas zinc-alum y pre-pintadas, perfiles C y U, pernos auto-perforantes, clavos galvanizados, sistema K-span/Arcotecho",
     ["acero", "techos"]),

    (4, 3317, "Acustica.bo", "Acustica.bo", "SCZ",
     "+591 69830577", None, "contacto@acustica.bo", "www.acustica.bo",
     "Soluciones acusticas para viviendas, oficinas, industrias y espacios multiples",
     ["aislantes"]),

    (5, 3318, "Ayudante de tu Hogar", "Ayudante de tu Hogar", "NACIONAL",
     "+591 75221344", None, "contacto@ayudantedetuhogar.com", "www.ayudantedetuhogar.com",
     "Plataforma/app que conecta expertos con clientes para servicios del hogar, mantenimiento y reparacion de electrodomesticos",
     ["herramientas"]),

    (6, 3319, "Bacheo.com.bo", "Bacheo.com.bo", "LPZ, SCZ",
     "+591 2 2118292", "+591 72072067", None, "www.bacheo.com.bo",
     "Asfalto frio EZ Street para mantenimiento vial, canchas deportivas, garajes y parqueos",
     ["agregados"]),

    (7, 3320, "Lab. Batercon (Barrientos Teran)", "Lab. Batercon (Barrientos Teran)", "EL ALTO",
     "+591 71505710", "+591 73206292", "laboratorio@barrientosteran.com", None,
     "Laboratorio de hormigones y suelos: prueba de pilotes, rotura de probetas, dosificacion de mezclas, analisis granulometrico, esclerometria",
     ["maquinaria"]),

    (8, 3321, "Barrientos Teran Consultores", "Barrientos Teran Consultores", "LPZ",
     "+591 71539532", "+591 2 2916182", "info@barrientosteran.com", "www.barrientosteran.com",
     "Servicio de post-tesado en puentes y edificios; anclajes Freyssinet/OVM, acero de pretensado, neoprenos, diseno estructural",
     ["acero", "prefabricados"]),

    (9, 3322, "Boliviaven", "Boliviaven", "LPZ",
     "+591 78949943", "+591 69725314", "info@boliviaven.com", "www.boliviaven.com",
     "Ingenieria y construccion: metalmecanica, estructural, hidroelectrico, HVAC, automatizacion, mantenimiento",
     ["acero", "maquinaria"]),

    (10, 3323, "Cemento Camba", "Cemento Camba", "SCZ",
     "+591 3 3978338", "+591 3 3481007", None, None,
     "Industrializacion y comercializacion de cemento y materiales de construccion",
     ["cemento"]),

    (11, 3324, "Cerabol", "Cerabol", "SCZ",
     "+591 3 3229435", "+591 721 46330", None, "www.cerabol.com",
     "Ceramicas, porcelanatos, marmoles, piedras, revestimientos, semi gres, linea flex",
     ["ceramica"]),

    (12, 3325, "Ceramica Dorado", "Ceramica Dorado", "EL ALTO, LPZ",
     "+591 77284877", "+591 77799267", "juliosusara@gmail.com", "www.ceramicadorado.com",
     "Ladrillos, tejas, complementos para losas, calaminas galvanizadas, bloques, losetas, rejillas, pisos y baldosas de hormigon",
     ["ceramica", "techos"]),

    (13, 3326, "Ceratech", "Ceratech", "LPZ",
     "+591 77299721", "+591 2 2797069", "ceratechsrl@hotmail.com", "www.ceratech-bo.com",
     "Techo Shingle TAMKO, alfombras americanas, porcelanato, tableros OSB/Aglomerado/Multilaminado",
     ["techos", "ceramica"]),

    (14, 3327, "Cimal", "Cimal", "SCZ, EL ALTO, LPZ",
     "+591 3 3462504", "+591 72155238", None, "www.cimal.com.bo",
     "Maderas MDF/melaminicos/venestas/multilaminados; puertas HDF/tablero; tapacantos y accesorios",
     ["madera"]),

    (15, 3328, "Construpanel", "Construpanel", "SCZ",
     "+591 3 3701073", "+591 75022244", "contacto@construpanel.com.bo", "www.construpanel.com.bo",
     "Termo Spray, muros termoacusticos, Phono Spray",
     ["aislantes"]),

    (16, 3329, "Corinsa", "Corinsa", "ORU, LPZ, SCZ",
     "+591 77369939", "+591 2 5262211", None, "corinsa-srl.com",
     "Gaviones, colchonetas, malla hexagonal, alambre de puas, clavos, grapas, alambre galvanizado, viruta de acero VIRULIM",
     ["acero"]),

    (17, 3330, "DJ Importaciones", "DJ Importaciones", "EL ALTO, LPZ",
     "+591 71557243", None, "contactos@djimportaciones.com", "www.djimportaciones.com",
     "Pisos flotantes LAMIWOOD, cielos falsos DECORAM",
     ["ceramica"]),

    (18, 3331, "Duralit", "Duralit", "CBBA, LPZ/ORU, SCZ",
     "+591 79799764", None, None, "www.duralit.com",
     "Cubiertas fibrocemento (teja ondulada/espanola/Ondina/Residencial), techos plasticos, tanques, placas Eterboard para Drywall",
     ["techos", "sanitario"]),

    (19, 3332, "ECEBOL", "ECEBOL", "LPZ, ORU, PSI",
     "+591 2 2147001", None, "ventas@ecebol.com.bo", "ecebol.com.bo",
     "Cemento IP-30 e IP-40 en sacos 50Kg, Big Bag 1.5Tn y granel hasta 27Tn. Linea gratuita: 800 10 1707",
     ["cemento"]),

    (20, 3333, "Electrored", "Electrored", "LPZ, SCZ, CBBA",
     "+591 2 2282428", "+591 3 3368888", None, "electrored.store",
     "Importacion y distribucion de materiales electricos en general",
     ["electrico"]),

    (21, 3334, "Eurocable", "Eurocable", "LPZ",
     "+591 2 2710961", "+591 76719240", "info@eurocable.net", "www.eurocable.net",
     "Piso radiante electrico y calefactores para exteriores",
     ["electrico"]),

    (22, 3335, "Faboce", "Faboce", "CBBA, SCZ, LPZ",
     "+591 4 4746485", None, None, "www.faboce.com.bo",
     "Revestimientos y acabados: tecnogranito, porcelanato, tecnogres, gres porcelanico, lapados, ceramica premium",
     ["ceramica"]),

    (23, 3336, "Facil Cementos Adhesivos", "Facil Cementos Adhesivos", "LPZ",
     "+591 67300277", "+591 2 2712798", None, None,
     "Cemento cola ceramica/porcelanato, pega ladrillo, revoque fino para fachadas y paredes",
     ["cemento", "ceramica"]),

    (24, 3337, "Famequi", "Famequi", "CBBA, SCZ",
     "+591 4 4314631", "+591 71420288", "famequi-jk@hotmail.com", None,
     "Fabrica de maquinaria: tanques hidropulmon, mezcladoras, guinches, sondas, vibradoras, elevadores",
     ["maquinaria"]),

    (25, 3338, "Faragauss Bolivia", "Faragauss Bolivia", "LPZ",
     "+591 2 2246122", "+591 71542281", "contacto@pseing.com", "www.faragaussbolivia.com",
     "Tecnologia electromagnetica: puesta a tierra (acoplamiento magneto activo), pararrayos, proteccion catodica",
     ["electrico"]),

    (26, 3339, "Ferrotodo", "Ferrotodo", "SCZ, LPZ, CBBA",
     "+591 3 3711000", "+591 2 2460760", None, None,
     "Comercializacion de maquinarias, materiales y metalmecanica: tubos, perfiles galvanizados, alambres, mallas electrosoldadas",
     ["acero", "ferreteria"]),

    (27, 3340, "Galindo Ingenieria", "Galindo Ingenieria", "LPZ",
     "+591 72044342", None, "contacto@galindoingenieria.com", "www.galindoingenieria.com",
     "Diseno y calculo estructural, ingenieria sismica, patologia estructural, supervision y consultoria",
     ["acero"]),

    (28, 3341, "Gestual Arquitectura", "Gestual Arquitectura", "LPZ",
     "+591 62322006", None, None, None,
     "Estudio de arquitectura, diseno arquitectonico y de interiores",
     []),

    (29, 3342, "Grupo R&N", "Grupo R&N", "LPZ, SCZ",
     "+591 2 2773627", "+591 76534943", "contacto@gruporyn.net", "www.gruporyn.net",
     "Geomallas, geomantos, geotextil, geomembrana, geoceldas; impermeabilizacion, drenaje vertical, demolicion de rocas",
     ["impermeabilizantes"]),

    (30, 3343, "Hansa", "Hansa", "LPZ, CBBA, SCZ",
     "+591 2 2149800", "+591 72037846", None, None,
     "Naves industriales, obra gruesa/fina, equipamientos, sistemas contraincendios, electricos; domotica avanzada",
     ["acero", "maquinaria"]),

    (31, 3344, "Hidronyx", "Hidronyx", "LPZ",
     "+591 70120080", "+591 64125477", "hidronyx@gmail.com", None,
     "Tanques plasticos bicapa/tricapa 300-10,000L, cisternas, camaras septicas, bebederos",
     ["sanitario", "plomeria"]),

    (32, 3345, "ICI Ltda.", "ICI Ltda.", "LPZ",
     "+591 78934730", "+591 2 2440944", "ici_ltda.lp@hotmail.com", "www.iciltda.com",
     "Equipos para instalacion de gas natural: medidores domesticos/comerciales/industriales, reguladores, valvulas",
     ["sanitario"]),

    (33, 3346, "IMCAR (Dist. Sika)", "IMCAR (Dist. Sika)", "LPZ",
     "+591 77242420", "+591 71526027", "imcar@mail.com", None,
     "Distribuidores oficiales Sika; lavamanos, inodoros, griferia, porcelanatos, pisos flotantes SPC-PVC",
     ["impermeabilizantes", "sanitario"]),

    (34, 3347, "Importadora Alarcon", "Importadora Alarcon", "SCZ, CBBA",
     "+591 3 3557100", "+591 70953567", "ventas@importadora-alarcon.com.bo", "www.importadora-alarcon.com.bo",
     "Canerias para agua fria/caliente, tubos polipropileno desague, membranas aislantes, tuberias gas domiciliario",
     ["plomeria", "sanitario"]),

    (35, 3348, "Importadora Duran", "Importadora Duran", "EL ALTO, LPZ",
     "+591 2 2829541", "+591 67349325", None, "www.importadoraduran.com",
     "Cubiertas policarbonato, pisos flotantes HDF/SPC, zocalos, cielos falsos PVC, aluminio compuesto, luminarias LED",
     ["ceramica", "techos"]),

    (36, 3349, "Importadora Z. Santos", "Importadora Z. Santos", "EL ALTO",
     "+591 2 2850866", "+591 71231350", "importsantos@yahoo.es", None,
     "Vainas corrugadas, cordon pretensado grado 270K, anclajes Freyssinet/OVM, servicio de tesado e inyectado",
     ["acero", "prefabricados"]),

    (37, 3350, "INGCO Bolivia", "INGCO Bolivia", "EL ALTO, SCZ",
     "+591 71241833", "+591 71570898", None, "www.ingcobolivia.com",
     "Herramientas manuales, electricas, neumaticas, de banco; generadores y bombas de agua",
     ["herramientas"]),

    (38, 3351, "Inno Domotics", "Inno Domotics", "SCZ, CBBA",
     "+591 3 3393974", None, "sc@innodomotics.com", "www.innodomotics.com",
     "Automatizacion domotica: home theater, asesoramiento, proyectos, soporte tecnico, instalaciones especiales",
     ["electrico"]),

    (39, 3352, "Innoplack", "Innoplack", "SCZ",
     "+591 71349585", "+591 62000359", "ventas@innoplack.com", "www.innoplack.com",
     "Perfiles acero galvanizado para cerchas/cielo falso, placas de yeso Drywall (estandar, humedad, fuego), teja fibrocemento",
     ["acero", "techos"]),

    (40, 3353, "Inkaforte (Brizio)", "Inkaforte (Brizio)", "LPZ",
     "+591 735952554", None, "inkaforte@inka-forte.com", "www.inka-forte.com",
     "Cemento cola para ceramica y porcelanato; alta adherencia en pisos y paredes",
     ["cemento", "ceramica"]),

    (41, 3354, "Intermec S.R.L.", "Intermec S.R.L.", "CBBA, LPZ",
     "+591 4 4449686", "+591 60700143", "intermec.bo@gmail.com", "www.intermecsrl.com",
     "Estructuras metalicas, tinglados, coliseos, cielos falsos GALVATEX/YESOTEX, vidrio templado, aluminio compuesto",
     ["acero", "vidrios"]),

    (42, 3355, "Isocret", "Isocret", "EL ALTO",
     "+591 61005252", None, "ventas@isocret.com.bo", "www.isocret.com.bo",
     "Viguetas pretensadas, styropor expandido, hormigon industrial, postes curvos, calculo de estructuras",
     ["prefabricados"]),

    (43, 3356, "Isolcruz", "Isolcruz", "SCZ",
     "+591 3 3888774", "+591 71343157", "info@isolcruz.com", "www.isolcruz.com",
     "EPS isoteja/isopanel, poliuretano frigopanel, termo/phono spray, poliisocianurato, muros termoacusticos",
     ["aislantes"]),

    (44, 3357, "Las Lomas", "Las Lomas", "LPZ, CBBA, SCZ",
     "+591 2 2821021", "+591 4 4227729", None, "www.laslomas.com.bo",
     "Importacion de fierro de construccion DEDINI corrugado y liso, planchas, angulares, pletinas",
     ["acero"]),

    (45, 3358, "Mamut", "Mamut", "CBBA, SCZ, LPZ",
     "+591 70341775", "+591 4 4486243", "manuel.laredo@pisosmamut.com", None,
     "Baldosa amortiguante EPDM, pavimento continuo, piso podotactil, industrial y deportivo de poliuretano",
     ["ceramica"]),

    (46, 3359, "Maqualq S.R.L.", "Maqualq S.R.L.", "LPZ",
     "+591 2 2912823", "+591 77706766", "quiroga.maqalq@hotmail.com", None,
     "Construccion de edificios y obras civiles; alquiler de andamios, puntales, compactadora, mezcladora, vibradora",
     ["maquinaria"]),

    (47, 3360, "Maquiobras", "Maquiobras", "SCZ",
     "+591 70314533", "+591 69045456", None, "sites.google.com/view/maquiobras",
     "Construccion/mantenimiento civil, pintura e impermeabilizacion, diseno y remodelacion, negocios inmobiliarios",
     ["pintura", "impermeabilizantes"]),

    (48, 3361, "Marcav", "Marcav", "CHQ, PSI/ORU/LPZ, SCZ/TJA/CBBA",
     "+591 77110060", "+591 72881248", "empresamarcav@gmail.com", None,
     "Provision e instalacion de geomembrana y geotextil; termofusion de tuberias HDPE; impermeabilizacion de suelos",
     ["impermeabilizantes", "plomeria"]),

    (49, 3362, "Monopol", "Monopol", "LPZ, SCZ, CBBA",
     "+591 2 2180222", None, None, "pinturasmonopol.com",
     "Pinturas latex arquitectonicas, anticorrosivas, de marcacion vial; barnices, pegamentos, impermeabilizantes",
     ["pintura"]),

    (50, 3363, "Monterrey", "Monterrey", "SCZ, EL ALTO",
     "+591 3 3471960", "+591 2 2860363", None, "www.monterrey.com.bo",
     "Acero de construccion, clavos, calaminas, mallas, perfiles, planchas, tubos, equipos de soldar",
     ["acero", "ferreteria"]),

    (51, 3364, "Nueva Esperanza S.R.L.", "Nueva Esperanza S.R.L.", "LPZ, EL ALTO",
     "+591 70135605", "+591 70118600", "info@ecnuevaesperanza.com", None,
     "Arena, grava, entregas en obra",
     ["agregados"]),

    (52, 3365, "Picmetrica S.R.L.", "Picmetrica S.R.L.", "LPZ",
     "+591 63091512", None, "gerenciageneral@picmetrica.com", "constructorapicmetrica-srl.com",
     "Obra fina y gruesa, llave en mano, diseno de interiores, proyectos comerciales/residenciales, supervision",
     []),

    (53, 3366, "Piedra Liquida Bolivia", "Piedra Liquida Bolivia", "LPZ, SCZ",
     "+591 63091512", "+591 75262959", "piedraliquidabolivia@gmail.com", None,
     "Revestimientos para fachadas, pisos, gradas, paredes; diseno de interiores y exteriores; encimeras",
     ["ceramica"]),

    (54, 3367, "Plasticos Carmen", "Plasticos Carmen", "SCZ",
     "+591 3 3332762", "+591 72042942", None, "www.plasticoscarmen.com",
     "Tanques bicapa y tricapa, cisternas, camaras septicas, bebederos, tuberia PEAD/HDPE. Linea: 800-10-9005",
     ["plomeria", "sanitario"]),

    (55, 3368, "Plastiforte", "Plastiforte", "CBBA, SCZ, LPZ, CHQ, ORU, PSI, TJA",
     "+591 4 4433270", None, "ventas@plastiforte.com", "www.plastiforte.com",
     "SUPERTUBO HDPE 20-1200mm, accesorios SUPERJUNTA, tuberia corrugada, geomembrana, tanques, silos",
     ["plomeria", "impermeabilizantes"]),

    (56, 3369, "Plussteel", "Plussteel", "SCZ, CBBA, LPZ, EL ALTO",
     "+591 3 3347777", "+591 78519872", None, None,
     "Perfileria acero galvanizado, Drywall, Steelframe, cerchas metalicas, placas yeso/cementica, aluminio compuesto Hunter Douglas",
     ["acero", "techos"]),

    (57, 3370, "Postcrete", "Postcrete", "LPZ, CBBA, SCZ",
     "+591 72558308", "+591 7704893", "aramos@postcrete.com", "www.postcrete.com",
     "Losas y fundaciones postensadas, viguetas pretensadas",
     ["prefabricados", "acero"]),

    (58, 3371, "Pretbol Constructora", "Pretbol Constructora", "SCZ",
     "+591 73685996", None, "pretbolsrl@gmail.com", None,
     "Prefabricados de hormigon, losetas hexagonales, pavimento rigido, cordones de acera, postes curvos, malla olimpica",
     ["prefabricados"]),

    (59, 3372, "Pretensa", "Pretensa", "LPZ, EL ALTO",
     "+591 2 2745474", "+591 77612273", "pretensa.mkt@gmail.com", "pretensaltda.com",
     "Viguetas pretensadas, losas huecas, muro de contencion, Plastoformo EPS, Tabiplast antisismico",
     ["prefabricados"]),

    (60, 3373, "PT Orias S.R.L.", "PT Orias S.R.L.", "SCZ",
     "+591 71099805", None, "ico_2005@yahoo.com", None,
     "Sistemas estructurales postensados, losas postensadas, estructuras especiales",
     ["prefabricados", "acero"]),

    (61, 3374, "Quark Costos y Presupuestos", "Quark Costos y Presupuestos", "LPZ",
     "+591 2 2421368", "+591 71592932", "webmaster@quark-costos.com", "www.quark-costos.com",
     "Software especializado para ingenieria, arquitectura y construccion - sistema QUARK",
     ["herramientas"]),

    (62, 3375, "Quasar Solutions", "Quasar Solutions", "LPZ",
     "+591 2 310832", "+591 73718195", "ventas@quasar.com.bo", "www.quasar.com.bo",
     "Materiales puesta a tierra: Cemento Conductivo ILLAPA, Bentonita Ultra Gel, EcoGel, Terranova (hecho en Bolivia)",
     ["electrico"]),

    (63, 3376, "Ready Mix Bolivia / SOBOCE", "Ready Mix Bolivia / SOBOCE", "SCZ, LPZ, CBBA, ORU, TJA",
     "+591 3 3449939", "+591 2 2406040", None, "www.soboce.com",
     "Hormigon premezclado H15-H45; cemento Eco Fuerte Plus, IP-30, IP-40, puzolanico. Linea: 800-103-606",
     ["cemento"]),

    (64, 3377, "REMOC Cimentaciones", "REMOC Cimentaciones", "CBBA",
     "+591 72152000", "+591 73710666", None, None,
     "Perforacion de pilotes in-situ y CFA, hormigon premezclado, construccion civil, montaje estructuras metalicas",
     ["prefabricados"]),

    (65, 3378, "Roca Fuerte Aridos", "Roca Fuerte Aridos", "EL ALTO, LPZ",
     "+591 71561962", "+591 71563286", "aridosrocafuerte7@gmail.com", None,
     "Arenas y gravas para hormigon, aridos para pavimento, piedras, cascote, servicio de transporte a obra",
     ["agregados"]),

    (66, 3379, "SACOCI S.R.L.", "SACOCI S.R.L.", "EL ALTO",
     "+591 77777726", "+591 77295388", "sacoci_bol@yahoo.es", "www.sacocisrl.com",
     "Demolicion y voladura, alquiler maquinaria pesada, mantenimiento, arquitectura y metalmecanica",
     ["maquinaria"]),

    (67, 3380, "San Rafael", "San Rafael", "CBBA, SCZ, ORU",
     "+591 76920124", "+591 77444329", None, "www.sanrafael.com.bo",
     "Bombas de agua, perforacion de pozos, asistencia tecnica y mantenimiento",
     ["sanitario", "maquinaria"]),

    (68, 3381, "Sanear", "Sanear", "SCZ, EL ALTO, CBBA, PSI, ORU, CHQ",
     "+591 710 19333", None, "ventas.nal@stpsanear.com", None,
     "Tanques polietileno tricapa/bicapa, fosas septicas, camaras de inspeccion, banos quimicos, sanitarios portatiles",
     ["sanitario"]),

    (69, 3382, "Sobopret / SOBOCE", "Sobopret / SOBOCE", "SCZ, LPZ, CBBA, ORU, TJA",
     "+591 3 3449939", "+591 2 2406040", None, "www.soboce.com",
     "Viguetas pretensadas Sobopret, complementos Styropor expandido",
     ["prefabricados"]),

    (70, 3383, "Sokolmet", "Sokolmet", "LPZ",
     "+591 79523922", "+591 70551647", "informacion@sokolmet.com", "www.sokolmet.com",
     "Alquiler maquinaria de construccion, andamios modulares, puntales metalicos, compactadoras, mezcladoras",
     ["maquinaria"]),

    (71, 3384, "Synergy", "Synergy", "SCZ, CBBA, LPZ, TJA",
     "+591 3 3420345", None, None, None,
     "Perfileria acero galvanizado, placas yeso, cielo falso PVC, impermeabilizantes, pisos vinilicos, puertas/ventanas PVC",
     ["acero", "techos"]),

    (72, 3385, "TechoBol S.R.L.", "TechoBol S.R.L.", "CBBA",
     "+591 4 4330651", "+591 69530554", None, None,
     "Calaminas prepintadas/onduladas/trapezoidales/tipo teja/zincalum; policarbonatos; ganchos/clavos/autoperforantes",
     ["techos"]),

    (73, 3386, "Tecnohidro", "Tecnohidro", "LPZ",
     "+591 2 2126862", "+591 71573634", "tecnohidro-ventas@hotmail.com", None,
     "Bombas de agua industriales/sumergibles, generadores, perforacion y limpieza de pozos 4-12 pulgadas",
     ["sanitario", "maquinaria"]),

    (74, 3387, "Tecnoplan S.R.L.", "Tecnoplan S.R.L.", "LPZ",
     "+591 2 2434930", "+591 70181122", "tecnoplan_srl@hotmail.com", None,
     "Membrana asfaltica para impermeabilizacion de losas, terrazas, piscinas; constructora con +35 anos",
     ["impermeabilizantes"]),

    (75, 3388, "Tecnopreco", "Tecnopreco", "LPZ, SCZ",
     "+591 70513827", None, None, "www.tecnopreco.com",
     "Viguetas pretensadas BUNKER/TATAKE/TITAN, Plastoformo EPS, graderias, bloques, cordones, baldosas, postes, muro perimetral",
     ["prefabricados"]),

    (76, 3389, "Tektron", "Tektron", "LPZ, EL ALTO, CBBA, SCZ",
     "+591 76767808", None, "contacto@tektron.com.bo", "www.tektron.com.bo",
     "Placas yeso, Drywall, perfileria liviana, placas cementicias, Steel Frame, lana de fibra de vidrio, SPC/HDF, aluminio compuesto",
     ["acero", "aislantes"]),

    (77, 3390, "Terra Foundations", "Terra Foundations", "LPZ, SCZ",
     "+591 2 2776248", "+591 3 3120996", "info@terrafoundations.com.bo", "www.terrafoundations.com",
     "Pilotes, micropilotes, anclajes, Soil Nailing, inyecciones, muros pantalla y berlineses, mejoramiento de suelos",
     ["prefabricados"]),

    (78, 3391, "Termocruz", "Termocruz", "SCZ",
     "+591 70860219", "+591 79054874", "cevbozo@outlook.com", None,
     "Aislacion termica industrial linea frio/caliente; camaras frigorificas industriales; aislamiento de canerias",
     ["aislantes"]),

    (79, 3392, "Termovid PVC", "Termovid PVC", "CBBA",
     "+591 75921686", "+591 77449572", "termovidpvc@gmail.com", None,
     "Termopanel TERMOVID, persianas, carpinteria de aluminio estandar y con ruptura de puente termico, vidrio templado/laminado",
     ["vidrios"]),

    (80, 3393, "Tigre", "Tigre", "SCZ, LPZ, EL ALTO",
     "+591 3 3147210", "+591 2 2147220", None, None,
     "Tuberias y accesorios PVC agua caliente/fria, HDPE, cables conductores cobre/aluminio, tuberia desague",
     ["plomeria", "electrico"]),

    (81, 3394, "TrabajAhora", "TrabajAhora", "NACIONAL",
     "+591 75221344", None, "contact-info@andystfort.com", "www.trabajahora.andystfort.com",
     "App para buscar empleo o contratar: filtros por ciudad/categoria, publicacion de vacantes, evaluacion previa",
     ["herramientas"]),

    (82, 3395, "Turf Brasil / Mundo Pisos", "Turf Brasil / Mundo Pisos", "LPZ, EL ALTO, SCZ",
     "+591 77761063", "+591 76732376", None, "www.mundo-pisos.com",
     "Cesped sintetico, muros verdes, cielo falso PVC, panel ripado, pisos vinilicos SPC, revestimientos de pared",
     ["ceramica"]),

    (83, 3396, "Valkure Bolivia", "Valkure Bolivia", "LPZ",
     "+591 61000354", None, "comercial@valkurebolivia.com", None,
     "Pega ladrillo de alta adherencia con dosificacion controlada",
     ["cemento"]),

    (84, 3397, "Vitral CBBA", "Vitral CBBA", "CBBA",
     "+591 63964389", "+591 79336680", None, None,
     "Vitrales y murales modulares, estructuras luminicas, murales modernos",
     ["vidrios"]),

    (85, 3398, "Plasticos Carmen (Campeon)", "Plasticos Carmen (Campeon)", "SCZ",
     "+591 3 3332762", "+591 72042942", None, "www.plasticoscarmen.com",
     "Tanque bicapa Campeon 300-20000L, tubos HDPE para agua potable, riego, drenaje y cableado electrico",
     ["sanitario", "plomeria"]),
]


def normalize(val):
    """Normalize for comparison — strip whitespace, lowercase."""
    if val is None:
        return ""
    return str(val).strip().lower()


def main():
    print(f"Actualizando {len(SUPPLIERS)} proveedores en {APP_URL}...")

    # Step 1: Get current state
    with httpx.Client(verify=False, timeout=15) as c:
        resp = c.get(f"{APP_URL}/api/v1/integration/suppliers?limit=200", headers=HEADERS)
        current_data = resp.json()["data"]
        current_by_id = {s["id"]: s for s in current_data}

        updated = 0
        skipped = 0
        errors = 0

        for user_id, db_id, name, trade_name, cities_raw, phone, phone2, email, website, desc, cats in SUPPLIERS:
            current = current_by_id.get(db_id)
            if not current:
                print(f"  ! ID {db_id} ({name}): no encontrado en DB")
                errors += 1
                continue

            # Parse operating cities
            op_cities = parse_cities(cities_raw)
            primary_city = op_cities[0] if op_cities else ""
            dept = CITY_TO_DEPT.get(primary_city, "")

            # Build update payload — only fields that differ
            payload = {}

            if normalize(current.get("name")) != normalize(name):
                payload["name"] = name
            if normalize(current.get("trade_name")) != normalize(trade_name):
                payload["trade_name"] = trade_name
            if normalize(current.get("phone")) != normalize(phone):
                payload["phone"] = phone
            if normalize(current.get("phone2") or "") != normalize(phone2 or ""):
                payload["phone2"] = phone2
            if normalize(current.get("email") or "") != normalize(email or ""):
                payload["email"] = email
            if normalize(current.get("website") or "") != normalize(website or ""):
                payload["website"] = website
            if normalize(current.get("description") or "") != normalize(desc):
                payload["description"] = desc
            if normalize(current.get("city") or "") != normalize(primary_city):
                payload["city"] = primary_city
            if normalize(current.get("department") or "") != normalize(dept):
                payload["department"] = dept

            # Compare categories (sorted)
            current_cats = sorted(current.get("categories") or [])
            if current_cats != sorted(cats):
                payload["categories"] = cats

            # Compare operating cities (sorted)
            current_op = sorted(current.get("operating_cities") or [])
            if current_op != sorted(op_cities):
                payload["operating_cities"] = op_cities

            if not payload:
                skipped += 1
                continue

            # Send partial update
            resp = c.put(
                f"{APP_URL}/api/v1/integration/suppliers/{db_id}",
                json=payload, headers=HEADERS,
            )
            if resp.status_code == 200:
                updated += 1
                fields = ", ".join(payload.keys())
                print(f"  + {name} (ID {db_id}): {fields}")
            else:
                errors += 1
                print(f"  ! {name} (ID {db_id}): HTTP {resp.status_code} — {resp.text[:100]}")

        print(f"\nResultado: {updated} actualizados, {skipped} sin cambios, {errors} errores")
        print(f"Total proveedores: {len(SUPPLIERS)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
