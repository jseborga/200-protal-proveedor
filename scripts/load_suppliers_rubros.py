"""Carga masiva de 85 proveedores con info de contacto.

Ejecutar: python scripts/load_suppliers_rubros.py
Requiere: APP_URL y API_KEY (o usa defaults de produccion)
"""

import httpx
import os

APP_URL = os.getenv("APP_URL", "https://apu-marketplace-app.q8waob.easypanel.host")
API_KEY = os.getenv("API_KEY", "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

CITY_TO_DEPT = {
    "LPZ": "La Paz", "EL ALTO": "La Paz", "SCZ": "Santa Cruz",
    "CBBA": "Cochabamba", "ORU": "Oruro", "CHQ": "Chuquisaca",
    "SUC": "Chuquisaca", "TJA": "Tarija", "PSI": "Potosi",
    "PTI": "Potosi", "BEN": "Beni", "PAN": "Pando",
    "NACIONAL": "Nacional", "BOLIVIA": "Nacional",
}

# ── Dataset completo: 85 proveedores ─────────────────────────
SUPPLIERS = [
    {
        "name": "Acermax",
        "categories": ["acero", "techos"],
        "operating_cities": ["LPZ", "EL ALTO", "SCZ"],
        "phone": "+591 67007501", "phone2": "+591 2 2830778",
        "email": "info@acermax.com.bo", "website": "www.acermax.com.bo",
        "description": "Fabrica de calaminas plana/ondulada/trapezoidal, teja americana/colonial/espanola, cumbreras; corte, plegado y cilindrado de planchas de acero",
    },
    {
        "name": "Aceros Arequipa",
        "categories": ["acero", "ferreteria"],
        "operating_cities": ["SCZ", "LPZ", "CBBA", "EL ALTO"],
        "phone": "+591 76303499", "phone2": "+591 77641656",
        "email": None, "website": None,
        "description": "Produccion de acero de construccion, estribos corrugados, clavos, alambres, conectores mecanicos, mallas electrosoldadas, perfiles, planchas y tubos",
    },
    {
        "name": "Aceros Torrico",
        "categories": ["acero", "techos"],
        "operating_cities": ["LPZ", "SCZ", "CBBA"],
        "phone": "+591 78970158", "phone2": "+591 78504206",
        "email": None, "website": "www.acerostorrico.com",
        "description": "Fabrica calaminas zinc-alum y pre-pintadas, perfiles C y U, pernos auto-perforantes, clavos galvanizados, sistema K-span/Arcotecho",
    },
    {
        "name": "Acustica.bo",
        "categories": ["aislantes"],
        "operating_cities": ["SCZ"],
        "phone": "+591 69830577", "phone2": None,
        "email": "contacto@acustica.bo", "website": "www.acustica.bo",
        "description": "Soluciones acusticas para viviendas, oficinas, industrias y espacios multiples",
    },
    {
        "name": "Ayudante de tu Hogar",
        "categories": ["herramientas"],
        "operating_cities": ["NACIONAL"],
        "phone": "+591 75221344", "phone2": None,
        "email": "contacto@ayudantedetuhogar.com", "website": "www.ayudantedetuhogar.com",
        "description": "Plataforma/app que conecta expertos con clientes para servicios del hogar, mantenimiento y reparacion de electrodomesticos",
    },
    {
        "name": "Bacheo.com.bo",
        "categories": ["agregados"],
        "operating_cities": ["LPZ", "SCZ"],
        "phone": "+591 2 2118292", "phone2": "+591 72072067",
        "email": None, "website": "www.bacheo.com.bo",
        "description": "Asfalto frio EZ Street para mantenimiento vial, canchas deportivas, garajes y parqueos",
    },
    {
        "name": "Lab. Batercon (Barrientos Teran)",
        "categories": ["maquinaria"],
        "operating_cities": ["EL ALTO"],
        "phone": "+591 71505710", "phone2": "+591 73206292",
        "email": "laboratorio@barrientosteran.com", "website": None,
        "description": "Laboratorio de hormigones y suelos: prueba de pilotes, rotura de probetas, dosificacion de mezclas, analisis granulometrico, esclerometria",
    },
    {
        "name": "Barrientos Teran Consultores",
        "categories": ["acero", "prefabricados"],
        "operating_cities": ["LPZ"],
        "phone": "+591 71539532", "phone2": "+591 2 2916182",
        "email": "info@barrientosteran.com", "website": "www.barrientosteran.com",
        "description": "Servicio de post-tesado en puentes y edificios; anclajes Freyssinet/OVM, acero de pretensado, neoprenos, diseno estructural",
    },
    {
        "name": "Boliviaven",
        "categories": ["acero", "maquinaria"],
        "operating_cities": ["LPZ"],
        "phone": "+591 78949943", "phone2": "+591 69725314",
        "email": "info@boliviaven.com", "website": "www.boliviaven.com",
        "description": "Ingenieria y construccion: metalmecanica, estructural, hidroelectrico, HVAC, automatizacion, mantenimiento",
    },
    {
        "name": "Cemento Camba",
        "categories": ["cemento"],
        "operating_cities": ["SCZ"],
        "phone": "+591 3 3978338", "phone2": "+591 3 3481007",
        "email": None, "website": None,
        "description": "Industrializacion y comercializacion de cemento y materiales de construccion",
    },
    {
        "name": "Cerabol",
        "categories": ["ceramica"],
        "operating_cities": ["SCZ"],
        "phone": "+591 3 3229435", "phone2": "+591 721 46330",
        "email": None, "website": "www.cerabol.com",
        "description": "Ceramicas, porcelanatos, marmoles, piedras, revestimientos, semi gres, linea flex",
    },
    {
        "name": "Ceramica Dorado",
        "categories": ["ceramica", "techos"],
        "operating_cities": ["EL ALTO", "LPZ"],
        "phone": "+591 77284877", "phone2": "+591 77799267",
        "email": "juliosusara@gmail.com", "website": "www.ceramicadorado.com",
        "description": "Ladrillos, tejas, complementos para losas, calaminas galvanizadas, bloques, losetas, rejillas, pisos y baldosas de hormigon",
    },
    {
        "name": "Ceratech",
        "categories": ["techos", "ceramica"],
        "operating_cities": ["LPZ"],
        "phone": "+591 77299721", "phone2": "+591 2 2797069",
        "email": "ceratechsrl@hotmail.com", "website": "www.ceratech-bo.com",
        "description": "Techo Shingle TAMKO, alfombras americanas, porcelanato, tableros OSB/Aglomerado/Multilaminado",
    },
    {
        "name": "Cimal",
        "categories": ["madera"],
        "operating_cities": ["SCZ", "EL ALTO", "LPZ"],
        "phone": "+591 3 3462504", "phone2": "+591 72155238",
        "email": None, "website": "www.cimal.com.bo",
        "description": "Maderas MDF/melaminicos/venestas/multilaminados; puertas HDF/tablero; tapacantos y accesorios",
    },
    {
        "name": "Construpanel",
        "categories": ["aislantes"],
        "operating_cities": ["SCZ"],
        "phone": "+591 3 3701073", "phone2": "+591 75022244",
        "email": "contacto@construpanel.com.bo", "website": "www.construpanel.com.bo",
        "description": "Termo Spray, muros termoacusticos, Phono Spray",
    },
    {
        "name": "Corinsa",
        "categories": ["acero"],
        "operating_cities": ["ORU", "LPZ", "SCZ"],
        "phone": "+591 77369939", "phone2": "+591 2 5262211",
        "email": None, "website": "corinsa-srl.com",
        "description": "Gaviones, colchonetas, malla hexagonal, alambre de puas, clavos, grapas, alambre galvanizado, viruta de acero VIRULIM",
    },
    {
        "name": "DJ Importaciones",
        "categories": ["ceramica"],
        "operating_cities": ["EL ALTO", "LPZ"],
        "phone": "+591 71557243", "phone2": None,
        "email": "contactos@djimportaciones.com", "website": "www.djimportaciones.com",
        "description": "Pisos flotantes LAMIWOOD, cielos falsos DECORAM",
    },
    {
        "name": "Duralit",
        "categories": ["techos"],
        "operating_cities": ["CBBA", "LPZ", "SCZ"],
        "phone": "+591 79799764", "phone2": None,
        "email": None, "website": "www.duralit.com",
        "description": "Cubiertas fibrocemento (teja ondulada/espanola/Ondina/Residencial), techos plasticos, tanques, placas Eterboard para Drywall",
    },
    {
        "name": "ECEBOL",
        "categories": ["cemento"],
        "operating_cities": ["LPZ", "ORU", "PSI"],
        "phone": "+591 2 2147001", "phone2": None,
        "email": "ventas@ecebol.com.bo", "website": "ecebol.com.bo",
        "description": "Cemento IP-30 e IP-40 en sacos 50Kg, Big Bag 1.5Tn y granel hasta 27Tn. Linea gratuita: 800 10 1707",
    },
    {
        "name": "Electrored",
        "categories": ["electrico"],
        "operating_cities": ["LPZ", "SCZ", "CBBA"],
        "phone": "+591 2 2282428", "phone2": "+591 3 3368888",
        "email": None, "website": "electrored.store",
        "description": "Importacion y distribucion de materiales electricos en general",
    },
    {
        "name": "Eurocable",
        "categories": ["electrico"],
        "operating_cities": ["LPZ"],
        "phone": "+591 2 2710961", "phone2": "+591 76719240",
        "email": "info@eurocable.net", "website": "www.eurocable.net",
        "description": "Piso radiante electrico y calefactores para exteriores",
    },
    {
        "name": "Faboce",
        "categories": ["ceramica"],
        "operating_cities": ["CBBA", "SCZ", "LPZ"],
        "phone": "+591 4 4746485", "phone2": None,
        "email": None, "website": "www.faboce.com.bo",
        "description": "Revestimientos y acabados: tecnogranito, porcelanato, tecnogres, gres porcelanico, lapados, ceramica premium",
    },
    {
        "name": "Facil Cementos Adhesivos",
        "categories": ["cemento", "ceramica"],
        "operating_cities": ["LPZ"],
        "phone": "+591 67300277", "phone2": "+591 2 2712798",
        "email": None, "website": None,
        "description": "Cemento cola ceramica/porcelanato, pega ladrillo, revoque fino para fachadas y paredes",
    },
    {
        "name": "Famequi",
        "categories": ["maquinaria"],
        "operating_cities": ["CBBA", "SCZ"],
        "phone": "+591 4 4314631", "phone2": "+591 71420288",
        "email": "famequi-jk@hotmail.com", "website": None,
        "description": "Fabrica de maquinaria: tanques hidropulmon, mezcladoras, guinches, sondas, vibradoras, elevadores",
    },
    {
        "name": "Faragauss Bolivia",
        "categories": ["electrico"],
        "operating_cities": ["LPZ"],
        "phone": "+591 2 2246122", "phone2": "+591 71542281",
        "email": "contacto@pseing.com", "website": "www.faragaussbolivia.com",
        "description": "Tecnologia electromagnetica: puesta a tierra (acoplamiento magneto activo), pararrayos, proteccion catodica",
    },
    {
        "name": "Ferrotodo",
        "categories": ["acero", "ferreteria"],
        "operating_cities": ["SCZ", "LPZ", "CBBA"],
        "phone": "+591 3 3711000", "phone2": "+591 2 2460760",
        "email": None, "website": None,
        "description": "Comercializacion de maquinarias, materiales y metalmecanica: tubos, perfiles galvanizados, alambres, mallas electrosoldadas",
    },
    {
        "name": "Galindo Ingenieria",
        "categories": ["acero"],
        "operating_cities": ["LPZ"],
        "phone": "+591 72044342", "phone2": None,
        "email": "contacto@galindoingenieria.com", "website": "www.galindoingenieria.com",
        "description": "Diseno y calculo estructural, ingenieria sismica, patologia estructural, supervision y consultoria",
    },
    {
        "name": "Gestual Arquitectura",
        "categories": [],
        "operating_cities": [],
        "phone": "+591 62322006", "phone2": None,
        "email": None, "website": None,
        "description": "Estudio de arquitectura, diseno arquitectonico y de interiores",
    },
    {
        "name": "Grupo R&N",
        "categories": ["impermeabilizantes"],
        "operating_cities": ["LPZ", "SCZ"],
        "phone": "+591 2 2773627", "phone2": "+591 76534943",
        "email": "contacto@gruporyn.net", "website": "www.gruporyn.net",
        "description": "Geomallas, geomantos, geotextil, geomembrana, geoceldas; impermeabilizacion, drenaje vertical, demolicion de rocas",
    },
    {
        "name": "Hansa",
        "categories": ["acero", "maquinaria"],
        "operating_cities": ["LPZ", "CBBA", "SCZ"],
        "phone": "+591 2 2149800", "phone2": "+591 72037846",
        "email": None, "website": None,
        "description": "Naves industriales, obra gruesa/fina, equipamientos, sistemas contraincendios, electricos; domotica avanzada",
    },
    {
        "name": "Hidronyx",
        "categories": ["sanitario", "plomeria"],
        "operating_cities": ["LPZ"],
        "phone": "+591 70120080", "phone2": "+591 64125477",
        "email": "hidronyx@gmail.com", "website": None,
        "description": "Tanques plasticos bicapa/tricapa 300-10,000L, cisternas, camaras septicas, bebederos",
    },
    {
        "name": "ICI Ltda.",
        "categories": ["sanitario"],
        "operating_cities": ["LPZ"],
        "phone": "+591 78934730", "phone2": "+591 2 2440944",
        "email": "ici_ltda.lp@hotmail.com", "website": "www.iciltda.com",
        "description": "Equipos para instalacion de gas natural: medidores domesticos/comerciales/industriales, reguladores, valvulas",
    },
    {
        "name": "IMCAR (Dist. Sika)",
        "categories": ["impermeabilizantes", "sanitario"],
        "operating_cities": ["LPZ"],
        "phone": "+591 77242420", "phone2": "+591 71526027",
        "email": "imcar@mail.com", "website": None,
        "description": "Distribuidores oficiales Sika; lavamanos, inodoros, griferia, porcelanatos, pisos flotantes SPC-PVC",
    },
    {
        "name": "Importadora Alarcon",
        "categories": ["plomeria", "sanitario"],
        "operating_cities": ["SCZ", "CBBA"],
        "phone": "+591 3 3557100", "phone2": "+591 70953567",
        "email": "ventas@importadora-alarcon.com.bo", "website": "www.importadora-alarcon.com.bo",
        "description": "Canerias para agua fria/caliente, tubos polipropileno desague, membranas aislantes, tuberias gas domiciliario",
    },
    {
        "name": "Importadora Duran",
        "categories": ["ceramica", "techos"],
        "operating_cities": ["EL ALTO", "LPZ"],
        "phone": "+591 2 2829541", "phone2": "+591 67349325",
        "email": None, "website": "www.importadoraduran.com",
        "description": "Cubiertas policarbonato, pisos flotantes HDF/SPC, zocalos, cielos falsos PVC, aluminio compuesto, luminarias LED",
    },
    {
        "name": "Importadora Z. Santos",
        "categories": ["acero", "prefabricados"],
        "operating_cities": ["EL ALTO"],
        "phone": "+591 2 2850866", "phone2": "+591 71231350",
        "email": "importsantos@yahoo.es", "website": None,
        "description": "Vainas corrugadas, cordon pretensado grado 270K, anclajes Freyssinet/OVM, servicio de tesado e inyectado",
    },
    {
        "name": "INGCO Bolivia",
        "categories": ["herramientas"],
        "operating_cities": ["EL ALTO", "SCZ"],
        "phone": "+591 71241833", "phone2": "+591 71570898",
        "email": None, "website": "www.ingcobolivia.com",
        "description": "Herramientas manuales, electricas, neumaticas, de banco; generadores y bombas de agua",
    },
    {
        "name": "Inno Domotics",
        "categories": ["electrico"],
        "operating_cities": ["SCZ", "CBBA"],
        "phone": "+591 3 3393974", "phone2": None,
        "email": "sc@innodomotics.com", "website": "www.innodomotics.com",
        "description": "Automatizacion domotica: home theater, asesoramiento, proyectos, soporte tecnico, instalaciones especiales",
    },
    {
        "name": "Innoplack",
        "categories": ["acero", "techos"],
        "operating_cities": ["SCZ"],
        "phone": "+591 71349585", "phone2": "+591 62000359",
        "email": "ventas@innoplack.com", "website": "www.innoplack.com",
        "description": "Perfiles acero galvanizado para cerchas/cielo falso, placas de yeso Drywall (estandar, humedad, fuego), teja fibrocemento",
    },
    {
        "name": "Inkaforte (Brizio)",
        "categories": ["cemento", "ceramica"],
        "operating_cities": ["LPZ"],
        "phone": "+591 735952554", "phone2": None,
        "email": "inkaforte@inka-forte.com", "website": "www.inka-forte.com",
        "description": "Cemento cola para ceramica y porcelanato; alta adherencia en pisos y paredes",
    },
    {
        "name": "Intermec S.R.L.",
        "categories": ["acero", "vidrios"],
        "operating_cities": ["CBBA", "LPZ"],
        "phone": "+591 4 4449686", "phone2": "+591 60700143",
        "email": "intermec.bo@gmail.com", "website": "www.intermecsrl.com",
        "description": "Estructuras metalicas, tinglados, coliseos, cielos falsos GALVATEX/YESOTEX, vidrio templado, aluminio compuesto",
    },
    {
        "name": "Isocret",
        "categories": ["prefabricados"],
        "operating_cities": ["EL ALTO"],
        "phone": "+591 61005252", "phone2": None,
        "email": "ventas@isocret.com.bo", "website": "www.isocret.com.bo",
        "description": "Viguetas pretensadas, styropor expandido, hormigon industrial, postes curvos, calculo de estructuras",
    },
    {
        "name": "Isolcruz",
        "categories": ["aislantes"],
        "operating_cities": ["SCZ"],
        "phone": "+591 3 3888774", "phone2": "+591 71343157",
        "email": "info@isolcruz.com", "website": "www.isolcruz.com",
        "description": "EPS isoteja/isopanel, poliuretano frigopanel, termo/phono spray, poliisocianurato, muros termoacusticos",
    },
    {
        "name": "Las Lomas",
        "categories": ["acero"],
        "operating_cities": ["LPZ", "CBBA", "SCZ"],
        "phone": "+591 2 2821021", "phone2": "+591 4 4227729",
        "email": None, "website": "www.laslomas.com.bo",
        "description": "Importacion de fierro de construccion DEDINI corrugado y liso, planchas, angulares, pletinas",
    },
    {
        "name": "Mamut",
        "categories": ["ceramica"],
        "operating_cities": ["CBBA", "SCZ", "LPZ"],
        "phone": "+591 70341775", "phone2": "+591 4 4486243",
        "email": "manuel.laredo@pisosmamut.com", "website": None,
        "description": "Baldosa amortiguante EPDM, pavimento continuo, piso podotactil, industrial y deportivo de poliuretano",
    },
    {
        "name": "Maqualq S.R.L.",
        "categories": ["maquinaria"],
        "operating_cities": ["LPZ"],
        "phone": "+591 2 2912823", "phone2": "+591 77706766",
        "email": "quiroga.maqalq@hotmail.com", "website": None,
        "description": "Construccion de edificios y obras civiles; alquiler de andamios, puntales, compactadora, mezcladora, vibradora",
    },
    {
        "name": "Maquiobras",
        "categories": ["pintura", "impermeabilizantes"],
        "operating_cities": ["SCZ"],
        "phone": "+591 70314533", "phone2": "+591 69045456",
        "email": None, "website": "sites.google.com/view/maquiobras",
        "description": "Construccion/mantenimiento civil, pintura e impermeabilizacion, diseno y remodelacion, negocios inmobiliarios",
    },
    {
        "name": "Marcav",
        "categories": ["impermeabilizantes", "plomeria"],
        "operating_cities": ["CHQ", "PSI", "SCZ"],
        "phone": "+591 77110060", "phone2": "+591 72881248",
        "email": "empresamarcav@gmail.com", "website": None,
        "description": "Provision e instalacion de geomembrana y geotextil; termofusion de tuberias HDPE; impermeabilizacion de suelos",
    },
    {
        "name": "Monopol",
        "categories": ["pintura"],
        "operating_cities": ["LPZ", "SCZ", "CBBA"],
        "phone": "+591 2 2180222", "phone2": None,
        "email": None, "website": "pinturasmonopol.com",
        "description": "Pinturas latex arquitectonicas, anticorrosivas, de marcacion vial; barnices, pegamentos, impermeabilizantes",
    },
    {
        "name": "Monterrey",
        "categories": ["acero", "ferreteria"],
        "operating_cities": ["SCZ", "EL ALTO"],
        "phone": "+591 3 3471960", "phone2": "+591 2 2860363",
        "email": None, "website": "www.monterrey.com.bo",
        "description": "Acero de construccion, clavos, calaminas, mallas, perfiles, planchas, tubos, equipos de soldar",
    },
    {
        "name": "Nueva Esperanza S.R.L.",
        "categories": ["agregados"],
        "operating_cities": ["LPZ", "EL ALTO"],
        "phone": "+591 70135605", "phone2": "+591 70118600",
        "email": "info@ecnuevaesperanza.com", "website": None,
        "description": "Arena, grava, entregas en obra",
    },
    {
        "name": "Picmetrica S.R.L.",
        "categories": [],
        "operating_cities": ["LPZ"],
        "phone": "+591 63091512", "phone2": None,
        "email": "gerenciageneral@picmetrica.com", "website": "constructorapicmetrica-srl.com",
        "description": "Obra fina y gruesa, llave en mano, diseno de interiores, proyectos comerciales/residenciales, supervision",
    },
    {
        "name": "Piedra Liquida Bolivia",
        "categories": ["ceramica"],
        "operating_cities": ["LPZ", "SCZ"],
        "phone": "+591 63091512", "phone2": "+591 75262959",
        "email": "piedraliquidabolivia@gmail.com", "website": None,
        "description": "Revestimientos para fachadas, pisos, gradas, paredes; diseno de interiores y exteriores; encimeras",
    },
    {
        "name": "Plasticos Carmen",
        "categories": ["sanitario", "plomeria"],
        "operating_cities": ["SCZ"],
        "phone": "+591 3 3332762", "phone2": "+591 72042942",
        "email": None, "website": "www.plasticoscarmen.com",
        "description": "Tanques bicapa y tricapa, cisternas, camaras septicas, bebederos, tuberia PEAD/HDPE. Linea: 800-10-9005",
    },
    {
        "name": "Plastiforte",
        "categories": ["plomeria", "impermeabilizantes"],
        "operating_cities": ["CBBA", "SCZ", "LPZ", "CHQ", "ORU", "PSI", "TJA"],
        "phone": "+591 4 4433270", "phone2": None,
        "email": "ventas@plastiforte.com", "website": "www.plastiforte.com",
        "description": "SUPERTUBO HDPE 20-1200mm, accesorios SUPERJUNTA, tuberia corrugada, geomembrana, tanques, silos",
    },
    {
        "name": "Plussteel",
        "categories": ["acero", "techos"],
        "operating_cities": ["SCZ", "CBBA", "LPZ", "EL ALTO"],
        "phone": "+591 3 3347777", "phone2": "+591 78519872",
        "email": None, "website": None,
        "description": "Perfileria acero galvanizado, Drywall, Steelframe, cerchas metalicas, placas yeso/cementica, aluminio compuesto Hunter Douglas",
    },
    {
        "name": "Postcrete",
        "categories": ["prefabricados", "acero"],
        "operating_cities": ["LPZ", "CBBA", "SCZ"],
        "phone": "+591 72558308", "phone2": "+591 7704893",
        "email": "aramos@postcrete.com", "website": "www.postcrete.com",
        "description": "Losas y fundaciones postensadas, viguetas pretensadas",
    },
    {
        "name": "Pretbol Constructora",
        "categories": ["prefabricados"],
        "operating_cities": ["SCZ"],
        "phone": "+591 73685996", "phone2": None,
        "email": "pretbolsrl@gmail.com", "website": None,
        "description": "Prefabricados de hormigon, losetas hexagonales, pavimento rigido, cordones de acera, postes curvos, malla olimpica",
    },
    {
        "name": "Pretensa",
        "categories": ["prefabricados"],
        "operating_cities": ["LPZ", "EL ALTO"],
        "phone": "+591 2 2745474", "phone2": "+591 77612273",
        "email": "pretensa.mkt@gmail.com", "website": "pretensaltda.com",
        "description": "Viguetas pretensadas, losas huecas, muro de contencion, Plastoformo EPS, Tabiplast antisismico",
    },
    {
        "name": "PT Orias S.R.L.",
        "categories": ["prefabricados", "acero"],
        "operating_cities": ["SCZ"],
        "phone": "+591 71099805", "phone2": None,
        "email": "ico_2005@yahoo.com", "website": None,
        "description": "Sistemas estructurales postensados, losas postensadas, estructuras especiales",
    },
    {
        "name": "Quark Costos y Presupuestos",
        "categories": [],
        "operating_cities": ["LPZ"],
        "phone": "+591 2 2421368", "phone2": "+591 71592932",
        "email": "webmaster@quark-costos.com", "website": "www.quark-costos.com",
        "description": "Software especializado para ingenieria, arquitectura y construccion - sistema QUARK",
    },
    {
        "name": "Quasar Solutions",
        "categories": ["electrico"],
        "operating_cities": ["LPZ"],
        "phone": "+591 2 310832", "phone2": "+591 73718195",
        "email": "ventas@quasar.com.bo", "website": "www.quasar.com.bo",
        "description": "Materiales puesta a tierra: Cemento Conductivo ILLAPA, Bentonita Ultra Gel, EcoGel, Terranova (hecho en Bolivia)",
    },
    {
        "name": "Ready Mix Bolivia / SOBOCE",
        "categories": ["cemento"],
        "operating_cities": ["SCZ", "LPZ", "CBBA", "ORU", "TJA"],
        "phone": "+591 3 3449939", "phone2": "+591 2 2406040",
        "email": None, "website": "www.soboce.com",
        "description": "Hormigon premezclado H15-H45; cemento Eco Fuerte Plus, IP-30, IP-40, puzolanico. Linea: 800-103-606",
    },
    {
        "name": "REMOC Cimentaciones",
        "categories": ["prefabricados"],
        "operating_cities": ["CBBA"],
        "phone": "+591 72152000", "phone2": "+591 73710666",
        "email": None, "website": None,
        "description": "Perforacion de pilotes in-situ y CFA, hormigon premezclado, construccion civil, montaje estructuras metalicas",
    },
    {
        "name": "Roca Fuerte Aridos",
        "categories": ["agregados"],
        "operating_cities": ["EL ALTO", "LPZ"],
        "phone": "+591 71561962", "phone2": "+591 71563286",
        "email": "aridosrocafuerte7@gmail.com", "website": None,
        "description": "Arenas y gravas para hormigon, aridos para pavimento, piedras, cascote, servicio de transporte a obra",
    },
    {
        "name": "SACOCI S.R.L.",
        "categories": ["maquinaria"],
        "operating_cities": ["EL ALTO"],
        "phone": "+591 77777726", "phone2": "+591 77295388",
        "email": "sacoci_bol@yahoo.es", "website": "www.sacocisrl.com",
        "description": "Demolicion y voladura, alquiler maquinaria pesada, mantenimiento, arquitectura y metalmecanica",
    },
    {
        "name": "San Rafael",
        "categories": ["sanitario", "maquinaria"],
        "operating_cities": ["CBBA", "SCZ", "ORU"],
        "phone": "+591 76920124", "phone2": "+591 77444329",
        "email": None, "website": "www.sanrafael.com.bo",
        "description": "Bombas de agua, perforacion de pozos, asistencia tecnica y mantenimiento",
    },
    {
        "name": "Sanear",
        "categories": ["sanitario"],
        "operating_cities": ["SCZ", "EL ALTO", "CBBA", "PSI", "ORU", "CHQ"],
        "phone": "+591 710 19333", "phone2": None,
        "email": "ventas.nal@stpsanear.com", "website": None,
        "description": "Tanques polietileno tricapa/bicapa, fosas septicas, camaras de inspeccion, banos quimicos, sanitarios portatiles",
    },
    {
        "name": "Sobopret / SOBOCE",
        "categories": ["prefabricados"],
        "operating_cities": ["SCZ", "LPZ", "CBBA", "ORU", "TJA"],
        "phone": "+591 3 3449939", "phone2": "+591 2 2406040",
        "email": None, "website": "www.soboce.com",
        "description": "Viguetas pretensadas Sobopret, complementos Styropor expandido",
    },
    {
        "name": "Sokolmet",
        "categories": ["maquinaria"],
        "operating_cities": ["LPZ"],
        "phone": "+591 79523922", "phone2": "+591 70551647",
        "email": "informacion@sokolmet.com", "website": "www.sokolmet.com",
        "description": "Alquiler maquinaria de construccion, andamios modulares, puntales metalicos, compactadoras, mezcladoras",
    },
    {
        "name": "Synergy",
        "categories": ["acero", "techos"],
        "operating_cities": ["SCZ", "CBBA", "LPZ", "TJA"],
        "phone": "+591 3 3420345", "phone2": None,
        "email": None, "website": None,
        "description": "Perfileria acero galvanizado, placas yeso, cielo falso PVC, impermeabilizantes, pisos vinilicos, puertas/ventanas PVC",
    },
    {
        "name": "TechoBol S.R.L.",
        "categories": ["techos"],
        "operating_cities": ["CBBA"],
        "phone": "+591 4 4330651", "phone2": "+591 69530554",
        "email": None, "website": None,
        "description": "Calaminas prepintadas/onduladas/trapezoidales/tipo teja/zincalum; policarbonatos; ganchos/clavos/autoperforantes",
    },
    {
        "name": "Tecnohidro",
        "categories": ["sanitario", "maquinaria"],
        "operating_cities": ["LPZ"],
        "phone": "+591 2 2126862", "phone2": "+591 71573634",
        "email": "tecnohidro-ventas@hotmail.com", "website": None,
        "description": "Bombas de agua industriales/sumergibles, generadores, perforacion y limpieza de pozos 4-12 pulgadas",
    },
    {
        "name": "Tecnoplan S.R.L.",
        "categories": ["impermeabilizantes"],
        "operating_cities": ["LPZ"],
        "phone": "+591 2 2434930", "phone2": "+591 70181122",
        "email": "tecnoplan_srl@hotmail.com", "website": None,
        "description": "Membrana asfaltica para impermeabilizacion de losas, terrazas, piscinas; constructora con +35 anos",
    },
    {
        "name": "Tecnopreco",
        "categories": ["prefabricados"],
        "operating_cities": ["LPZ", "SCZ"],
        "phone": "+591 70513827", "phone2": None,
        "email": None, "website": "www.tecnopreco.com",
        "description": "Viguetas pretensadas BUNKER/TATAKE/TITAN, Plastoformo EPS, graderias, bloques, cordones, baldosas, postes, muro perimetral",
    },
    {
        "name": "Tektron",
        "categories": ["acero", "aislantes"],
        "operating_cities": ["LPZ", "EL ALTO", "CBBA", "SCZ"],
        "phone": "+591 76767808", "phone2": None,
        "email": "contacto@tektron.com.bo", "website": "www.tektron.com.bo",
        "description": "Placas yeso, Drywall, perfileria liviana, placas cementicias, Steel Frame, lana de fibra de vidrio, SPC/HDF, aluminio compuesto",
    },
    {
        "name": "Terra Foundations",
        "categories": ["prefabricados"],
        "operating_cities": ["LPZ", "SCZ"],
        "phone": "+591 2 2776248", "phone2": "+591 3 3120996",
        "email": "info@terrafoundations.com.bo", "website": "www.terrafoundations.com",
        "description": "Pilotes, micropilotes, anclajes, Soil Nailing, inyecciones, muros pantalla y berlineses, mejoramiento de suelos",
    },
    {
        "name": "Termocruz",
        "categories": ["aislantes"],
        "operating_cities": ["SCZ"],
        "phone": "+591 70860219", "phone2": "+591 79054874",
        "email": "cevbozo@outlook.com", "website": None,
        "description": "Aislacion termica industrial linea frio/caliente; camaras frigorificas industriales; aislamiento de canerias",
    },
    {
        "name": "Termovid PVC",
        "categories": ["vidrios"],
        "operating_cities": ["CBBA"],
        "phone": "+591 75921686", "phone2": "+591 77449572",
        "email": "termovidpvc@gmail.com", "website": None,
        "description": "Termopanel TERMOVID, persianas, carpinteria de aluminio estandar y con ruptura de puente termico, vidrio templado/laminado",
    },
    {
        "name": "Tigre",
        "categories": ["plomeria", "electrico"],
        "operating_cities": ["SCZ", "LPZ", "EL ALTO"],
        "phone": "+591 3 3147210", "phone2": "+591 2 2147220",
        "email": None, "website": None,
        "description": "Tuberias y accesorios PVC agua caliente/fria, HDPE, cables conductores cobre/aluminio, tuberia desague",
    },
    {
        "name": "TrabajAhora",
        "categories": ["herramientas"],
        "operating_cities": ["NACIONAL"],
        "phone": "+591 75221344", "phone2": None,
        "email": "contact-info@andystfort.com", "website": "www.trabajahora.andystfort.com",
        "description": "App para buscar empleo o contratar: filtros por ciudad/categoria, publicacion de vacantes, evaluacion previa",
    },
    {
        "name": "Turf Brasil / Mundo Pisos",
        "categories": ["ceramica"],
        "operating_cities": ["LPZ", "EL ALTO", "SCZ"],
        "phone": "+591 77761063", "phone2": "+591 76732376",
        "email": None, "website": "www.mundo-pisos.com",
        "description": "Cesped sintetico, muros verdes, cielo falso PVC, panel ripado, pisos vinilicos SPC, revestimientos de pared",
    },
    {
        "name": "Valkure Bolivia",
        "categories": ["cemento"],
        "operating_cities": ["LPZ"],
        "phone": "+591 61000354", "phone2": None,
        "email": "comercial@valkurebolivia.com", "website": None,
        "description": "Pega ladrillo de alta adherencia con dosificacion controlada",
    },
    {
        "name": "Vitral CBBA",
        "categories": ["vidrios"],
        "operating_cities": ["CBBA"],
        "phone": "+591 63964389", "phone2": "+591 79336680",
        "email": None, "website": None,
        "description": "Vitrales y murales modulares, estructuras luminicas, murales modernos",
    },
    {
        "name": "Plasticos Carmen (Campeon)",
        "categories": ["sanitario", "plomeria"],
        "operating_cities": ["SCZ"],
        "phone": "+591 3 3332762", "phone2": "+591 72042942",
        "email": None, "website": "www.plasticoscarmen.com",
        "description": "Tanque bicapa Campeon 300-20000L, tubos HDPE para agua potable, riego, drenaje y cableado electrico",
    },
]

# ── Rubros por proveedor (primeros 3) ────────────────────────
RUBROS = [
    {"supplier_name": "Acermax", "rubro": "Calaminas", "category_key": "techos",
     "description": "Calamina plana, ondulada, rectangular, trapezoidal y trapezoidal alto; teja americana, colonial y espanola; cumbreras"},
    {"supplier_name": "Acermax", "rubro": "Metalmecanica", "category_key": "acero",
     "description": "Corte, plegado y cilindrado de planchas de acero"},
    {"supplier_name": "Aceros Arequipa", "rubro": "Acero de construccion", "category_key": "acero",
     "description": "Acero corrugado, estribos, clavos, alambres, conectores mecanicos"},
    {"supplier_name": "Aceros Arequipa", "rubro": "Mallas / Perfiles", "category_key": "acero",
     "description": "Mallas electrosoldadas, perfiles de acero, planchas y tubos"},
    {"supplier_name": "Aceros Torrico", "rubro": "Calaminas", "category_key": "techos",
     "description": "Calaminas zinc-alum, pre-pintadas, corrugadas; teja americana/colonial"},
]


def main():
    print(f"Cargando {len(SUPPLIERS)} proveedores a {APP_URL}...")

    created = 0
    skipped = 0
    supplier_id_map = {}  # name → server_id

    for s in SUPPLIERS:
        first_city = s["operating_cities"][0] if s.get("operating_cities") else None
        payload = {
            "name": s["name"],
            "categories": s.get("categories", []),
            "city": first_city,
            "department": CITY_TO_DEPT.get(first_city, first_city) if first_city else None,
            "phone": s.get("phone"),
            "phone2": s.get("phone2"),
            "email": s.get("email"),
            "website": s.get("website"),
            "description": s.get("description"),
            "operating_cities": s.get("operating_cities"),
            "country": "BO",
        }

        resp = httpx.post(
            f"{APP_URL}/api/v1/integration/suppliers",
            json=payload, headers=HEADERS, timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                action = data.get("action", "created")
                sid = data["data"]["id"]
                supplier_id_map[s["name"]] = sid
                if action == "skipped":
                    skipped += 1
                    print(f"  = {s['name']} (ya existe, id={sid})")
                else:
                    created += 1
                    print(f"  + {s['name']} (id={sid})")
            else:
                print(f"  ! {s['name']}: {data.get('error', 'unknown')}")
        else:
            print(f"  ! {s['name']}: HTTP {resp.status_code}")

    print(f"\nProveedores: {created} creados, {skipped} existentes / {len(SUPPLIERS)} total")

    # Step 2: Create rubros
    rubros_created = 0
    for r in RUBROS:
        sid = supplier_id_map.get(r["supplier_name"])
        if not sid:
            print(f"  ! Rubro '{r['rubro']}': proveedor '{r['supplier_name']}' no encontrado")
            continue

        payload = {
            "supplier_id": sid,
            "rubro": r["rubro"],
            "description": r.get("description", ""),
            "category_key": r.get("category_key", ""),
        }
        resp = httpx.post(
            f"{APP_URL}/api/v1/integration/supplier-rubros",
            json=payload, headers=HEADERS, timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                rubros_created += 1
                print(f"  + {r['rubro']} -> {r['supplier_name']}")
        else:
            print(f"  ! {r['rubro']}: HTTP {resp.status_code}")

    print(f"\nRubros: {rubros_created} creados / {len(RUBROS)} total")
    print("Done.")


if __name__ == "__main__":
    main()
