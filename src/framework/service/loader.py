import os
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
            pass
    
    
    