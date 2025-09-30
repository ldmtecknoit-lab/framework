import os
import sys
import asyncio
import logging
from typing import Dict, Any, List, Optional
from kink import di # Dependancy Injection

# 1. Configurazione del Logging per la Massima Debuggabilità (Principio 1)
# Nomi chiari delle funzioni e messaggi di log descrittivi.
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - [%(name)s.%(funcName)s] - %(message)s'
)
logger = logging.getLogger("BOOTSTRAPPER")

# ----------------------------------------------------------------------
# FUNZIONI FOCALIZZATE SULLA SINGOLA RESPONSABILITÀ (Principio 2)
# ----------------------------------------------------------------------

def parse_browser_cookies(cookie_string: str) -> Dict[str, str]:
    """
    Funzione dichiarativa per il parsing dei cookie.
    Si concentra sul 'cosa' (ottenere key:value) e non sul 'come' (looping).
    
    Gestione Errore: Restituisce un dizionario vuoto in caso di input non valido.
    """
    if not cookie_string:
        return {}

    logger.debug("Parsing dei cookie in ambiente browser...")
    
    # Principio 3: List Comprehension per parsing dichiarativo
    cookies_dict = {}
    try:
        for cookie_pair in cookie_string.split(';'):
            # Garantisce che ci sia un '=', altrimenti salta l'elemento
            if '=' in cookie_pair:
                key, value = cookie_pair.split('=', 1)
                cookies_dict[key.strip()] = value
    except Exception as e:
        logger.error(f"Errore critico durante il parsing dei cookie: {e}")
        # Restituisce il dizionario parziale/vuoto per evitare il blocco
        return cookies_dict
        
    return cookies_dict

def tenta_recupero_sessione(session_value: str) -> Dict[str, Any]:
    """
    Tenta di eseguire la doppia 'eval' sulla stringa di sessione in modo sicuro.
    Gestisce eccezioni specifiche per tracciare il problema (Principio 1).
    """
    session_data: Dict[str, Any] = {}
    if not session_value or session_value == 'None':
        return session_data

    # Commento: La doppia eval è inusuale e potenzialmente non sicura. 
    # Mantenuta per aderenza al codice originale, ma raccomandata una revisione.
    for i in range(2):
        try:
            logger.debug(f"Tentativo di eval() su sessione (Passo {i+1}): {session_value}")
            # L'uso di `eval()` è intrinsecamente non sicuro. 
            # In un contesto reale, si preferirebbe `json.loads`.
            session_value = eval(session_value)
            
            # Se la prima eval non ha convertito in un tipo, si interrompe il loop.
            if not isinstance(session_value, str) and i == 0:
                 break
        except Exception as e:
            logger.warning(f"Errore durante l'eval() della sessione al passo {i+1}. Dettaglio: {e}")
            return {} # Fallimento del recupero della sessione
    
    if isinstance(session_value, dict):
        return session_value
        
    return {} # Non è un dizionario (o la doppia eval è fallita)

async def installa_dipendenze_browser() -> None:
    """Installa le dipendenze Python necessarie in ambiente Pyodide."""
    if sys.platform != "emscripten":
        return

    logger.info("Rilevato ambiente Pyodide. Avvio installazione dipendenze.")
    try:
        # Importiamo solo se necessario per evitare errori in ambienti non-browser
        import micropip 
        
        # 2. Ottimizzazione: Lista dichiarativa e compatta
        packages_to_install = [
            "kink", "tomli", "jinja2", "untangle", "bs4", "lxml", 
            # "webassets" (commentato come nell'originale)
        ]
        
        await micropip.install(packages_to_install)
        logger.info(f"Installazione di {len(packages_to_install)} pacchetti completata.")
        
    except ImportError:
        logger.critical("Dipendenze Pyodide (micropip) non disponibili, ma sys.platform è 'emscripten'.")
        # Rilancia un errore critico per debug immediato
        raise RuntimeError("Impossibile caricare micropip per l'installazione delle dipendenze.")

# ----------------------------------------------------------------------
# FUNZIONE PRINCIPALE DI BOOTSTRAP (Orchestratore)
# ----------------------------------------------------------------------

async def bootstrap_optimized() -> None:
    """
    Avvia il framework in modo ottimizzato, debuggabile e dichiarativo.
    """
    print("Bootstrapping the loader...###########################################################")
    
    env_config: Dict[str, Any] = dict(os.environ)
    session_data: Dict[str, Any] = {}
    identifier_val: str = 'None'
    
    await installa_dipendenze_browser() # Delega la responsabilità
    
    # 1. Gestione Condizionale della Configurazione Browser/Server
    if sys.platform == "emscripten":
        import js # Accesso al DOM
        
        # Delega il parsing dei cookie
        cookies: Dict[str, str] = parse_browser_cookies(str(js.document.cookie))
        
        session_str = cookies.get('session', 'None')
        identifier_val = cookies.get('session_identifier', 'None')
        
        # Delega il recupero della sessione, con gestione degli errori incorporata
        session_data = tenta_recupero_sessione(session_str)
        
        # 2. Ottimizzazione: Uso dell'operatore merge standard (Python 3.9+)
        # Unione esplicita di env, sessione e identifier
        config_params = {**env_config, "session": session_data, "identifier": identifier_val}
        config = language.get_confi(**config_params)
        
    else:
        # 2. Ottimizzazione: Uso dell'operatore merge standard (Python 3.9+) o `update()`
        # Qui si usa la sintassi originale (Python 3.9+) per coerenza, se supportata
        config = language.get_confi(**env_config | {"session": session_data})
        
    logger.info("Configurazione del sistema caricata con successo.")
    
    # ----------------------------------------------------------------------
    # FASE DI CARICAMENTO MANAGER (Dichiarativa & Parallela)
    # ----------------------------------------------------------------------
    
    # Caricamento sequenziale dei manager essenziali
    # NOTA: Assumiamo che `language` e `executor` non richiedano `di`
    await language.load_manager(language, provider="message", name="messenger", path="framework/manager/messenger.py")
    await language.load_manager(language, provider="actuator", name="executor", path="framework/manager/executor.py")

    # 1. Recupero immediato del dependency injector (nome più descrittivo per la variabile)
    dependency_executor = di.get("executor")
    if not dependency_executor:
        logger.critical("Dipendenza 'executor' non iniettata! Impossibile proseguire.")
        raise LookupError("Il manager 'executor' non è stato trovato nel DI.")

    # 3. Dichiarazione esplicita delle task asincrone
    manager_tasks: List[asyncio.Task] = [
        asyncio.create_task(language.load_manager(language, provider="presentation", name="presenter", path="framework/manager/presenter.py"), name="load_presenter"),
        asyncio.create_task(language.load_manager(language, provider="authentication", name="defender", path="framework/manager/defender.py"), name="load_defender"),
        asyncio.create_task(language.load_manager(language, provider="persistence", name="storekeeper", path="framework/manager/storekeeper.py"), name="load_storekeeper"),
        asyncio.create_task(language.load_manager(language, provider="authentication", name="tester", path="framework/manager/tester.py"), name="load_tester"),
    ]
    
    logger.info(f"Avvio del caricamento parallelo di {len(manager_tasks)} manager.")
    
    # Attende il caricamento di tutti i manager (deleghiamo l'attesa all'executor)
    # L'uso di all_completed dovrebbe includere una gestione degli errori/timeout
    await dependency_executor.all_completed(tasks=manager_tasks) 

    # ----------------------------------------------------------------------
    # FASE DI CARICAMENTO PROVIDER (Dichiarativa & Parallela)
    # ----------------------------------------------------------------------

    provider_tasks: List[asyncio.Task] = []
    
    # Lista dichiarativa dei moduli principali
    MODULI_PRINCIPALI = ["presentation", "persistence", "message", "authentication", "actuator"]
    
    # 3. Ciclo dichiarativo per la creazione delle task
    for module_name in MODULI_PRINCIPALI:
        if module_name in config and isinstance(config[module_name], dict):
            # Ciclo sulle configurazioni di ciascun driver all'interno del modulo
            for driver_name, setting_data in config[module_name].items():
                
                # 1. Controllo di coerenza e gestione errori
                adapter_name = setting_data.get("adapter")
                if not adapter_name:
                    logger.error(f"Configurazione incompleta per modulo '{module_name}', driver '{driver_name}': Manca 'adapter'.")
                    continue
                
                # Composizione dichiarativa del payload
                payload_data = {
                    **setting_data, 
                    "profile": driver_name, 
                    "project": config.get("project", "default_project")
                }
                
                # Creazione della task con nome per la debuggabilità
                task = asyncio.create_task(
                    language.load_provider(
                        language,
                        path=f"infrastructure/{module_name}/{adapter_name}.py",
                        area="infrastructure", 
                        service=module_name, 
                        adapter=adapter_name, 
                        payload=payload_data
                    ),
                    name=f"load_provider_{module_name}_{driver_name}"
                )
                provider_tasks.append(task)
        else:
            logger.debug(f"Modulo '{module_name}' non trovato o non è un dizionario nella configurazione. Skippato.")

    logger.info(f"Avvio del caricamento parallelo di {len(provider_tasks)} provider.")
    await dependency_executor.all_completed(tasks=provider_tasks)
    
    # ----------------------------------------------------------------------
    # FASE DI CARICAMENTO ELEMENTI PRESENTAZIONE (Dichiarativa & Robusta)
    # ----------------------------------------------------------------------
    
    # 1. Recupero dipendenze con gestione esplicita dell'errore (Principio 1)
    try:
        presentation_elements: List[Any] = di["presentation"]
        event_loop = asyncio.get_event_loop()
    except KeyError as e:
        logger.critical(f"Dipendenza '{e}' non iniettata! Impossibile caricare gli elementi di presentazione.")
        return # Interrompe l'esecuzione in modo pulito
    
    logger.info(f"Avvio del caricamento di {len(presentation_elements)} elementi di presentazione.")
    
    # 3. Ciclo dichiarativo e robusto
    for item in presentation_elements:
        # 1. Logging di debug per il tracciamento
        item_name = getattr(item, '__class__', item)
        logger.debug(f"Controllo elemento presentazione: {item_name}")

        if hasattr(item, "loader"):
            try:
                # 1. Chiamata con contesto di gestione errori
                item.loader(loop=event_loop)
                logger.debug(f"Loader eseguito con successo per {item_name}.")
            except Exception as e:
                logger.error(f"ERRORE GRAVE: Il metodo 'loader' dell'elemento {item_name} ha fallito. Dettaglio: {e}")
        else:
            # 1. Messaggio informativo per la debuggabilità
            logger.debug(f"L'elemento {item_name} non ha un metodo 'loader'. Saltato.")

'''import os
import sys
import asyncio
from kink import di
# Import language module
import framework.service.language as language 

async def bootstrap() -> None:
    print("Bootstrapping the loader...###########################################################")
    env = dict(os.environ)
    session = dict()
    # Controlla se siamo in Pyodide (browser)
    if sys.platform == "emscripten":
        import js
        import micropip

        # Recupera i cookie dal documento
        cookies = {
                  key.strip(): value
                  for cookie in js.document.cookie.split(';') if '=' in cookie
                  for key, value in [cookie.split('=', 1)]
        }

        session = cookies.get('session', 'None')
        identifier = cookies.get('session_identifier', 'None')
        try:
            session = eval(session)
            session = eval(session)
            print(session, "session",type(session))
        except:
            pass

        packages = [
            "kink",
            "tomli",
            "jinja2",
            "untangle",
            "bs4",
            "lxml",
            #"webassets",
        ]
        
        await micropip.install(packages)

        # Unisce env e cookies
        config = language.get_confi(**{**env, **{"session":session,"identifier":identifier}})
    else:
        config = language.get_confi(**{**env, "session":session})

    print(config, "config")

    
    await language.load_manager(language,provider="message", name="messenger", path="framework/manager/messenger.py")
    await language.load_manager(language,provider="actuator", name="executor", path="framework/manager/executor.py")

    executor = di["executor"]

    # Carica i gestori principali
    tasks = [
        asyncio.create_task(language.load_manager(language,provider="presentation", name="presenter", path="framework/manager/presenter.py")),
        asyncio.create_task(language.load_manager(language,provider="authentication", name="defender", path="framework/manager/defender.py")),
        asyncio.create_task(language.load_manager(language,provider="persistence", name="storekeeper", path="framework/manager/storekeeper.py")),
        asyncio.create_task(language.load_manager(language,provider="authentication", name="tester", path="framework/manager/tester.py")),
    ]
    
    

    # Attende il caricamento di tutti i manager in parallelo
    await executor.all_completed(tasks=tasks)


    
    # Carica i provider dai moduli di configurazione
    tasks = []
    for module in ["presentation", "persistence", "message", "authentication","actuator"]:
        if module in config:
            for driver, setting in config[module].items():
                adapter = setting["adapter"]
                payload = {**setting, "profile": driver, "project": config["project"]}
                
                tasks.append(asyncio.create_task(
                    language.load_provider(language,path=f"infrastructure/{module}/{adapter}.py",area="infrastructure", service=module, adapter=adapter, payload=payload)
                ))
    
    # Attende il caricamento dei provider in parallelo
    await executor.all_completed(tasks=tasks)

    messenger = di["messenger"]
    presentation = di["presentation"]
    
    
    event_loop = asyncio.get_event_loop()
    #await messenger.post(domain='debug',message="Caricamento degli elementi della presentazione.")
    for item in presentation:
        #await messenger.post(domain='debug',message=f"Caricamento dell'elemento: {item}")
        if hasattr(item, "loader"):
            item.loader(loop=event_loop)
        else:
            #await messenger.post(domain='debug',message=f"L'elemento {item} non ha un metodo 'loader'.")
            pass'''