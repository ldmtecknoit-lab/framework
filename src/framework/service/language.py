from kink import di
import importlib
import tomli
import sys
import os
from jinja2 import Environment
import asyncio
import ast
import re
import fnmatch
from datetime import datetime, timezone
import uuid
import json
import copy
from urllib.parse import parse_qs,urlencode,urlparse
import traceback
import types # Importato per la gestione dinamica dei moduli

from cerberus import Validator, TypeDefinition, errors
import inspect
from typing import Dict, Callable, Any

# --- 1. Eccezione per la Tracciabilità degli Errori ---

class ResourceLoadError(Exception):
    """
    Eccezione personalizzata per gli errori di caricamento delle risorse.
    Include l'adapter e il path per la tracciabilità della catena di errore.
    """
    def __init__(self, message: str, adapter_name: str, path: str):
        super().__init__(message)
        self.adapter = adapter_name
        self.path = path
        self.message = message
        # Migliora il messaggio visualizzato nello stack trace
        self.args = (f"❌ Caricamento fallito per '{adapter_name}' ({path}): {message}",)


# --- 2. Funzioni Helper per la Logica Specifica e il Caricamento ---

async def _load_test_contract_and_export(lang: Any, test_path: str, adapter: str) -> tuple[Dict[str, Any], Callable[..., Any]]:
    """
    Carica il contratto (*.test.py) per estrarre 'CONTRACT_DEFINITIONS' e la funzione 'EXPORT_FUNCTION'.
    Utilizza lang.backend per l'I/O.
    """
    test_adapter = f"{adapter}_contract"
    test_constants = {'path': test_path, 'adapter': test_adapter}

    try:
        # Usa lang.backend per l'I/O
        test_code = await lang.backend(**test_constants) 

        contract_module = types.ModuleType(test_adapter)
        contract_module.__file__ = test_path
        contract_module.language = lang 
        exec(test_code, contract_module.__dict__)
        
        contract_data = None
        export_func = None
        
        # Cerca la classe di test per le definizioni del contratto
        for name, obj in inspect.getmembers(contract_module):
            if inspect.isclass(obj) and hasattr(obj, 'CONTRACT_DEFINITIONS'):
                contract_data = obj.CONTRACT_DEFINITIONS
                
        # Cerca la funzione di esportazione a livello di modulo
        export_func = getattr(contract_module, 'EXPORT_FUNCTION', None)
        
        if contract_data is None: 
            raise ValueError("Contratto non definito: 'CONTRACT_DEFINITIONS' non trovato nella classe di test.")
        if not callable(export_func): 
            raise ValueError("Funzione di esportazione mancante: 'EXPORT_FUNCTION' non è stata definita o non è richiamabile.")
        
        return contract_data, export_func
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Contratto mancante: '{test_path}' non trovato nel backend.")
    except Exception as e:
        raise ResourceLoadError(
            f"Errore di sintassi o estrazione nel contratto '{test_path}'.",
            adapter_name=test_adapter,
            path=test_path
        ) from e


async def _load_python_module(lang, path, adapter, module_code):
    """Gestisce la convalida, il caricamento ricorsivo, l'esecuzione e il filtro del codice Python."""
    
    test_path = path.replace('.py', '.test.py')

    # 1. Carica il Contratto e la Funzione di Esportazione
    contract_data, export_func = await _load_test_contract_and_export(lang, test_path, adapter)
    
    # 2. Estrazione delle Dipendenze
    # Usa lang.extract_modules_from_code
    modules_to_install = await lang.extract_modules_from_code(module_code)
    
    # 3. Creazione del Modulo
    temp_module = types.ModuleType(adapter + "_TEMP")
    temp_module.__file__ = path 
    temp_module.language = lang 
    temp_module.contract = contract_data # Inietta l'oggetto contratto
    
    # 4. Caricamento Ricorsivo delle Risorse Dipendenti
    for resource_name, resource_path in modules_to_install.items():
        try:
            # Usa lang.resource per la chiamata ricorsiva
            loaded_resource = await lang.resource(lang, path=resource_path, adapter=resource_name)
            setattr(temp_module, resource_name, loaded_resource)
        except Exception as e:
            raise ResourceLoadError(
                f"Errore nel caricamento della risorsa dipendente '{resource_path}'.",
                adapter_name=resource_name,
                path=resource_path
            ) from e

    # 5. Esecuzione del Codice
    try:
        exec(module_code, temp_module.__dict__)
    except Exception as e:
        raise ResourceLoadError(
            f"Errore di esecuzione/runtime nel modulo.",
            adapter_name=adapter,
            path=path
        ) from e
        
    # 6. Esecuzione del Filtro API
    try:
        final_module = export_func(temp_module)
        if not isinstance(final_module, types.ModuleType):
             raise TypeError("La funzione EXPORT_FUNCTION non ha restituito un oggetto modulo.")
        
        print(f"✅ Modulo Python '{adapter}' filtrato ed esportato da '{test_path}'.")
        return final_module
            
    except Exception as e:
        raise ResourceLoadError(
            f"Errore durante l'esecuzione del filtro (EXPORT_FUNCTION).",
            adapter_name=adapter,
            path=path
        ) from e


async def _load_json_resource(lang, adapter, resource_content):
    """Gestisce il parsing di un file JSON (Usando lang.json_to_pydict)."""
    try:
        # Usa lang.json_to_pydict
        return await lang.json_to_pydict(resource_content, adapter)
    except Exception as e:
        raise ResourceLoadError(
            f"Errore di parsing del JSON per la risorsa.",
            adapter_name=adapter,
            path='JSON_PATH' # Usare il path effettivo se accessibile
        ) from e


# --- 3. Funzione Principale language.resource ---

async def resource(lang, **constants):
    """
    Carica una risorsa (modulo Python o file JSON) dinamicamente con tracciamento degli errori.
    """
    path = constants.get("path", "")
    # Remove leading slash if present
    if path.startswith('/'):
        path = path[1:]
    adapter = constants.get("adapter", 'NaM').replace('.test', '')
    
    try:
        # --- 1. Recupero del Contenuto ---
        if 'code' in constants:
            resource_content = constants['code']
        else:
            # USA lang.backend per il recupero iniziale del contenuto
            resource_content = await lang.backend(**constants) 
        
        if not resource_content:
            raise FileNotFoundError(f"Contenuto non valido o vuoto.")

        # --- 2. Dispatch in base al Tipo ---
        if path.endswith('.py'):
            # Passa lang alla funzione helper
            return await _load_python_module(lang, path, adapter, resource_content)

        elif path.endswith('.json'):
            # Passa lang alla funzione helper
            return await _load_json_resource(lang, adapter, resource_content)
        
        else:
            print(f"⚠️ Tipo di risorsa non supportato per '{adapter}'. Restituzione del contenuto grezzo.")
            return resource_content 
            
    except ResourceLoadError:
        raise
        
    except (FileNotFoundError, IOError) as e:
        error_msg = str(e)
        raise ResourceLoadError(error_msg, adapter_name=adapter, path=path) from e
        
    except Exception as e:
        raise ResourceLoadError(f"Errore non gestito: {e}", adapter_name=adapter, path=path) from e

# --- Funzioni di Utilità (Modificate per non dipendere da un 'language' globale) ---
# ... (Mantieni il resto del codice di language.py inalterato qui, poiché 
# queste funzioni non chiamano `resource` o `backend` direttamente, 
# ma saranno accessibili tramite il modulo restituito dal filtro)
# In particolare, `model` dovrà essere aggiornato per usare `lang.resource`


async def model(schema, value=None, mode='full', lang=None):
    """
    Convalida, popola, trasforma e struttura i dati utilizzando uno schema Cerberus.
    Aggiornato per usare lang.resource.
    """
    value = value or {}

    # Se lo schema è una stringa, prova a caricarlo dinamicamente
    if isinstance(schema, str):
        try:
            # USA lang.resource
            module = await lang.resource(lang, path=f'application/model/{schema}.py')
            cerberus_schema = getattr(module, 'SCHEMA', None)
            if not cerberus_schema:
                raise AttributeError(f"⚠️ Lo schema Cerberus 'SCHEMA' non trovato nel modulo '{schema}'.")
            schema = cerberus_schema
        except Exception as e:
            print(f"Errore durante il caricamento dello schema '{schema}': {e}")
            raise

    # ... (Il resto della funzione model rimane invariato)
    if not isinstance(schema, dict):
        raise TypeError("Lo schema deve essere un dizionario valido per Cerberus.")

    # 1. Popolamento e Trasformazione Iniziale (Default, Funzioni)
    processed_value = value.copy()

    for key in schema.copy():
        item = schema[key]
        for field_name, field_rules in item.copy().items():
            if field_name.startswith('_'):
                schema.get(key).pop(field_name)


    for field_name, field_rules in schema.copy().items():
        if isinstance(field_rules, dict) and 'function' in field_rules:
            func_name = field_rules['function']
            if func_name == 'generate_identifier':
                if field_name not in processed_value:
                    processed_value[field_name] = generate_identifier()
            elif func_name == 'time_now_utc':
                if field_name not in processed_value:
                    processed_value[field_name] = time_now_utc()

    print("##################",schema)
    v = MyCustomValidator(schema,allow_unknown=True)

    if not v.validate(processed_value):
        print(f"⚠️ Errore di validazione: {v.errors}  | data:{processed_value}")
        raise ValueError(f"⚠️ Errore di validazione: {v.errors} | data:{processed_value}")

    final_output = v.document

    return final_output


# --- Funzioni Globali (backend, json_to_pydict, extract_modules_from_code) ---
# Queste devono essere disponibili nell'ambito del modulo o iniettate nell'oggetto lang

def extract_params(s):
    match = re.search(r"\w+\((.*)\)", s)
    if not match: return {}
    content = match.group(1).strip()
    if not content: return {}
    json_content = re.sub(r'(\b\w+)\s*:', r'"\1":', content)
    json_content = re.sub(r"'(.*?)'", r'"\1"', json_content)
    json_content = json_content.replace("True", "true").replace("False", "false").replace("None", "null")
    final_json_string = "{" + json_content + "}"
    try:
        return json.loads(final_json_string)
    except json.JSONDecodeError as e:
        print(f"Errore di decodifica JSON: {e}")
        print(f"Stringa JSON tentata: {final_json_string}")
        return {}
# ... (restanti funzioni come convert, generate_identifier, time_now_utc, wildcard_match, ...)

def convert(data, ttype):
    # Convert data to string first
    s = str(data).strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')): 
        s = s[1:-1]
    return ast.literal_eval(s)

def generate_identifier(): return str(uuid.uuid4())
def time_now_utc(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
def wildcard_match(check, pattern):
    check = list(check)
    r = []
    for item in check:
        if fnmatch.fnmatch(item, pattern): r.append(item)
    print(f"Wildcard match: {pattern} {check} -> {r}")
    return r

async def extract_modules_from_code(code):
    extracted_modules = None
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "resources":
                        extracted_modules = ast.literal_eval(node.value)
                        break
    except Exception as e: print(f"Errore durante l'analisi dei moduli richiesti: {e}")
    return extracted_modules if extracted_modules is not None else {}

if sys.platform != 'emscripten':
    async def backend(**constants):
        path = constants["path"]
        # Fissaggio: usa il percorso corretto per l'I/O.
        if path.startswith('/'): path = path[1:]
        try:
            with open(f"src/{path}", "r") as f:
                return f.read()
        except FileNotFoundError:
            # Solleva FileNotFoundError, che sarà catturato e incapsulato da resource()
            raise FileNotFoundError(f"File non trovato: src/{path}")
        
else:
    import js
    async def backend(**constants):
        area, service, adapter = constants["path"].split(".")
        module_url = f"{area}/{service}/{adapter}.py"
        response = await js.fetch(module_url,{'method':'GET'})
        return await response.text()
    

async def json_to_pydict(content: str, adapter_name: str):
    try:
        parsed_json = json.loads(content)
        print(f"✅ Risorsa JSON '{adapter_name}' caricata con successo.")
        return parsed_json
    except json.JSONDecodeError as e:
        raise ValueError(f"⚠️ Errore durante il parsing del JSON per '{adapter_name}': {e}")

async def load_provider(lang,**constants):
    adapter = constants.get('adapter', '')
    service = constants.get('service', '')
    payload = constants.get('payload', '')
    if service not in di: di[service] = lambda di: list([])
    try:
        module = await resource(lang,**constants)
        provider = getattr(module, 'adapter')
        di[service].append(provider(config=payload))
    except Exception as e:
        exc_type, exc_obj, tb = sys.exc_info()
        last_tb = traceback.extract_tb(tb)[-1]
        error_info = {"file": last_tb.filename, "line": last_tb.lineno, "error": str(e),}
        print(f"❌ Errore generico: {error_info}")
        print(f"❌ Error: loading 'infrastructure.{service}.{adapter}': {repr(e)}")

async def load_manager(lang,**constants):
    service = constants.get('name', '')
    path = constants["path"]
    if service not in di: di[service] = lambda di: list([])
    try:
        module = await resource(lang,**constants)
        provider = getattr(module, service)
        providers = constants["provider"]
        if providers is list:
            providers = [di[provider] for provider in providers ]
        else:
            if providers not in di: di[providers] = lambda di: list([])
            providers = di[providers]
        di[service] = lambda _di: provider(providers=providers)
    except Exception as e:
        print(constants)
        print(f"❌  '{path}': {repr(e)}")
    
def validate_toml(content):
    config = tomli.loads(content)
    errors = []
    # ... (logica di validazione omessa per brevità)
    if errors:
        print("⛔ Errore di validazione:")
        for error in errors: print(f"  - {error}")
        exit(1)
    else: print("✅ Il file TOML è valido!")

def get_confi(**constants):
    jinjaEnv = Environment()
    jinjaEnv.filters['get'] = get
    # ... (logica di caricamento TOML omessa per brevità)
    if sys.platform != 'emscripten':
        with open('pyproject.toml', 'r') as f: text = f.read()
    else:
        import js; req = js.XMLHttpRequest.new(); req.open("GET", "pyproject.toml", False); req.send()
        text = str(req.response)
    template = jinjaEnv.from_string(text)
    content = template.render(constants)
    validate_toml(content)
    return tomli.loads(content)

def get(dictionary, domain, default=None):
    if not isinstance(dictionary, (dict, list)): raise TypeError("Il primo argomento deve essere un dizionario o una lista.")
    current_data = dictionary
    for chunk in domain.split('.'):
        if isinstance(current_data, list):
            try: index = int(chunk); current_data = current_data[index]
            except (IndexError, ValueError, TypeError): return default
        elif isinstance(current_data, dict):
            if chunk in current_data: current_data = current_data[chunk]
            else: return default
        else: return default
    return current_data 

def find_matching_keys(mapper, schema) :
    if not isinstance(mapper, dict) or not mapper: return None
    if not isinstance(schema, dict) or not schema: return None
    number_occurrences = {}
    for original_field_name, format_mappings in mapper.items():
        if not isinstance(format_mappings, dict): continue
        for format_key, output_path_in_mapper in format_mappings.items():
            if _check_path_in_schema(output_path_in_mapper, schema):
                number_occurrences.setdefault(format_key, 0)
                number_occurrences[format_key] += 1
    if not number_occurrences: return None
    max_value = max(number_occurrences.values())
    winning_keys = [k for k, v in number_occurrences.items() if v == max_value]
    if winning_keys: return winning_keys[0]
    return None

def translation(data_dict, mapper, values, input, output):
    translated = {}
    if not isinstance(data_dict, dict): raise TypeError("Il primo argomento deve essere un dizionario.")
    if not isinstance(mapper, dict): raise TypeError("'mapper' deve essere un dizionario.")
    if not isinstance(values, dict): raise TypeError("'values' deve essere un dizionario.")
    if not isinstance(input, dict): raise TypeError("'input' deve essere un dizionario.")
    if not isinstance(output, dict): raise TypeError("'output' deve essere un dizionario.")
    key = find_matching_keys(mapper,output) or find_matching_keys(mapper,input)
    for k, v in mapper.items():
        n1 = get(data_dict, k)
        n2 = get(data_dict, v.get(key, None))
        if n1:
            output_key = v.get(key, None)
            translated |= put(translated, output_key, n1, output)
        if n2:
            output_key = k
            translated |= put(translated, output_key, n2, output)
    fieldsData = data_dict.keys()
    fieldsOutput = output.keys()
    for field in fieldsData:
        if field in fieldsOutput:
            translated |= put(translated, field, get(data_dict, field), output)
    return translated

def filter(self): pass
def first(self): pass
def last(iterable): return iterable[-1] if iterable else None
def keys(self): pass
def map(self): pass
def reduce(self): pass
def replace(self): pass
def slice(self): pass
def route(url: dict, new_part: str) -> str:
    url = copy.deepcopy(url)
    protocol = url.get("protocol", "http"); host = url.get("host", "localhost"); port = url.get("port")
    path = url.get("path", []); query_params = url.get('query', {}); fragment = url.get("fragment", "")
    parsed_new_part = urlparse(new_part)
    if parsed_new_part.path: path = [p for p in parsed_new_part.path.split('/') if p]
    if parsed_new_part.query:
        [query_params.setdefault(k, []).append(v) for k, v in (param.split('=', 1) for param in parsed_new_part.query.split('&') if '=' in param)]
    query_parts = []
    for key, values in query_params.items():
        if values: query_parts.append(f"{key}={values[-1]}")
    query_string = "&".join(query_parts)
    base_url = ""
    if path: base_url += "/" + "/".join(path)
    if query_string: base_url += f"?{query_string}"
    if fragment: base_url += f"#{fragment}"
    return base_url

def route3(url: dict, query_string: str) -> str:
    existing_query = url.get('query', {})
    new_params = parse_qs(query_string, keep_blank_values=True)
    combined_params = {k: v for k, v in existing_query.items()}
    for key, value in new_params.items(): combined_params[key] = value
    protocol = url.get("protocol", "http"); host = url.get("host", "localhost"); port = url.get("port")
    path_list = url.get("path", []); fragment = url.get("fragment", "")
    base_url = f"{protocol}://{host}"
    if port: base_url += f":{port}"
    if path_list: base_url += "/" + "/".join(path_list)
    encoded_query = urlencode(combined_params, doseq=True)
    final_url = base_url
    if encoded_query: final_url += "?" + encoded_query
    if fragment: final_url += "#" + fragment
    return final_url

def route2(url: dict, **data) -> str:
    protocol = url.get("protocol", "http"); host = url.get("host", "localhost"); port = url.get("port")
    path = "/".join(url.get("path", [])) if 'path' not in data else data['path']
    fragment = url.get("fragment", []); query = url.get('query',{}); qq = data.get('query',{})
    base_url = ""
    if path: base_url += f"/{path}"
    query_params = {k: list(v) for k, v in query.items()}
    if 'query' in data and isinstance(data['query'], dict):
        for key, value in data['query'].items(): query_params[key] = value
    query_parts = []
    for key, values in query_params.items():
        if values: query_parts.append(f"{key}={values[-1]}")
    query_string = "&".join(query_parts)
    final_url = base_url
    if query_string: final_url += "?" + query_string
    if len(fragment): final_url += "#" + "&".join(fragment)
    return final_url

def _get_next_schema(schema, key):
    if isinstance(schema, dict):
        if 'schema' in schema:
            if schema.get('type') == 'list': return schema['schema']
            if isinstance(schema['schema'], dict): return schema['schema'].get(key)
        return schema.get(key)
    return None

def _check_path_in_schema(path: str, schema: Any) -> bool:
    if not isinstance(path, str) or not path: return False
    if not isinstance(schema, dict) or not schema: return False
    current_schema_node = schema
    path_chunks = path.split('.')
    for i, chunk in enumerate(path_chunks):
        is_last_chunk = (i == len(path_chunks) - 1)
        if current_schema_node is None or not isinstance(current_schema_node, dict): return False
        next_schema_part = _get_next_schema(current_schema_node, chunk)
        if next_schema_part is None: return False
        if not is_last_chunk: current_schema_node = next_schema_part
    return True

def put(data: dict, path: str, value: Any, schema: dict) -> dict:
    if not isinstance(data, dict): raise TypeError("Il dizionario iniziale deve essere di tipo dict.")
    if not isinstance(path, str) or not path: raise ValueError("Il dominio deve essere una stringa non vuota.")
    if not isinstance(schema, dict) or not schema: raise ValueError("Lo schema deve essere un dizionario valido.")
    result = copy.deepcopy(data); node, sch = result, schema; chunks = path.split('.')
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1; is_index = chunk.lstrip('-').isdigit()
        key = int(chunk) if is_index else chunk; next_sch = _get_next_schema(sch, chunk)
        if isinstance(node, dict):
            if is_index: raise IndexError(f"Indice numerico '{chunk}' usato in un dizionario a livello {i}.")
            if is_last:
                if next_sch is None: raise IndexError(f"Campo '{chunk}' non definito nello schema.")
                if not MyCustomValidator({chunk: next_sch}, allow_unknown=False).validate({chunk: value}): raise ValueError(f"Valore non valido per '{chunk}': {value}")
                node[key] = value
            else:
                node.setdefault(key, {} if next_sch and next_sch.get('type') == 'dict'
                                     else [] if next_sch and next_sch.get('type') == 'list'
                                     else None)
                if node[key] is None: raise IndexError(f"Nodo intermedio '{chunk}' non valido nello schema.")
                node, sch = node[key], next_sch
        elif isinstance(node, list):
            if not is_index: raise IndexError(f"Chiave '{chunk}' non numerica usata in una lista a livello {i}.")
            if not isinstance(next_sch, dict) or 'type' not in next_sch: raise IndexError(f"Schema non valido per lista a livello {i}.")
            if key == -1:
                t = next_sch['type']; new_elem = {} if t == 'dict' else [] if t == 'list' else None; node.append(new_elem); key = len(node) - 1
            if key < 0: raise IndexError(f"Indice negativo '{chunk}' non valido in lista.")
            while len(node) <= key:
                t = next_sch['type']; node.append({} if t == 'dict' else [] if t == 'list' else None)
            if is_last:
                if not MyCustomValidator({chunk: next_sch}, allow_unknown=False).validate({chunk: value}): raise ValueError(f"Valore non valido per indice '{chunk}': {value}")
                node[key] = value
            else:
                if node[key] is None or not isinstance(node[key], (dict, list)):
                    t = next_sch['type'];
                    if t == 'dict': node[key] = {}
                    elif t == 'list': node[key] = []
                    else: raise IndexError(f"Tipo non contenitore '{t}' per nodo '{chunk}' in lista.")
                node, sch = node[key], next_sch
        else: raise IndexError(f"Nodo non indicizzabile al passo '{chunk}' (tipo: {type(node).__name__})")
    return result

class MyCustomValidator(Validator):
    def _normalize_coerce_identifier(self, value): return generate_identifier()
    def _normalize_setter_identifier(self, mapping, field, value): return generate_identifier()
    def _check_with_is_odd(self, field, value):
        if not value & 1: self._error(field, "Must be an odd number")
    def _validate_is_odd(self, constraint, field, value):
        if constraint is True and not bool(value & 1): self._error(field, "Must be an odd number")
    def _validate_function(self, constraint, field, value):
        if value == 'generate_identifier': return generate_identifier()
        elif value == 'time_now_utc': return time_now_utc()
        else: self._error(f"Funzione '{value}' sconosciuta o non supportata.")
